from __future__ import annotations

import os
import tempfile
import time
import unittest

from pac_downstream_adapter import AdapterCapabilities, AdapterClass
from pac_external_effect import (
    CONFIRMED, ExternalEffectStore, ReconciliationEvidence,
    effect_id_for, execute_external_effect,
)
from pac_proof_token import issue_proof_token
from pac_protected_execution import DurableExecutionStore, execution_id_for_token
from pac_redispatch_recovery import RedispatchAuthorizationStore


class ConfirmingAdapter:
    system_id = "boundary-provider"
    capabilities = AdapterCapabilities(
        AdapterClass.A, True, True, True,
        original_request_can_complete_late=False,
    )
    def __init__(self):
        self.calls = 0
    def dispatch(self, effect_id, operation, payload):
        self.calls += 1
        return {"downstream_reference": effect_id}
    def reconcile(self, effect_id, downstream_reference=None):
        return ReconciliationEvidence(CONFIRMED, downstream_reference=effect_id)


class AdversarialBoundaryHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "pac.sqlite3")
        self.execution = DurableExecutionStore(self.path)
        self.effects = ExternalEffectStore(self.path)
        self.secret = "PAC-adversarial-secret-material-32-bytes-minimum"
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
        self.execution_id = execution_id_for_token(self.token)
        self.adapter = ConfirmingAdapter()
        self.effect_payload = {"amount": 1250}
        self.effect_id = effect_id_for(
            self.execution_id, self.adapter.system_id, "charge", self.effect_payload
        )

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self):
        return execute_external_effect(
            self.payload, self.token, self.secret, "charge", self.effect_payload,
            self.adapter, self.execution, self.effects,
        )

    def test_crash_after_atomic_prepare_resumes_without_second_execution_claim(self):
        self.assertTrue(self.effects.claim_execution_and_prepare(
            self.execution, self.effect_id, self.execution_id,
            self.adapter.system_id, "charge", self.effect_payload,
        ))
        result = self.execute()
        self.assertTrue(result["executed"])
        self.assertEqual(self.adapter.calls, 1)
        self.assertEqual(self.effects.get(self.effect_id)["attempt_count"], 1)
        self.assertEqual(self.execution.state(self.execution_id), "completed")

    def test_confirmed_effect_repairs_indeterminate_execution_without_dispatch(self):
        self.execution.claim(self.execution_id)
        self.execution.mark_indeterminate(self.execution_id)
        self.effects.prepare(
            self.effect_id, self.execution_id, self.adapter.system_id,
            "charge", self.effect_payload,
        )
        self.effects.transition(self.effect_id, ("prepared",), "dispatching")
        self.effects.transition(
            self.effect_id, ("dispatching",), "confirmed",
            downstream_reference=self.effect_id,
        )
        result = self.execute()
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "effect_already_confirmed")
        self.assertTrue(result["execution_recovered"])
        self.assertEqual(self.adapter.calls, 0)
        self.assertEqual(self.execution.state(self.execution_id), "completed")

    def test_prepared_effect_with_corrupt_execution_state_fails_closed(self):
        self.effects.prepare(
            self.effect_id, self.execution_id, self.adapter.system_id,
            "charge", self.effect_payload,
        )
        result = self.execute()
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "prepared_effect_execution_state_mismatch")
        self.assertEqual(self.adapter.calls, 0)

    def test_relative_and_absolute_store_paths_are_same_database(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.tmp.name)
            auths = RedispatchAuthorizationStore("pac.sqlite3")
            effects = ExternalEffectStore(os.path.abspath("pac.sqlite3"))
            # path identity validation must not reject equivalent filesystem paths
            self.assertEqual(os.path.realpath(auths.path), os.path.realpath(effects.path))
        finally:
            os.chdir(cwd)

    def test_terminal_effect_rejects_corrupt_reopen(self):
        self.execution.claim(self.execution_id)
        self.effects.prepare(
            self.effect_id, self.execution_id, self.adapter.system_id,
            "charge", self.effect_payload,
        )
        self.effects.transition(self.effect_id, ("prepared",), "dispatching")
        self.effects.transition(self.effect_id, ("dispatching",), "confirmed")
        with self.assertRaises(ValueError):
            self.effects.transition(self.effect_id, ("confirmed",), "indeterminate")


if __name__ == "__main__":
    unittest.main()
