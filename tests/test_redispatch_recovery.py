from __future__ import annotations

import os
import tempfile
import time
import unittest

from pac_downstream_adapter import AdapterCapabilities, AdapterClass
from pac_external_effect import (
    CONFIRMED,
    NOT_FOUND,
    ExternalEffectStore,
    ReconciliationEvidence,
    effect_id_for,
)
from pac_proof_token import issue_proof_token
from pac_protected_execution import DurableExecutionStore, execution_id_for_token
from pac_redispatch_recovery import (
    RedispatchAuthorizationStore,
    authorize_redispatch,
    recover_external_effect,
)


class RecoveryAdapter:
    system_id = "recoverable-provider"

    def __init__(self, adapter_class=AdapterClass.A):
        if adapter_class is AdapterClass.A:
            self.capabilities = AdapterCapabilities(
                AdapterClass.A, True, True, True,
                original_request_can_complete_late=False,
            )
        elif adapter_class is AdapterClass.B:
            self.capabilities = AdapterCapabilities(
                AdapterClass.B, False, True, True,
                original_request_can_complete_late=False,
            )
        else:
            self.capabilities = AdapterCapabilities(AdapterClass.C, False, False, False)
        self.exists = False
        self.dispatch_calls = 0

    def dispatch(self, effect_id, operation, payload):
        self.dispatch_calls += 1
        self.exists = True
        return {"downstream_reference": effect_id}

    def reconcile(self, effect_id, downstream_reference=None):
        if self.exists:
            return ReconciliationEvidence(CONFIRMED, downstream_reference=effect_id)
        return ReconciliationEvidence(
            NOT_FOUND,
            authoritative_not_found=self.capabilities.authoritative_not_found,
        )


class RedispatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tempdir.name, "pac.sqlite3")
        self.execution_store = DurableExecutionStore(self.path)
        self.effect_store = ExternalEffectStore(self.path)
        self.auth_store = RedispatchAuthorizationStore(self.path)
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
        self.execution_id = execution_id_for_token(self.token)
        self.effect_payload = {"amount": 1250}
        self.adapter = RecoveryAdapter()
        self.effect_id = effect_id_for(
            self.execution_id, self.adapter.system_id, "charge", self.effect_payload
        )
        self.execution_store.claim(self.execution_id)
        self.execution_store.mark_indeterminate(self.execution_id)
        self.effect_store.prepare(
            self.effect_id, self.execution_id, self.adapter.system_id,
            "charge", self.effect_payload,
        )
        self.effect_store.transition(self.effect_id, ("prepared",), "indeterminate")

    def tearDown(self):
        self.tempdir.cleanup()

    def authorize(self, adapter=None):
        return authorize_redispatch(
            self.effect_id,
            adapter or self.adapter,
            self.effect_store,
            self.auth_store,
        )

    def test_class_a_proven_not_found_creates_durable_authority(self):
        result = self.authorize()
        self.assertTrue(result["authorized"])
        restarted = RedispatchAuthorizationStore(self.path)
        self.assertTrue(restarted.consume(result["authorization"]))
        self.assertFalse(restarted.consume(result["authorization"]))

    def test_recovery_consumes_authority_and_confirms_once(self):
        authority = self.authorize()["authorization"]
        result = recover_external_effect(
            authority, "charge", self.effect_payload, self.adapter,
            self.execution_store, self.effect_store, self.auth_store,
        )
        self.assertTrue(result["executed"])
        self.assertEqual(self.adapter.dispatch_calls, 1)
        self.assertEqual(self.effect_store.get(self.effect_id)["state"], "confirmed")
        self.assertEqual(self.execution_store.state(self.execution_id), "completed")
        again = recover_external_effect(
            authority, "charge", self.effect_payload, self.adapter,
            self.execution_store, self.effect_store, self.auth_store,
        )
        self.assertFalse(again["executed"])
        self.assertEqual(self.adapter.dispatch_calls, 1)

    def test_class_b_authoritative_absence_can_authorize(self):
        adapter = RecoveryAdapter(AdapterClass.B)
        result = self.authorize(adapter)
        self.assertTrue(result["authorized"])

    def test_class_c_cannot_authorize_redispatch(self):
        adapter = RecoveryAdapter(AdapterClass.C)
        result = self.authorize(adapter)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "class_c_redispatch_forbidden")

    def test_mutated_effect_payload_cannot_use_authority(self):
        authority = self.authorize()["authorization"]
        result = recover_external_effect(
            authority, "charge", {"amount": 9999}, self.adapter,
            self.execution_store, self.effect_store, self.auth_store,
        )
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "effect_binding_mismatch")
        self.assertEqual(self.adapter.dispatch_calls, 0)

    def test_redispatch_exception_returns_to_indeterminate(self):
        class FailingAdapter(RecoveryAdapter):
            def dispatch(self, effect_id, operation, payload):
                self.dispatch_calls += 1
                raise TimeoutError("ambiguous")

        adapter = FailingAdapter()
        authority = self.authorize(adapter)["authorization"]
        result = recover_external_effect(
            authority, "charge", self.effect_payload, adapter,
            self.execution_store, self.effect_store, self.auth_store,
        )
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "redispatch_outcome_indeterminate")
        self.assertEqual(self.effect_store.get(self.effect_id)["state"], "indeterminate")


if __name__ == "__main__":
    unittest.main()
