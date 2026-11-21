"""Optional third-party webhook keyway. No PAC execution privileges.

Integrators provision a dedicated database and explicit tenant-bound event source.
Legacy events without verified tenant attribution are rejected.
"""
import json
import sqlite3
import time
import uuid
from pac_webhook_worker import SecureWebhookSender, validate_destination
from pac_notification_outbox import signed_headers


class WebhookKeyway:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pac_keyway_subscriptions (
                subscription_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                destination TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(tenant_id,destination))""")
            db.execute("""CREATE TABLE IF NOT EXISTS pac_keyway_deliveries (
                delivery_id TEXT PRIMARY KEY, subscription_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL, event_id TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, available_at INTEGER NOT NULL,
                lease_until INTEGER, UNIQUE(subscription_id,event_id))""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def identity(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 128 or not all(
            c.isascii() and (c.isalnum() or c in "-_") for c in value
        ):
            raise ValueError("Invalid identifier")
        return value

    def provision(self, tenant_id, destination):
        """Trusted host must authenticate the tenant before calling this method."""
        self.identity(tenant_id)
        validate_destination(destination)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT OR IGNORE INTO pac_keyway_subscriptions
                (subscription_id,tenant_id,destination) VALUES (?,?,?)""",
                (str(uuid.uuid4()),tenant_id,destination))
            result = db.execute("""SELECT subscription_id FROM pac_keyway_subscriptions
                WHERE tenant_id=? AND destination=?""", (tenant_id,destination)).fetchone()[0]
            db.commit()
            return result

    def revoke(self, tenant_id, subscription_id):
        self.identity(tenant_id)
        self.identity(subscription_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE pac_keyway_subscriptions SET enabled=0
                WHERE tenant_id=? AND subscription_id=?""", (tenant_id,subscription_id)).rowcount
            db.execute("""UPDATE pac_keyway_deliveries SET state='dead'
                WHERE tenant_id=? AND subscription_id=? AND state IN ('pending','leased')""",
                (tenant_id,subscription_id))
            db.commit()
            return changed == 1

    def enqueue_verified(self, tenant_id, event_id, payload, verified_tenant_id):
        """verified_tenant_id must come from the trusted host's authenticated source."""
        self.identity(tenant_id)
        self.identity(event_id)
        if tenant_id != verified_tenant_id:
            raise PermissionError("Tenant attribution not verified")
        event = json.loads(payload)
        if not isinstance(event, dict) or event.get("tenant_id") != tenant_id:
            raise PermissionError("Event tenant mismatch")
        now = int(time.time())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            subscriptions = db.execute("""SELECT subscription_id FROM pac_keyway_subscriptions
                WHERE tenant_id=? AND enabled=1""", (tenant_id,)).fetchall()
            for (subscription_id,) in subscriptions:
                db.execute("""INSERT OR IGNORE INTO pac_keyway_deliveries
                    (delivery_id,subscription_id,tenant_id,event_id,payload,available_at)
                    VALUES (?,?,?,?,?,?)""",
                    (str(uuid.uuid4()),subscription_id,tenant_id,event_id,payload,now))
            db.commit()
            return len(subscriptions)

    def claim(self, tenant_id, now=None, lease_seconds=30):
        self.identity(tenant_id)
        now = int(time.time()) if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT d.delivery_id,d.event_id,d.payload,d.attempts,s.destination
                FROM pac_keyway_deliveries d JOIN pac_keyway_subscriptions s
                ON d.subscription_id=s.subscription_id AND d.tenant_id=s.tenant_id
                WHERE d.tenant_id=? AND s.enabled=1 AND
                ((d.state='pending' AND d.available_at<=?) OR
                (d.state='leased' AND d.lease_until<=?))
                ORDER BY d.rowid LIMIT 1""", (tenant_id,now,now)).fetchone()
            if row:
                db.execute("""UPDATE pac_keyway_deliveries SET state='leased',
                    attempts=attempts+1,lease_until=? WHERE delivery_id=?""",
                    (now+lease_seconds,row[0]))
            db.commit()
        return None if row is None else {
            "delivery_id":row[0],"event_id":row[1],"payload":row[2],
            "attempt":row[3]+1,"destination":row[4],"lease_until":now+lease_seconds}

    def finish(self, tenant_id, item, delivered, now=None):
        self.identity(tenant_id)
        now = int(time.time()) if now is None else now
        state = "delivered" if delivered else ("dead" if item["attempt"] >= 8 else "pending")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE pac_keyway_deliveries
                SET state=?,lease_until=NULL,available_at=?
                WHERE tenant_id=? AND delivery_id=? AND state='leased'
                AND attempts=? AND lease_until=? AND EXISTS
                (SELECT 1 FROM pac_keyway_subscriptions s WHERE
                s.subscription_id=pac_keyway_deliveries.subscription_id
                AND s.tenant_id=pac_keyway_deliveries.tenant_id AND s.enabled=1)""",
                (state,now if delivered else now+min(3600,2**min(item["attempt"],11)),
                 tenant_id,item["delivery_id"],item["attempt"],item["lease_until"])).rowcount
            db.commit()
            return changed == 1


def deliver_one(keyway, tenant_id, signing_secret, sender_factory=SecureWebhookSender, now=None):
    item = keyway.claim(tenant_id, now=now)
    if item is None:
        return None
    headers = signed_headers(item["event_id"],item["payload"],signing_secret,timestamp=now)
    try:
        delivered = sender_factory(item["destination"])(item["payload"],headers) is True
    except Exception:
        delivered = False
    finalized = keyway.finish(tenant_id,item,delivered,now=now)
    return {"delivery_id":item["delivery_id"],"delivered":delivered,"finalized":finalized}
