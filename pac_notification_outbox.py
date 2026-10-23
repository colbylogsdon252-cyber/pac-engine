"""Durable PAC notification outbox; never executes downstream actions."""
import hashlib
import hmac
import json
import sqlite3
import time
import uuid

EVENTS = {"execution.indeterminate", "effect.indeterminate", "execution.completed"}


class NotificationOutbox:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pac_notification_outbox (
                event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
                subject_id TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                available_at INTEGER NOT NULL, lease_until INTEGER,
                created_at INTEGER NOT NULL,
                UNIQUE(event_type,subject_id))""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def enqueue(self, event_type, subject_id, metadata=None):
        if event_type not in EVENTS or not isinstance(subject_id, str) or not 1 <= len(subject_id) <= 256:
            raise ValueError("Invalid notification identity")
        metadata = {} if metadata is None else metadata
        if not isinstance(metadata, dict) or any(
            k not in ("state", "reason") or not isinstance(v, str) or len(v) > 256
            for k, v in metadata.items()
        ):
            raise ValueError("Only redacted state and reason metadata permitted")
        payload = json.dumps({"event_type": event_type, "subject_id": subject_id, "metadata": metadata},
                             sort_keys=True, separators=(",", ":"))
        now = int(time.time())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT OR IGNORE INTO pac_notification_outbox
                (event_id,event_type,subject_id,payload,state,available_at,created_at)
                VALUES (?,?,?,?,?,?,?)""", (str(uuid.uuid4()), event_type, subject_id, payload, "pending", now, now))
            event_id = db.execute("SELECT event_id FROM pac_notification_outbox WHERE event_type=? AND subject_id=?",
                                  (event_type, subject_id)).fetchone()[0]
            db.commit()
            return event_id

    def claim(self, now=None, lease_seconds=30):
        if not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("Invalid lease")
        now = int(time.time()) if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT event_id,payload,attempts FROM pac_notification_outbox
                WHERE (state='pending' AND available_at<=?) OR (state='leased' AND lease_until<=?)
                ORDER BY created_at,event_id LIMIT 1""", (now, now)).fetchone()
            if row:
                db.execute("""UPDATE pac_notification_outbox SET state='leased',
                    attempts=attempts+1,lease_until=? WHERE event_id=?""",
                    (now+lease_seconds, row[0]))
            db.commit()
        return None if row is None else {"event_id": row[0], "payload": row[1],
                                          "attempt": row[2]+1, "lease_until": now+lease_seconds}

    def finish(self, item, delivered, now=None, max_attempts=8):
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("Invalid attempts limit")
        now = int(time.time()) if now is None else now
        state = "delivered" if delivered else ("dead" if item["attempt"] >= max_attempts else "pending")
        delay = 0 if delivered else min(3600, 2 ** min(item["attempt"], 11))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE pac_notification_outbox
                SET state=?,available_at=?,lease_until=NULL
                WHERE event_id=? AND state='leased' AND attempts=? AND lease_until=?""",
                (state, now+delay, item["event_id"], item["attempt"], item["lease_until"])).rowcount
            db.commit()
            return changed == 1

    def status(self, event_id):
        with self.connect() as db:
            row = db.execute("SELECT state,attempts FROM pac_notification_outbox WHERE event_id=?",
                             (event_id,)).fetchone()
            return None if row is None else {"state": row[0], "attempts": row[1]}


def signed_headers(event_id, payload, secret, timestamp=None):
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("Webhook signing key too short")
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    body = (event_id + "." + timestamp + ".").encode() + payload.encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-PAC-Event-ID": event_id,
            "X-PAC-Timestamp": timestamp, "X-PAC-Signature": "sha256=" + signature}


def dispatch_one(outbox, sender, secret, now=None):
    """sender(payload, headers) is a trusted, separately configured transport.

    Never grant sender access to PAC Proof Tokens, execution stores, or adapters.
    """
    item = outbox.claim(now=now)
    if item is None:
        return None
    headers = signed_headers(item["event_id"], item["payload"], secret, timestamp=now)
    try:
        delivered = sender(item["payload"], headers) is True
    except Exception:
        delivered = False
    finished = outbox.finish(item, delivered, now=now)
    return {"event_id": item["event_id"], "delivered": delivered, "finalized": finished}
