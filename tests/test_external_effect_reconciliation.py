from __future__ import annotations

import os
import tempfile
import time
import unittest

from pac_external_effect import (
    CONFIRMED,
    NOT_FOUND,
    UNKNOWN,
    ExternalEffectStore,
    ReconciliationEvidence,
    effect_id_for,
    execute_external_effect,
    reconcile_effect,
)
from pac_proof_token import issue_proof_token
from pac_protected_execution import DurableExecutionStore, execution_id_for_token


class FakeAdapter:
    system_id = "fake-payments"
    supports_idempotent_dispatch = True

    def __init__(self):
        self.effects = {}
        self.dispatch_calls = 0
        self.reconcile_outcome = None
        self.raise_after_effect = False

    def dispatch(self, effect_id, operation, payload):
        self.dispatch_calls += 1
        self.effects.setdefault(effect_id, {"operation": operation, "payload": payload})
        if self.raise_after_effect:
            raise TimeoutError("response lost after downstream effect")
        return {"downstream_reference": effect_id}

    def reconcile(self, effect_id, downstream_reference=None):
        if self.reconcile_outcome is not None:
            return self.reconcile_outcome
        if effect_id in self.effects:
            return ReconciliationEvidence(CONFIRMED, downstream_reference=effect_id)
        return ReconciliationEvidence(NOT_FOUND, authoritative_not_found=False)


class ExternalEffectReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tempdir.name, "pac.sqlite3")
        self.execution_store = DurableExecutionStore(self.path)
        self.effect_store = ExternalEffectStore(self.path)
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
        self.adapter = FakeAdapter()
        self.effect_payload = {"amount": 1250, "currency": "USD"}

    def tearDown(self):
        self.tempdir.cleanup()

    def execute(self):
        return execute_external_effect(
            self.payload,
            self.token,
            self.secret,
            "charge",
            self.effect_payload,
            self.adapter,
            self.execution_store,
            self.effect_store,
        )

    def test_confirmed_external_effect_completes_execution(self):
        result = self.execute()
        self.assertTrue(result["executed"])
        self.assertEqual(result["reason"], "external_effect_confirmed")
        self.assertEqual(self.adapter.dispatch_calls, 1)
        self.assertEqual(self.execution_store.state(result["execution_id"]), "completed")
        self.assertEqual(self.effect_store.get(result["effect_id"])["state"], "confirmed")

    def test_confirmed_effect_is_not_dispatched_twice(self):
        first = self.execute()
        second = self.execute()
        self.assertTrue(first["executed"])
        self.assertFalse(second["executed"])
        self.assertEqual(second["reason"], "effect_already_confirmed")
        self.assertEqual(self.adapter.dispatch_calls, 1)

    def test_lost_response_becomes_indeterminate_not_retry(self):
        self.adapter.raise_after_effect = True
        first = self.execute()
        self.assertEqual(first["reason"], "dispatch_outcome_indeterminate")
        second = self.execute()
        self.assertEqual(second["reason"], "reconciliation_required")
        self.assertEqual(self.adapter.dispatch_calls, 1)

    def test_restart_reconciliation_finds_effect_after_lost_response(self):
        self.adapter.raise_after_effect = True
        first = self.execute()
        effect_id = first["effect_id"]
        restarted_store = ExternalEffectStore(self.path)
        evidence = reconcile_effect(effect_id, self.adapter, restarted_store)
        self.assertTrue(evidence["resolved"])
        self.assertEqual(evidence["state"], "confirmed")
        self.assertEqual(self.adapter.dispatch_calls, 1)

    def test_non_authoritative_not_found_remains_fail_closed(self):
        execution_id = execution_id_for_token(self.token)
        effect_id = effect_id_for(
            execution_id, self.adapter.system_id, "charge", self.effect_payload
        )
        self.effect_store.prepare(
            effect_id, execution_id, self.adapter.system_id, "charge", self.effect_payload
        )
        self.effect_store.transition(effect_id, ("prepared",), "dispatching")
        result = reconcile_effect(effect_id, self.adapter, self.effect_store)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["state"], "indeterminate")

    def test_unknown_reconciliation_remains_fail_closed(self):
        self.adapter.reconcile_outcome = ReconciliationEvidence(UNKNOWN, detail="downstream unavailable")
        execution_id = execution_id_for_token(self.token)
        effect_id = effect_id_for(
            execution_id, self.adapter.system_id, "charge", self.effect_payload
        )
        self.effect_store.prepare(
            effect_id, execution_id, self.adapter.system_id, "charge", self.effect_payload
        )
        self.effect_store.transition(effect_id, ("prepared",), "dispatching")
        result = reconcile_effect(effect_id, self.adapter, self.effect_store)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "insufficient_downstream_evidence")

    def test_mutated_effect_payload_has_different_effect_identity(self):
        execution_id = execution_id_for_token(self.token)
        original = effect_id_for(
            execution_id, self.adapter.system_id, "charge", self.effect_payload
        )
        mutated = effect_id_for(
            execution_id,
            self.adapter.system_id,
            "charge",
            {"amount": 9999, "currency": "USD"},
        )
        self.assertNotEqual(original, mutated)

    def test_invalid_authorization_never_dispatches(self):
        mutated_payload = dict(self.payload, target={"id": "T-002", "type": "example"})
        result = execute_external_effect(
            mutated_payload,
            self.token,
            self.secret,
            "charge",
            self.effect_payload,
            self.adapter,
            self.execution_store,
            self.effect_store,
        )
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "authorization_denied")
        self.assertEqual(self.adapter.dispatch_calls, 0)


if __name__ == "__main__":
    unittest.main()
