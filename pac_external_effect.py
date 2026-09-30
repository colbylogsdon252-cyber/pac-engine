from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Protocol

from pac_protected_execution import DurableExecutionStore, execution_id_for_token
from pac_downstream_adapter import AdapterCapabilities, AdapterClass, evaluate_authoritative_not_found
from pac_proof_token import verify_execution_authorization


CONFIRMED = "CONFIRMED"
NOT_FOUND = "NOT_FOUND"
FAILED = "FAILED"
UNKNOWN = "UNKNOWN"

TERMINAL_EFFECT_STATES = {"confirmed", "failed"}
BLOCKING_EFFECT_STATES = {"dispatching", "acknowledged", "indeterminate"}


@dataclass(frozen=True)
class ReconciliationEvidence:
    outcome: str
    downstream_reference: str | None = None
    authoritative_not_found: bool = False
    detail: str | None = None


class ExternalEffectAdapter(Protocol):
    system_id: str
    capabilities: AdapterCapabilities

    def dispatch(self, effect_id: str, operation: str, payload: dict) -> dict: ...
    def reconcile(
        self, effect_id: str, downstream_reference: str | None = None
    ) -> ReconciliationEvidence: ...


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def effect_id_for(
    execution_id: str, downstream_system: str, operation: str, effect_payload: dict
) -> str:
    material = {
        "execution_id": execution_id,
        "downstream_system": downstream_system,
        "operation": operation,
        "effect_payload": effect_payload,
    }
    return hashlib.sha256(_canonical_json(material)).hexdigest()


class ExternalEffectStore:
    """Durable effect ledger sharing the PAC SQLite deployment database."""

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
                CREATE TABLE IF NOT EXISTS pac_external_effect (
                    effect_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    downstream_system TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('prepared','dispatching','acknowledged',
                                  'confirmed','failed','indeterminate')
                    ),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    downstream_reference TEXT,
                    evidence_json TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def prepare(
        self,
        effect_id: str,
        execution_id: str,
        downstream_system: str,
        operation: str,
        effect_payload: dict,
    ) -> dict:
        digest = hashlib.sha256(_canonical_json(effect_payload)).hexdigest()
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO pac_external_effect
                    (effect_id, execution_id, downstream_system, operation,
                     request_digest, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'prepared', ?, ?)
                """,
                (effect_id, execution_id, downstream_system, operation, digest, now, now),
            )
            row = connection.execute(
                "SELECT * FROM pac_external_effect WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            connection.execute("COMMIT")
        if (
            row["execution_id"] != execution_id
            or row["downstream_system"] != downstream_system
            or row["operation"] != operation
            or row["request_digest"] != digest
        ):
            raise RuntimeError("effect identity conflicts with persisted effect binding")
        return dict(row)

    def transition(
        self,
        effect_id: str,
        from_states: tuple[str, ...],
        to_state: str,
        *,
        downstream_reference: str | None = None,
        evidence: dict | None = None,
        increment_attempt: bool = False,
    ) -> bool:
        placeholders = ",".join("?" for _ in from_states)
        assignments = ["state = ?", "updated_at = ?"]
        params: list[Any] = [to_state, int(time.time())]
        if downstream_reference is not None:
            assignments.append("downstream_reference = ?")
            params.append(downstream_reference)
        if evidence is not None:
            assignments.append("evidence_json = ?")
            params.append(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
        if increment_attempt:
            assignments.append("attempt_count = attempt_count + 1")
        params.extend([effect_id, *from_states])
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                f"UPDATE pac_external_effect SET {', '.join(assignments)} "
                f"WHERE effect_id = ? AND state IN ({placeholders})",
                params,
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1

    def get(self, effect_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pac_external_effect WHERE effect_id = ?", (effect_id,)
            ).fetchone()
        return None if row is None else dict(row)


def _evidence_dict(evidence: ReconciliationEvidence) -> dict:
    return {
        "outcome": evidence.outcome,
        "downstream_reference": evidence.downstream_reference,
        "authoritative_not_found": evidence.authoritative_not_found,
        "detail": evidence.detail,
    }


def reconcile_effect(
    effect_id: str,
    adapter: ExternalEffectAdapter,
    store: ExternalEffectStore,
) -> dict:
    record = store.get(effect_id)
    if record is None:
        return {"resolved": False, "reason": "effect_not_found"}

    evidence = adapter.reconcile(effect_id, record["downstream_reference"])
    evidence_dict = _evidence_dict(evidence)

    if evidence.outcome == CONFIRMED:
        store.transition(
            effect_id,
            ("dispatching", "acknowledged", "indeterminate"),
            "confirmed",
            downstream_reference=evidence.downstream_reference,
            evidence=evidence_dict,
        )
        return {"resolved": True, "state": "confirmed", "evidence": evidence_dict}

    if evidence.outcome == FAILED:
        store.transition(
            effect_id,
            ("dispatching", "acknowledged", "indeterminate"),
            "failed",
            downstream_reference=evidence.downstream_reference,
            evidence=evidence_dict,
        )
        return {"resolved": True, "state": "failed", "evidence": evidence_dict}

    if evidence.outcome == NOT_FOUND and evidence.authoritative_not_found:
        capabilities = adapter.capabilities
        observation_age = max(0, int(time.time()) - int(record["created_at"]))
        decision = evaluate_authoritative_not_found(
            capabilities, observation_age_seconds=observation_age
        )
        store.transition(
            effect_id,
            ("dispatching", "acknowledged", "indeterminate"),
            "indeterminate",
            evidence={**evidence_dict, "redispatch_policy": decision.reason},
        )
        return {
            "resolved": False,
            "state": "indeterminate",
            "reason": (
                "redispatch_eligible"
                if decision.redispatch_eligible
                else "authoritative_not_found_blocked"
            ),
            "redispatch_eligible": decision.redispatch_eligible,
            "policy_reason": decision.reason,
            "evidence": evidence_dict,
        }

    store.transition(
        effect_id,
        ("dispatching", "acknowledged", "indeterminate"),
        "indeterminate",
        evidence=evidence_dict,
    )
    return {
        "resolved": False,
        "state": "indeterminate",
        "reason": "insufficient_downstream_evidence",
        "evidence": evidence_dict,
    }


def execute_external_effect(
    payload: dict,
    token: dict,
    secret: str,
    operation: str,
    effect_payload: dict,
    adapter: ExternalEffectAdapter,
    execution_store: DurableExecutionStore,
    effect_store: ExternalEffectStore,
) -> dict:
    authorization = verify_execution_authorization(payload, token, secret)
    if not authorization.get("authorized", False):
        return {"executed": False, "reason": "authorization_denied", "authorization": authorization}

    execution_id = execution_id_for_token(token)
    effect_id = effect_id_for(execution_id, adapter.system_id, operation, effect_payload)
    existing = effect_store.get(effect_id)

    if existing is not None:
        if existing["state"] == "confirmed":
            return {"executed": False, "reason": "effect_already_confirmed", "effect_id": effect_id}
        if existing["state"] in BLOCKING_EFFECT_STATES:
            return {
                "executed": False,
                "reason": "reconciliation_required",
                "effect_id": effect_id,
                "effect_state": existing["state"],
            }
        if existing["state"] == "failed":
            return {"executed": False, "reason": "effect_failed", "effect_id": effect_id}

    if not execution_store.claim(execution_id):
        return {
            "executed": False,
            "reason": "authorization_replayed",
            "execution_id": execution_id,
            "execution_state": execution_store.state(execution_id),
        }

    effect_store.prepare(
        effect_id, execution_id, adapter.system_id, operation, effect_payload
    )
    if not effect_store.transition(
        effect_id, ("prepared",), "dispatching", increment_attempt=True
    ):
        execution_store.mark_indeterminate(execution_id)
        return {"executed": False, "reason": "effect_dispatch_claim_failed", "effect_id": effect_id}

    try:
        response = adapter.dispatch(effect_id, operation, effect_payload)
    except Exception:
        effect_store.transition(effect_id, ("dispatching",), "indeterminate")
        execution_store.mark_indeterminate(execution_id)
        return {
            "executed": False,
            "reason": "dispatch_outcome_indeterminate",
            "effect_id": effect_id,
        }

    downstream_reference = response.get("downstream_reference")
    effect_store.transition(
        effect_id,
        ("dispatching",),
        "acknowledged",
        downstream_reference=downstream_reference,
        evidence={"dispatch_response": response},
    )

    reconciliation = reconcile_effect(effect_id, adapter, effect_store)
    if reconciliation.get("state") == "confirmed":
        execution_store.complete(
            execution_id,
            {"effect_id": effect_id, "downstream_reference": downstream_reference},
        )
        return {
            "executed": True,
            "reason": "external_effect_confirmed",
            "execution_id": execution_id,
            "effect_id": effect_id,
            "downstream_reference": downstream_reference,
        }

    execution_store.mark_indeterminate(execution_id)
    return {
        "executed": False,
        "reason": "reconciliation_required",
        "execution_id": execution_id,
        "effect_id": effect_id,
        "reconciliation": reconciliation,
    }
