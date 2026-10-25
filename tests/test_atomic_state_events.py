"""Atomic state/event commit and rollback verification."""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pac_external_effect import ExternalEffectStore
from pac_notification_outbox import NotificationOutbox
from pac_protected_execution import DurableExecutionStore


class AtomicEventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "pac.sqlite")
        self.executions = DurableExecutionStore(self.path)
        self.effects = ExternalEffectStore(self.path)
        self.outbox = NotificationOutbox(self.path)

    def events(self, event_type):
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT subject_id FROM pac_notification_outbox WHERE event_type=?",
                              (event_type,)).fetchall()

    def test_complete_and_restart_atomic(self):
        self.assertTrue(self.executions.claim("x1"))
        self.executions.complete("x1", {"ok": True})
        self.assertEqual(self.events("execution.completed"), [("x1",)])
        self.assertEqual(DurableExecutionStore(self.path).state("x1"), "completed")

    def test_indeterminate_and_idempotency(self):
        self.assertTrue(self.executions.claim("x2"))
        self.executions.mark_indeterminate("x2")
        self.executions.mark_indeterminate("x2")
        self.assertEqual(self.events("execution.indeterminate"), [("x2",)])

    def test_effect_transition_atomic(self):
        self.effects.prepare("effect1", "execution1", "system", "operation", {})
        self.assertTrue(self.effects.transition("effect1", ("prepared",), "indeterminate"))
        self.assertEqual(self.events("effect.indeterminate"), [("effect1",)])

    def test_failed_event_insert_rolls_back_execution(self):
        self.assertTrue(self.executions.claim("x3"))
        with patch("pac_protected_execution.enqueue_atomic", side_effect=sqlite3.OperationalError("disk failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.executions.mark_indeterminate("x3")
        self.assertEqual(self.executions.state("x3"), "claimed")
        self.assertEqual(self.events("execution.indeterminate"), [])

    def test_failed_event_insert_rolls_back_effect(self):
        self.effects.prepare("effect2", "execution2", "system", "operation", {})
        with patch("pac_external_effect.enqueue_atomic", side_effect=sqlite3.OperationalError("disk failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.effects.transition("effect2", ("prepared",), "indeterminate")
        self.assertEqual(self.effects.get("effect2")["state"], "prepared")
        self.assertEqual(self.events("effect.indeterminate"), [])

    def test_existing_outbox_worker_can_claim_atomic_event(self):
        self.assertTrue(self.executions.claim("x4"))
        self.executions.mark_indeterminate("x4")
        event = self.outbox.claim(now=9999999999)
        self.assertEqual(event["payload"].count("execution.indeterminate"), 1)


if __name__ == "__main__":
    unittest.main()
