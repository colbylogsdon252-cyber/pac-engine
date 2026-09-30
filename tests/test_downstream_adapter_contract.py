from __future__ import annotations

import unittest

from pac_downstream_adapter import (
    AdapterCapabilities,
    AdapterClass,
    evaluate_authoritative_not_found,
)


class DownstreamAdapterContractTests(unittest.TestCase):
    def test_class_a_requires_native_idempotency(self):
        with self.assertRaises(ValueError):
            AdapterCapabilities(AdapterClass.A, False, True, True)

    def test_class_b_requires_authoritative_reconciliation(self):
        with self.assertRaises(ValueError):
            AdapterCapabilities(AdapterClass.B, False, False, False)

    def test_class_c_rejects_authoritative_not_found(self):
        with self.assertRaises(ValueError):
            AdapterCapabilities(AdapterClass.C, False, False, True)

    def test_class_a_authoritative_not_found_can_be_eligible(self):
        caps = AdapterCapabilities(
            AdapterClass.A, True, True, True,
            minimum_observation_seconds=30,
            eventual_consistency_bound_seconds=10,
            original_request_can_complete_late=False,
        )
        decision = evaluate_authoritative_not_found(caps, observation_age_seconds=30)
        self.assertTrue(decision.redispatch_eligible)
        self.assertEqual(decision.reason, "class_a_idempotent_redispatch_eligible")

    def test_class_b_authoritative_not_found_can_be_eligible(self):
        caps = AdapterCapabilities(
            AdapterClass.B, False, True, True,
            minimum_observation_seconds=30,
            eventual_consistency_bound_seconds=10,
            original_request_can_complete_late=False,
        )
        self.assertTrue(
            evaluate_authoritative_not_found(caps, observation_age_seconds=30).redispatch_eligible
        )

    def test_observation_window_blocks_redispatch(self):
        caps = AdapterCapabilities(
            AdapterClass.B, False, True, True,
            minimum_observation_seconds=30,
            original_request_can_complete_late=False,
        )
        decision = evaluate_authoritative_not_found(caps, observation_age_seconds=29)
        self.assertFalse(decision.redispatch_eligible)
        self.assertEqual(decision.reason, "authoritative_observation_window_not_elapsed")

    def test_late_completion_blocks_redispatch(self):
        caps = AdapterCapabilities(
            AdapterClass.B, False, True, True,
            minimum_observation_seconds=0,
            original_request_can_complete_late=True,
        )
        self.assertFalse(
            evaluate_authoritative_not_found(caps, observation_age_seconds=100).redispatch_eligible
        )

    def test_class_c_never_auto_redispatches_not_found(self):
        caps = AdapterCapabilities(AdapterClass.C, False, False, False)
        decision = evaluate_authoritative_not_found(caps, observation_age_seconds=999)
        self.assertFalse(decision.redispatch_eligible)
        self.assertEqual(decision.reason, "class_c_never_auto_redispatches_not_found")


if __name__ == "__main__":
    unittest.main()
