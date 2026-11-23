"""Fail-closed bridge from canonical PAC events to optional tenant keyway.

Only a trusted host may register immutable subject ownership. The host is
responsible for authenticating the tenant and binding subject IDs before use.
This module does not accept tenant IDs from event payloads as authority.
"""
import json
import sqlite3
import time
import uuid

from pac_webhook_keyway import WebhookKeyway


class AuthoritativeEventRouter:
    def __init__(self, pac_database, keyway_database):
        self.pac_database = str(pac_database)
        self.keyway = WebhookKeyway(keyway_database)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pac_subject_tenants (
                subject_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS pac_tenant_event_exports (
                event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                exported_at INTEGER NOT NULL)""")

    def connect(self):
        db = sqlite3.connect(self.pac_database, timeout=15, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def bind_subject(self, tenant_id, subject_id):
        """Trusted host only: immutable ownership, never overwrite."""
        self.keyway.identity(tenant_id)
        if not isinstance(subject_id, str) or not 1 <= len(subject_id) <= 256:
            raise ValueError("Invalid subject identity")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO pac_subject_tenants VALUES (?,?)", (subject_id,tenant_id))
            owner = db.execute("SELECT tenant_id FROM pac_subject_tenants WHERE subject_id=?",
                               (subject_id,)).fetchone()[0]
            if owner != tenant_id:
                db.execute("ROLLBACK")
                raise PermissionError("Subject is bound to another tenant")
            db.commit()

    def route_one(self, tenant_id, event_id):
        """Verify canonical event existence and immutable ownership before export.

        Cross-database delivery is retryable and idempotent, not atomic across DBs.
        """
        self.keyway.identity(tenant_id)
        self.keyway.identity(event_id)
        with self.connect() as db:
            row = db.execute("""SELECT o.event_type,o.subject_id,o.payload,t.tenant_id
                FROM pac_notification_outbox o
                JOIN pac_subject_tenants t ON t.subject_id=o.subject_id
                WHERE o.event_id=?""", (event_id,)).fetchone()
        if row is None or row[3] != tenant_id:
            raise PermissionError("Canonical event ownership unverified")
        event_type, subject_id, _, _ = row
        payload = json.dumps({"tenant_id":tenant_id,"event_type":event_type,
                              "subject_id":subject_id}, sort_keys=True,separators=(",",":"))
        # Keyway checks tenant and deduplicates by subscriber and canonical event ID.
        return self.keyway.enqueue_verified(tenant_id,event_id,payload,tenant_id)
