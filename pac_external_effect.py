from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
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

ALLOWED_EFFECT_TRANSITIONS = {
    "prepared": {"dispatching", "indeterminate"},
    "dispatching": {"acknowledged", "confirmed", "failed", "indeterminate"},
    "acknowledged": {"confirmed", "failed", "indeterminate"},
    "indeterminate": {"dispatching", "confirmed", "failed", "indeterminate"},
    "confirmed": set(),
    "failed": set(),
}


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

    def claim_execution_and_prepare(
        self,
        execution_store: DurableExecutionStore,
        effect_id: str,
        execution_id: str,
        downstream_system: str,
        operation: str,
        effect_payload: dict,
    ) -> bool:
        if Path(self.path).resolve() != Path(execution_store.path).resolve():
            raise RuntimeError("execution and effect stores must share one PAC database")
        digest = hashlib.sha256(_canonical_json(effect_payload)).hexdigest()
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            execution_cursor = connection.execute(
                """
                INSERT OR IGNORE INTO pac_execution_state
                    (execution_id, state, claimed_at)
                VALUES (?, 'claimed', ?)
                """,
                (execution_id, now),
            )
            if execution_cursor.rowcount != 1:
                connection.execute("ROLLBACK")
                return False
            try:
                connection.execute(
                    """
                    INSERT INTO pac_external_effect
                        (effect_id, execution_id, downstream_system, operation,
                         request_digest, state, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'prepared', ?, ?)
                    """,
                    (effect_id, execution_id, downstream_system, operation, digest, now, now),
                )
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                return False
            connection.execute("COMMIT")
            return True

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
        if not from_states:
            raise ValueError("from_states must not be empty")
        if to_state not in ALLOWED_EFFECT_TRANSITIONS:
            raise ValueError("unknown effect state")
        for source in from_states:
            if source not in ALLOWED_EFFECT_TRANSITIONS:
                raise ValueError("unknown source effect state")
            if to_state not in ALLOWED_EFFECT_TRANSITIONS[source]:
                raise ValueError(f"illegal effect transition: {source} -> {to_state}")
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


def _validated_evidence(value: Any) -> ReconciliationEvidence:
    if not isinstance(value, ReconciliationEvidence):
        raise ValueError("adapter reconciliation evidence must be ReconciliationEvidence")
    if value.outcome not in {CONFIRMED, NOT_FOUND, FAILED, UNKNOWN}:
        raise ValueError("adapter reconciliation outcome is invalid")
    if value.downstream_reference is not None and not isinstance(value.downstream_reference, str):
        raise ValueError("downstream_reference must be a string or null")
    if not isinstance(value.authoritative_not_found, bool):
        raise ValueError("authoritative_not_found must be boolean")
    if value.detail is not None and not isinstance(value.detail, str):
        raise ValueError("evidence detail must be a string or null")
    if value.authoritative_not_found and value.outcome != NOT_FOUND:
        raise ValueError("authoritative_not_found is only valid with NOT_FOUND")
    return value


def _validated_dispatch_response(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("adapter dispatch response must be a dict")
    reference = value.get("downstream_reference")
    if reference is not None and not isinstance(reference, str):
        raise ValueError("dispatch downstream_reference must be a string or null")
    return value


def _evidence_dict(evidence: ReconciliationEvidence) -> dict:
    evidence = _validated_evidence(evidence)
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

    try:
        evidence = _validated_evidence(
            adapter.reconcile(effect_id, record["downstream_reference"])
        )
        evidence_dict = _evidence_dict(evidence)
    except Exception as exc:
        store.transition(
            effect_id,
            ("dispatching", "acknowledged", "indeterminate"),
            "indeterminate",
            evidence={"outcome": UNKNOWN, "detail": f"invalid_adapter_evidence:{type(exc).__name__}"},
        )
        return {
            "resolved": False,
            "state": "indeterminate",
            "reason": "invalid_adapter_evidence",
        }

    if evidence.outcome == CONFIRMED:
        transitioned = store.transition(
            effect_id,
            ("dispatching", "acknowledged", "indeterminate"),
            "confirmed",
            downstream_reference=evidence.downstream_reference,
            evidence=evidence_dict,
        )
        current = store.get(effect_id)
        if not transitioned and (current is None or current["state"] != "confirmed"):
            return {"resolved": False, "state": None if current is None else current["state"], "reason": "reconciliation_state_race"}
        return {"resolved": True, "state": "confirmed", "evidence": evidence_dict}

    if evidence.outcome == FAILED:
        transitioned = store.transition(
            effect_id,
            ("dispatching", "acknowledged", "indeterminate"),
            "failed",
            downstream_reference=evidence.downstream_reference,
            evidence=evidence_dict,
        )
        current = store.get(effect_id)
        if not transitioned and (current is None or current["state"] != "failed"):
            return {"resolved": False, "state": None if current is None else current["state"], "reason": "reconciliation_state_race"}
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
            completed = execution_store.complete_confirmed_effect(
                execution_id,
                {
                    "effect_id": effect_id,
                    "downstream_reference": existing["downstream_reference"],
                    "recovered": True,
                },
            )
            return {
                "executed": False,
                "reason": "effect_already_confirmed",
                "effect_id": effect_id,
                "execution_recovered": completed,
            }
        if existing["state"] == "prepared":
            execution_state = execution_store.state(execution_id)
            if execution_state != "claimed":
                return {
                    "executed": False,
                    "reason": "prepared_effect_execution_state_mismatch",
                    "effect_id": effect_id,
                    "execution_state": execution_state,
                }
            if not effect_store.transition(
                effect_id, ("prepared",), "dispatching", increment_attempt=True
            ):
                return {
                    "executed": False,
                    "reason": "prepared_effect_resume_race",
                    "effect_id": effect_id,
                }
        elif existing["state"] in BLOCKING_EFFECT_STATES:
            return {
                "executed": False,
                "reason": "reconciliation_required",
                "effect_id": effect_id,
                "effect_state": existing["state"],
            }
        elif existing["state"] == "failed":
            return {"executed": False, "reason": "effect_failed", "effect_id": effect_id}

    if existing is None and not effect_store.claim_execution_and_prepare(
        execution_store,
        effect_id,
        execution_id,
        adapter.system_id,
        operation,
        effect_payload,
    ):
        return {
            "executed": False,
            "reason": "authorization_replayed_or_effect_conflict",
            "execution_id": execution_id,
            "execution_state": execution_store.state(execution_id),
        }
    if existing is None:
        if not effect_store.transition(
            effect_id, ("prepared",), "dispatching", increment_attempt=True
        ):
            execution_store.mark_indeterminate(execution_id)
            return {"executed": False, "reason": "effect_dispatch_claim_failed", "effect_id": effect_id}

    try:
        response = _validated_dispatch_response(
            adapter.dispatch(effect_id, operation, effect_payload)
        )
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
        if not execution_store.complete_confirmed_effect(
            execution_id,
            {"effect_id": effect_id, "downstream_reference": downstream_reference},
        ):
            return {
                "executed": False,
                "reason": "confirmed_effect_execution_completion_failed",
                "execution_id": execution_id,
                "effect_id": effect_id,
            }
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
