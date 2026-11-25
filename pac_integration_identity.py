"""Optional local integration authority. No protected execution authority."""
import hashlib
import hmac
import secrets
import uuid

from pac_webhook_keyway import WebhookKeyway
from pac_webhook_worker import validate_destination


class IntegrationIdentity:
    """Owner initializes locally; clients receive a tenant-bound enrollment token."""

    def __init__(self, keyway):
        self.keyway = keyway
        with keyway.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pac_integration_identity (
                tenant_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, enabled INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS pac_subscriber_credentials (
                subscription_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                key_id TEXT NOT NULL, secret BLOB NOT NULL)""")

    def issue_tenant(self, tenant_id):
        """Owner-only local operation; never expose as a client endpoint."""
        self.keyway.identity(tenant_id)
        token = secrets.token_urlsafe(32)
        with self.keyway.connect() as db:
            db.execute("INSERT INTO pac_integration_identity VALUES (?,?,1)",
                       (tenant_id, hashlib.sha256(token.encode()).hexdigest()))
        return token

    def authenticate(self, db, tenant_id, token):
        self.keyway.identity(tenant_id)
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            raise PermissionError("Invalid enrollment credential")
        row = db.execute("SELECT token_hash FROM pac_integration_identity WHERE tenant_id=? AND enabled=1",
                         (tenant_id,)).fetchone()
        if not row or not hmac.compare_digest(row[0], hashlib.sha256(token.encode()).hexdigest()):
            raise PermissionError("Invalid enrollment credential")

    def enroll(self, tenant_id, token, destination):
        validate_destination(destination)
        with self.keyway.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authenticate(db, tenant_id, token)
            subscriber = str(uuid.uuid4())
            key_id = str(uuid.uuid4())
            secret = secrets.token_bytes(32)
            db.execute("INSERT INTO pac_keyway_subscriptions VALUES (?,?,?,1)",
                       (subscriber, tenant_id, destination))
            db.execute("INSERT INTO pac_subscriber_credentials VALUES (?,?,?,?)",
                       (subscriber, tenant_id, key_id, secret))
            db.commit()
        return subscriber, key_id, secret

    def rotate(self, tenant_id, token, subscriber):
        with self.keyway.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authenticate(db, tenant_id, token)
            key_id, secret = str(uuid.uuid4()), secrets.token_bytes(32)
            changed = db.execute("""UPDATE pac_subscriber_credentials SET key_id=?,secret=?
                WHERE subscription_id=? AND tenant_id=? AND EXISTS
                (SELECT 1 FROM pac_keyway_subscriptions s WHERE s.subscription_id=?
                AND s.tenant_id=? AND s.enabled=1)""",
                (key_id,secret,subscriber,tenant_id,subscriber,tenant_id)).rowcount
            if changed != 1:
                raise PermissionError("Subscriber unavailable")
            db.commit()
        return key_id, secret

    def revoke(self, tenant_id, token, subscriber):
        with self.keyway.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.authenticate(db, tenant_id, token)
            changed = db.execute("UPDATE pac_keyway_subscriptions SET enabled=0 WHERE subscription_id=? AND tenant_id=? AND enabled=1",
                                 (subscriber,tenant_id)).rowcount
            if changed != 1:
                raise PermissionError("Subscriber unavailable")
            db.execute("DELETE FROM pac_subscriber_credentials WHERE subscription_id=? AND tenant_id=?", (subscriber,tenant_id))
            db.execute("UPDATE pac_keyway_deliveries SET state='dead' WHERE subscription_id=? AND tenant_id=? AND state IN ('pending','leased')",
                       (subscriber,tenant_id))
            db.commit()
