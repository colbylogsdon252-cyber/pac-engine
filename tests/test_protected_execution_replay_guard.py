from __future__ import annotations

import time
import unittest

from pac_proof_token import issue_proof_token
from pac_protected_execution import ExecutionReplayStore, execute_protected


class ProtectedExecutionReplayGuardTests(unittest.TestCase):
    def setUp(self):
        self.secret = "PAC-test-secret-material-32-bytes-minimum"
        self.payload = {
            "action": True,
            "target": {"id": "T-001", "type": "example"},
            "proof_timestamp": int(time.time()),
            "current_state": "draft",
            "requested_state": "validated",
            "state_id_at_proof": "STATE-A",
            "current_state_id": "STATE-A",
        }
        self.token = issue_proof_token(self.payload, self.secret)
        self.store = ExecutionReplayStore()
        self.calls = 0

    def action(self):
        self.calls += 1
        return {"calls": self.calls}

    def test_valid_authorization_executes_once(self):
        result = execute_protected(self.payload, self.token, self.secret, self.action, self.store)
        self.assertTrue(result["executed"])
        self.assertEqual(self.calls, 1)

    def test_same_authorization_cannot_execute_twice(self):
        first = execute_protected(self.payload, self.token, self.secret, self.action, self.store)
        second = execute_protected(self.payload, self.token, self.secret, self.action, self.store)
        self.assertTrue(first["executed"])
        self.assertEqual(second["reason"], "authorization_replayed")
        self.assertEqual(self.calls, 1)

    def test_invalid_authorization_never_invokes_action(self):
        token = {"claims": dict(self.token["claims"]), "signature": self.token["signature"]}
        token["claims"]["target"] = {"id": "T-002", "type": "example"}
        result = execute_protected(self.payload, token, self.secret, self.action, self.store)
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "authorization_denied")
        self.assertEqual(self.calls, 0)

    def test_payload_mutation_never_invokes_action(self):
        payload = dict(self.payload, target={"id": "T-002", "type": "example"})
        result = execute_protected(payload, self.token, self.secret, self.action, self.store)
        self.assertFalse(result["executed"])
        self.assertEqual(self.calls, 0)

    def test_action_failure_releases_claim_for_retry(self):
        attempts = {"count": 0}

        def flaky_action():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("controlled failure")
            return "completed"

        with self.assertRaises(RuntimeError):
            execute_protected(self.payload, self.token, self.secret, flaky_action, self.store)

        retry = execute_protected(self.payload, self.token, self.secret, flaky_action, self.store)
        self.assertTrue(retry["executed"])
        self.assertEqual(attempts["count"], 2)

    def test_successful_execution_claim_is_retained(self):
        execute_protected(self.payload, self.token, self.secret, self.action, self.store)
        replay = execute_protected(self.payload, self.token, self.secret, self.action, self.store)
        self.assertFalse(replay["executed"])
        self.assertEqual(replay["reason"], "authorization_replayed")


if __name__ == "__main__":
    unittest.main()
