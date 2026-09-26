from __future__ import annotations

import time
import unittest

from pac_contract_validator import classify_error, load_contract, validate_temporal_validity


class TemporalProofLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract()
        self.now = int(time.time())
        self.base = {
            "proof_timestamp": self.now,
            "state_id_at_proof": "STATE-A",
            "current_state_id": "STATE-A",
        }

    def test_valid_fresh_state_bound_proof(self):
        self.assertEqual(validate_temporal_validity(self.base, self.contract), [])

    def test_state_mutation_invalidates_proof(self):
        payload = dict(self.base, current_state_id="STATE-B")
        errors = validate_temporal_validity(payload, self.contract)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("temporal.proof_invalidated:"))
        classification = classify_error(errors[0])
        self.assertEqual(classification["category"], "temporal")
        self.assertEqual(classification["severity"], "high")

    def test_expired_proof_uses_temporal_classification_path(self):
        max_age = self.contract["temporal"]["max_age_seconds"]
        payload = dict(self.base, proof_timestamp=self.now - max_age - 1)
        errors = validate_temporal_validity(payload, self.contract)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("temporal.proof_expired:"))
        classification = classify_error(errors[0])
        self.assertEqual(classification["category"], "temporal")
        self.assertEqual(classification["severity"], "high")

    def test_missing_state_binding_fails_closed(self):
        payload = dict(self.base)
        payload.pop("state_id_at_proof")
        errors = validate_temporal_validity(payload, self.contract)
        self.assertEqual(errors, ["temporal missing required field: state_id_at_proof"])

    def test_state_binding_types_fail_closed(self):
        payload = dict(self.base, state_id_at_proof=7)
        self.assertEqual(
            validate_temporal_validity(payload, self.contract),
            ["temporal.state_id_at_proof must be string"],
        )


if __name__ == "__main__":
    unittest.main()
