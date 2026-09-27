from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Callable

from pac_proof_token import verify_execution_authorization


class ExecutionReplayStore:
    """Process-local atomic claim store for PAC MVP protected execution."""

    def __init__(self) -> None:
        self._claimed: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, execution_id: str) -> bool:
        with self._lock:
            if execution_id in self._claimed:
                return False
            self._claimed.add(execution_id)
            return True

    def release(self, execution_id: str) -> None:
        with self._lock:
            self._claimed.discard(execution_id)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def execution_id_for_token(token: dict) -> str:
    return hashlib.sha256(_canonical_json(token)).hexdigest()


def execute_protected(
    payload: dict,
    token: dict,
    secret: str,
    action: Callable[[], Any],
    replay_store: ExecutionReplayStore,
) -> dict:
    """Verify PAC authorization, atomically claim it, then invoke the action once."""

    authorization = verify_execution_authorization(payload, token, secret)
    if not authorization.get("authorized", False):
        return {
            "executed": False,
            "reason": "authorization_denied",
            "authorization": authorization,
        }

    execution_id = execution_id_for_token(token)
    if not replay_store.claim(execution_id):
        return {
            "executed": False,
            "reason": "authorization_replayed",
            "execution_id": execution_id,
        }

    try:
        result = action()
    except Exception:
        replay_store.release(execution_id)
        raise

    return {
        "executed": True,
        "reason": "protected_execution_completed",
        "execution_id": execution_id,
        "result": result,
    }
