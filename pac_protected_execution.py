from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from pac_proof_token import verify_execution_authorization


class DurableExecutionStore:
    """SQLite-backed atomic execution state for persistent PAC replay control."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = str(Path(path))
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
                CREATE TABLE IF NOT EXISTS pac_execution_state (
                    execution_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK (state IN ('claimed', 'completed', 'indeterminate')),
                    claimed_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    result_json TEXT
                )
                """
            )

    def claim(self, execution_id: str) -> bool:
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO pac_execution_state
                    (execution_id, state, claimed_at)
                VALUES (?, 'claimed', ?)
                """,
                (execution_id, now),
            )
            connection.execute("COMMIT")
            return cursor.rowcount == 1

    def complete(self, execution_id: str, result: Any) -> None:
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE pac_execution_state
                SET state = 'completed', completed_at = ?, result_json = ?
                WHERE execution_id = ? AND state = 'claimed'
                """,
                (int(time.time()), encoded, execution_id),
            )
            if cursor.rowcount != 1:
                connection.execute("ROLLBACK")
                raise RuntimeError("execution claim is not active")
            connection.execute("COMMIT")

    def release(self, execution_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM pac_execution_state WHERE execution_id = ? AND state = 'claimed'",
                (execution_id,),
            )
            connection.execute("COMMIT")

    def mark_indeterminate(self, execution_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE pac_execution_state
                SET state = 'indeterminate'
                WHERE execution_id = ? AND state = 'claimed'
                """,
                (execution_id,),
            )
            connection.execute("COMMIT")

    def state(self, execution_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state FROM pac_execution_state WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        return None if row is None else str(row["state"])


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def execution_id_for_token(token: dict) -> str:
    return hashlib.sha256(_canonical_json(token)).hexdigest()


def execute_protected(
    payload: dict,
    token: dict,
    secret: str,
    action: Callable[[], Any],
    replay_store: DurableExecutionStore,
) -> dict:
    """Verify PAC authorization, durably claim it, invoke once, then persist completion."""

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
            "execution_state": replay_store.state(execution_id),
        }

    try:
        result = action()
    except Exception:
        replay_store.release(execution_id)
        raise

    try:
        replay_store.complete(execution_id, result)
    except Exception:
        replay_store.mark_indeterminate(execution_id)
        raise

    return {
        "executed": True,
        "reason": "protected_execution_completed",
        "execution_id": execution_id,
        "result": result,
    }


# Compatibility name retained for callers; semantics are now durable when a path is supplied.
ExecutionReplayStore = DurableExecutionStore
