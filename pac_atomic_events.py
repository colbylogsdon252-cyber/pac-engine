"""Atomic notification insert used inside PAC state transactions."""
import json
import time
import uuid

SCHEMA = """CREATE TABLE IF NOT EXISTS pac_notification_outbox (
 event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, subject_id TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 available_at INTEGER NOT NULL, lease_until INTEGER, created_at INTEGER NOT NULL,
 UNIQUE(event_type,subject_id))"""

EVENTS = {"execution.indeterminate", "effect.indeterminate", "execution.completed"}


def ensure_table(connection):
    connection.execute(SCHEMA)


def enqueue_atomic(connection, event_type, subject_id, metadata):
    if not connection.in_transaction:
        raise RuntimeError("Event insert requires active authoritative transaction")
    if event_type not in EVENTS or not isinstance(subject_id, str) or not 1 <= len(subject_id) <= 256:
        raise ValueError("Invalid event identity")
    if not isinstance(metadata, dict) or any(
        k not in ("state", "reason") or not isinstance(v, str) or len(v) > 256
        for k, v in metadata.items()
    ):
        raise ValueError("Invalid event metadata")
    payload = json.dumps({"event_type": event_type, "subject_id": subject_id, "metadata": metadata},
                         sort_keys=True, separators=(",", ":"))
    now = int(time.time())
    connection.execute("""INSERT OR IGNORE INTO pac_notification_outbox
        (event_id,event_type,subject_id,payload,state,available_at,created_at)
        VALUES (?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), event_type, subject_id, payload, "pending", now, now))
