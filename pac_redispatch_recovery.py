from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from pac_downstream_adapter import AdapterClass
from pac_external_effect import (
    CONFIRMED,
    ExternalEffectAdapter,
    ExternalEffectStore,
    reconcile_effect,
)
from pac_protected_execution import DurableExecutionStore


@dataclass(frozen=True)
class RedispatchAuthorization:
    authorization_id: str
    effect_id: str
    evidence_digest: str
    policy_reason: str


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class RedispatchAuthorizationStore:
    """Durable, single-consumption recovery authority for an existing PAC effect."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pac_redispatch_authorization (
                    authorization_id TEXT PRIMARY KEY,
                    effect_id TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    policy_reason TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('authorized','consumed')),
                    created_at INTEGER NOT NULL,
                    consumed_at INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS pac_one_active_redispatch_per_effect
                ON pac_redispatch_authorization(effect_id)
                """
            )

    def authorize(
        self, effect_id: str, evidence: dict, policy_reason: str
    ) -> RedispatchAuthorization:
        evidence_digest = hashlib.sha256(_canonical_json(evidence)).hexdigest()
        authorization_id = hashlib.sha256(
            _canonical_json(
                {
                    "effect_id": effect_id,
                    "evidence_digest": evidence_digest,
                    "policy_reason": policy_reason,
                }
            )
        ).hexdigest()
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO pac_redispatch_authorization
                    (authorization_id, effect_id, evidence_digest, policy_reason, state, created_at)
                VALUES (?, ?, ?, ?, 'authorized', ?)
                """,
                (authorization_id, effect_id, evidence_digest, policy_reason, now),
            )
            row = connection.execute(
                "SELECT * FROM pac_redispatch_authorization WHERE effect_id = ?",
                (effect_id,),
            ).fetchone()
            connection.execute("COMMIT")
        if (
            row["authorization_id"] != authorization_id
            or row["evidence_digest"] != evidence_digest
            or row["policy_reason"] != policy_reason
        ):
            raise RuntimeError("redispatch authority conflicts with existing effect authority")
        return RedispatchAuthorization(
            authorization_id, effect_id, evidence_digest, policy_reason
        )

    def consume(self, authorization: RedispatchAuthorization) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE pac_redispatch_authorization
                SET state = 'consumed', consumed_at = ?
                WHERE authorization_id = ? AND effect_id = ?
                  AND evidence_digest = ? AND policy_reason = ?
                  AND state = 'authorized'
                """,
                (
                    int(time.time()),
                    authorization.authorization_id,
                    authorization.effect_id,
                    authorization.evidence_digest,
                    authorization.policy_reason,
                ),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1


def authorize_redispatch(
    effect_id: str,
    adapter: ExternalEffectAdapter,
    effect_store: ExternalEffectStore,
    authorization_store: RedispatchAuthorizationStore,
) -> dict:
    record = effect_store.get(effect_id)
    if record is None or record["state"] != "indeterminate":
        return {"authorized": False, "reason": "effect_not_indeterminate"}

    if adapter.capabilities.adapter_class is AdapterClass.C:
        return {"authorized": False, "reason": "class_c_redispatch_forbidden"}

    reconciliation = reconcile_effect(effect_id, adapter, effect_store)
    if not reconciliation.get("redispatch_eligible", False):
        return {
            "authorized": False,
            "reason": "redispatch_not_proven_safe",
            "reconciliation": reconciliation,
        }

    evidence = reconciliation["evidence"]
    authority = authorization_store.authorize(
        effect_id, evidence, reconciliation["policy_reason"]
    )
    return {"authorized": True, "authorization": authority}


def recover_external_effect(
    authorization: RedispatchAuthorization,
    operation: str,
    effect_payload: dict,
    adapter: ExternalEffectAdapter,
    execution_store: DurableExecutionStore,
    effect_store: ExternalEffectStore,
    authorization_store: RedispatchAuthorizationStore,
) -> dict:
    record = effect_store.get(authorization.effect_id)
    if record is None or record["state"] != "indeterminate":
        return {"executed": False, "reason": "effect_not_recoverable"}

    if adapter.capabilities.adapter_class is AdapterClass.C:
        return {"executed": False, "reason": "class_c_redispatch_forbidden"}

    expected_digest = hashlib.sha256(_canonical_json(effect_payload)).hexdigest()
    if (
        record["downstream_system"] != adapter.system_id
        or record["operation"] != operation
        or record["request_digest"] != expected_digest
    ):
        return {"executed": False, "reason": "effect_binding_mismatch"}

    if not authorization_store.consume(authorization):
        return {"executed": False, "reason": "redispatch_authorization_unavailable"}

    if not effect_store.transition(
        authorization.effect_id,
        ("indeterminate",),
        "dispatching",
        increment_attempt=True,
        evidence={
            "redispatch_authorization_id": authorization.authorization_id,
            "policy_reason": authorization.policy_reason,
        },
    ):
        return {"executed": False, "reason": "redispatch_transition_failed"}

    try:
        response = adapter.dispatch(authorization.effect_id, operation, effect_payload)
    except Exception:
        effect_store.transition(
            authorization.effect_id, ("dispatching",), "indeterminate"
        )
        return {
            "executed": False,
            "reason": "redispatch_outcome_indeterminate",
            "effect_id": authorization.effect_id,
        }

    downstream_reference = response.get("downstream_reference")
    effect_store.transition(
        authorization.effect_id,
        ("dispatching",),
        "acknowledged",
        downstream_reference=downstream_reference,
        evidence={"redispatch_response": response},
    )
    reconciliation = reconcile_effect(authorization.effect_id, adapter, effect_store)

    if reconciliation.get("state") == "confirmed":
        execution_store.resolve_indeterminate_complete(
            record["execution_id"],
            {
                "effect_id": authorization.effect_id,
                "downstream_reference": downstream_reference,
                "recovered": True,
            },
        )
        return {
            "executed": True,
            "reason": "redispatch_confirmed",
            "effect_id": authorization.effect_id,
        }

    return {
        "executed": False,
        "reason": "reconciliation_required",
        "effect_id": authorization.effect_id,
        "reconciliation": reconciliation,
    }
