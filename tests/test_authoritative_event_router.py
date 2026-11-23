import os
import sqlite3
import tempfile
import unittest

from pac_authoritative_event_router import AuthoritativeEventRouter
from pac_protected_execution import DurableExecutionStore


class AuthoritativeRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "pac.sqlite")
        self.router = AuthoritativeEventRouter(self.db, os.path.join(self.temp.name,"keyway.sqlite"))
        self.execution = DurableExecutionStore(self.db)
        self.router.keyway.provision("tenant_a","https://example.com/a")
        self.router.keyway.provision("tenant_b","https://example.com/b")

    def canonical_event(self, subject):
        with sqlite3.connect(self.db) as db:
            return db.execute("SELECT event_id FROM pac_notification_outbox WHERE subject_id=?",
                              (subject,)).fetchone()[0]

    def test_bound_canonical_event_routes_only_to_owner(self):
        self.router.bind_subject("tenant_a","execution_a")
        self.assertTrue(self.execution.claim("execution_a"))
        self.execution.complete("execution_a",{"ok":True})
        event_id = self.canonical_event("execution_a")
        self.assertEqual(self.router.route_one("tenant_a",event_id),1)
        self.assertEqual(self.router.route_one("tenant_a",event_id),1)
        self.assertIsNotNone(self.router.keyway.claim("tenant_a",now=9999999999))
        self.assertIsNone(self.router.keyway.claim("tenant_b",now=9999999999))
        with self.assertRaises(PermissionError):
            self.router.route_one("tenant_b",event_id)

    def test_binding_cannot_be_overwritten(self):
        self.router.bind_subject("tenant_a","execution_a")
        with self.assertRaises(PermissionError):
            self.router.bind_subject("tenant_b","execution_a")

    def test_existing_unattributed_event_cannot_be_claimed(self):
        self.execution.claim("legacy")
        self.execution.mark_indeterminate("legacy")
        with self.assertRaises(PermissionError):
            self.router.bind_subject("tenant_a","legacy")
        with self.assertRaises(PermissionError):
            self.router.route_one("tenant_a",self.canonical_event("legacy"))

    def test_restart_idempotent_export(self):
        self.router.bind_subject("tenant_a","execution_a")
        self.execution.claim("execution_a")
        self.execution.mark_indeterminate("execution_a")
        event_id = self.canonical_event("execution_a")
        self.router.route_one("tenant_a",event_id)
        restarted = AuthoritativeEventRouter(self.db,os.path.join(self.temp.name,"keyway.sqlite"))
        self.assertEqual(restarted.route_one("tenant_a",event_id),1)
        with restarted.keyway.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM pac_keyway_deliveries").fetchone()[0],1)


if __name__ == "__main__":
    unittest.main()
