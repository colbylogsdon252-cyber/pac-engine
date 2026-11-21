import json
import tempfile
import unittest
from pathlib import Path

from pac_webhook_keyway import WebhookKeyway, deliver_one


class KeywayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "keyway.sqlite"
        self.keyway = WebhookKeyway(self.path)
        self.a = self.keyway.provision("tenant_a", "https://example.com/a")
        self.b = self.keyway.provision("tenant_b", "https://example.com/b")

    def test_provision_is_idempotent(self):
        self.assertEqual(self.a, self.keyway.provision("tenant_a", "https://example.com/a"))

    def test_cross_tenant_event_rejected(self):
        payload = json.dumps({"tenant_id":"tenant_a","event_type":"execution.completed"})
        with self.assertRaises(PermissionError):
            self.keyway.enqueue_verified("tenant_a","event1",payload,"tenant_b")
        with self.assertRaises(PermissionError):
            self.keyway.enqueue_verified("tenant_b","event1",payload,"tenant_b")
        self.assertIsNone(self.keyway.claim("tenant_a",now=9999999999))
        self.assertIsNone(self.keyway.claim("tenant_b",now=9999999999))

    def test_legacy_unattributed_event_rejected(self):
        with self.assertRaises(PermissionError):
            self.keyway.enqueue_verified("tenant_a","event2",'{"event_type":"execution.completed"}',"tenant_a")

    def test_delivery_only_to_matching_tenant(self):
        payload = json.dumps({"tenant_id":"tenant_a","event_type":"execution.completed"})
        self.assertEqual(self.keyway.enqueue_verified("tenant_a","event3",payload,"tenant_a"),1)
        self.assertEqual(self.keyway.enqueue_verified("tenant_a","event3",payload,"tenant_a"),1)
        self.assertIsNone(self.keyway.claim("tenant_b",now=9999999999))
        calls = []
        class Sender:
            def __init__(self, destination):
                calls.append(destination)
            def __call__(self, body, headers):
                return True
        result = deliver_one(self.keyway,"tenant_a",b"x"*32,Sender,now=9999999999)
        self.assertTrue(result["delivered"])
        self.assertEqual(calls,["https://example.com/a"])
        self.assertIsNone(self.keyway.claim("tenant_a",now=9999999999))

    def test_revocation_blocks_pending(self):
        payload = json.dumps({"tenant_id":"tenant_a"})
        self.keyway.enqueue_verified("tenant_a","event4",payload,"tenant_a")
        self.assertTrue(self.keyway.revoke("tenant_a",self.a))
        self.assertIsNone(self.keyway.claim("tenant_a",now=9999999999))
        self.assertFalse(self.keyway.revoke("tenant_b",self.a))

    def test_restart_preserves_delivery(self):
        payload = json.dumps({"tenant_id":"tenant_a"})
        self.keyway.enqueue_verified("tenant_a","event5",payload,"tenant_a")
        restarted = WebhookKeyway(self.path)
        item = restarted.claim("tenant_a",now=9999999999)
        self.assertIsNotNone(item)
        self.assertTrue(restarted.finish("tenant_a",item,False,now=9999999999))
        self.assertIsNone(restarted.claim("tenant_a",now=9999999999))


if __name__ == "__main__":
    unittest.main()
