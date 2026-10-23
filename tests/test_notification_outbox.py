import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path

from pac_notification_outbox import NotificationOutbox, dispatch_one, signed_headers


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite"
        self.store = NotificationOutbox(self.path)
        self.secret = b"x" * 32

    def test_dedup_and_restart(self):
        first = self.store.enqueue("execution.indeterminate", "execution-1", {"state": "indeterminate"})
        self.assertEqual(first, self.store.enqueue("execution.indeterminate", "execution-1"))
        self.assertEqual(NotificationOutbox(self.path).claim(now=9999999999)["event_id"], first)

    def test_success_and_signature(self):
        event = self.store.enqueue("effect.indeterminate", "effect-1")
        sent = []
        def sender(payload, headers):
            sent.append((payload, headers))
            return True
        result = dispatch_one(self.store, sender, self.secret, now=9999999999)
        self.assertTrue(result["delivered"])
        self.assertEqual(self.store.status(event)["state"], "delivered")
        self.assertEqual(len(sent), 1)
        payload, headers = sent[0]
        self.assertEqual(json.loads(payload)["subject_id"], "effect-1")
        self.assertEqual(headers, signed_headers(event, payload, self.secret, 9999999999))
        self.assertIsNone(dispatch_one(self.store, sender, self.secret, now=9999999999))

    def test_failure_retries_without_reexecution(self):
        event = self.store.enqueue("execution.completed", "execution-2")
        result = dispatch_one(self.store, lambda *_: False, self.secret, now=9999999999)
        self.assertFalse(result["delivered"])
        self.assertEqual(self.store.status(event)["state"], "pending")
        self.assertIsNone(self.store.claim(now=9999999999))
        self.assertIsNotNone(self.store.claim(now=9999999999 + 2))

    def test_expired_lease_and_stale_ack(self):
        event = self.store.enqueue("effect.indeterminate", "effect-3")
        old = self.store.claim(now=9999999999, lease_seconds=3)
        new = NotificationOutbox(self.path).claim(now=9999999999 + 4)
        self.assertEqual(old["event_id"], new["event_id"])
        self.assertFalse(self.store.finish(old, True, now=9999999999 + 4))
        self.assertTrue(self.store.finish(new, True, now=9999999999 + 4))
        self.assertEqual(self.store.status(event)["state"], "delivered")

    def test_redaction_rejects_sensitive_metadata(self):
        with self.assertRaises(ValueError):
            self.store.enqueue("execution.indeterminate", "x", {"proof_token": "secret"})
        with self.assertRaises(ValueError):
            self.store.enqueue("execution.authorized", "x")

    def test_short_signing_key_rejected(self):
        with self.assertRaises(ValueError):
            signed_headers("id", "{}", b"short")


if __name__ == "__main__":
    unittest.main()
