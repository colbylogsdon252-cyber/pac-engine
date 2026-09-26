from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from pac_proof_token import ProofTokenError, issue_proof_token, verify_execution_authorization


class ProofTokenExecutionBindingTests(unittest.TestCase):
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

    def test_valid_proof_issues_and_authorizes_exact_payload(self):
        token = issue_proof_token(self.payload, self.secret)
        result = verify_execution_authorization(self.payload, token, self.secret)
        self.assertTrue(result["authorized"])
        self.assertEqual(result["reason"], "proof_token_verified")

    def test_invalid_canonical_payload_cannot_issue_token(self):
        payload = dict(self.payload, current_state_id="STATE-B")
        with self.assertRaises(ProofTokenError):
            issue_proof_token(payload, self.secret)

    def test_tampered_token_claims_fail_signature(self):
        token = issue_proof_token(self.payload, self.secret)
        token["claims"]["action"] = False
        result = verify_execution_authorization(self.payload, token, self.secret)
        self.assertEqual(result, {"authorized": False, "reason": "token_signature_invalid"})

    def test_payload_mutation_invalidates_authorization(self):
        token = issue_proof_token(self.payload, self.secret)
        payload = dict(self.payload)
        payload["target"] = {"id": "T-002", "type": "example"}
        result = verify_execution_authorization(payload, token, self.secret)
        self.assertEqual(result, {"authorized": False, "reason": "payload_binding_mismatch"})

    def test_wrong_secret_fails_signature(self):
        token = issue_proof_token(self.payload, self.secret)
        result = verify_execution_authorization(self.payload, token, "different-PAC-secret-material-32-bytes-minimum")
        self.assertEqual(result, {"authorized": False, "reason": "token_signature_invalid"})

    def test_state_mutation_fails_current_canonical_validation(self):
        token = issue_proof_token(self.payload, self.secret)
        payload = dict(self.payload, current_state_id="STATE-B")
        result = verify_execution_authorization(payload, token, self.secret)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "canonical_validation_failed")

    def test_token_cannot_outlive_temporal_proof_window(self):
        token = issue_proof_token(self.payload, self.secret)
        future = token["claims"]["expires_at"] + 1
        with patch("pac_proof_token.time.time", return_value=future):
            result = verify_execution_authorization(self.payload, token, self.secret)
        self.assertEqual(result, {"authorized": False, "reason": "token_expired"})

    def test_short_secret_is_rejected(self):
        with self.assertRaises(ProofTokenError):
            issue_proof_token(self.payload, "too-short")


if __name__ == "__main__":
    unittest.main()
