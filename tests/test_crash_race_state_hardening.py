from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest

from pac_downstream_adapter import AdapterCapabilities, AdapterClass
from pac_external_effect import (
    CONFIRMED,
    ExternalEffectStore,
    ReconciliationEvidence,
    effect_id_for,
    execute_external_effect,
    reconcile_effect,
)
from pac_proof_token import issue_proof_token
from pac_protected_execution import DurableExecutionStore, execution_id_for_token
from pac_redispatch_recovery import (
    RedispatchAuthorizationStore,
    authorize_redispatch,
    recover_external_effect,
)


class HardeningAdapter:
    system_id = "hardening-provider"
    capabilities = AdapterCapabilities(
        AdapterClass.A, True, True, True,
        original_request_can_complete_late=False,
    )

    def __init__(self):
        self.dispatch_calls = 0
        self.effects = {}
        self.malformed_reconcile = False
        self.malformed_dispatch = False

    def dispatch(self, effect_id, operation, payload):
        self.dispatch_calls += 1
        self.effects[effect_id] = payload
        if self.malformed_dispatch:
            return ["not", "a", "dict"]
        return {"downstream_reference": effect_id}

    def reconcile(self, effect_id, downstream_reference=None):
        if self.malformed_reconcile:
            return {"outcome": CONFIRMED}
        if effect_id in self.effects:
            return ReconciliationEvidence(CONFIRMED, downstream_reference=effect_id)
        from pac_external_effect import NOT_FOUND
        return ReconciliationEvidence(NOT_FOUND, authoritative_not_found=True)


class CrashRaceStateHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "pac.sqlite3")
        self.execution = DurableExecutionStore(self.path)
        self.effects = ExternalEffectStore(self.path)
        self.auths = RedispatchAuthorizationStore(self.path)
        self.secret = "PAC-hardening-secret-material-32-bytes-minimum"
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
        self.adapter = HardeningAdapter()
        self.effect_payload = {"amount": 1250}
        self.execution_id = execution_id_for_token(self.token)
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

    def make_indeterminate(self):
        self.execution.claim(self.execution_id)
        self.execution.mark_indeterminate(self.execution_id)
        self.effects.prepare(
            self.effect_id, self.execution_id, self.adapter.system_id,
            "charge", self.effect_payload,
        )
        self.effects.transition(self.effect_id, ("prepared",), "indeterminate")

    def test_claim_and_prepared_effect_are_atomic(self):
        self.assertTrue(self.effects.claim_execution_and_prepare(
            self.execution, self.effect_id, self.execution_id,
            self.adapter.system_id, "charge", self.effect_payload,
        ))
        self.assertEqual(self.execution.state(self.execution_id), "claimed")
        self.assertEqual(self.effects.get(self.effect_id)["state"], "prepared")

    def test_concurrent_initial_execution_dispatches_once(self):
        barrier = threading.Barrier(4)
        results = []
        lock = threading.Lock()
        def worker():
            barrier.wait()
            result = self.execute()
            with lock:
                results.append(result)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertEqual(self.adapter.dispatch_calls, 1)
        self.assertEqual(sum(bool(r.get("executed")) for r in results), 1)

    def test_malformed_dispatch_response_fails_closed(self):
        self.adapter.malformed_dispatch = True
        result = self.execute()
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "dispatch_outcome_indeterminate")
        self.assertEqual(self.effects.get(result["effect_id"])["state"], "indeterminate")
        self.assertEqual(self.execution.state(result["execution_id"]), "indeterminate")

    def test_malformed_reconciliation_evidence_fails_closed(self):
        self.make_indeterminate()
        self.adapter.malformed_reconcile = True
        result = reconcile_effect(self.effect_id, self.adapter, self.effects)
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "invalid_adapter_evidence")
        self.assertEqual(self.effects.get(self.effect_id)["state"], "indeterminate")

    def test_terminal_state_cannot_be_reopened(self):
        self.make_indeterminate()
        self.effects.transition(self.effect_id, ("indeterminate",), "confirmed")
        with self.assertRaises(ValueError):
            self.effects.transition(self.effect_id, ("confirmed",), "dispatching")
        self.assertEqual(self.effects.get(self.effect_id)["state"], "confirmed")

    def test_illegal_state_jump_is_rejected(self):
        self.execution.claim("other-execution")
        other = effect_id_for("other-execution", self.adapter.system_id, "charge", {"x": 1})
        self.effects.prepare(other, "other-execution", self.adapter.system_id, "charge", {"x": 1})
        with self.assertRaises(ValueError):
            self.effects.transition(other, ("prepared",), "confirmed")

    def test_concurrent_recovery_consumes_authority_once(self):
        self.make_indeterminate()
        authority = authorize_redispatch(
            self.effect_id, self.adapter, self.effects, self.auths
        )["authorization"]
        barrier = threading.Barrier(4)
        results = []
        lock = threading.Lock()
        def worker():
            barrier.wait()
            result = recover_external_effect(
                authority, "charge", self.effect_payload, self.adapter,
                self.execution, self.effects, self.auths,
            )
            with lock:
                results.append(result)
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertEqual(self.adapter.dispatch_calls, 1)
        self.assertEqual(sum(bool(r.get("executed")) for r in results), 1)

    def test_recovery_malformed_dispatch_stays_indeterminate(self):
        self.make_indeterminate()
        authority = authorize_redispatch(
            self.effect_id, self.adapter, self.effects, self.auths
        )["authorization"]
        self.adapter.malformed_dispatch = True
        result = recover_external_effect(
            authority, "charge", self.effect_payload, self.adapter,
            self.execution, self.effects, self.auths,
        )
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "redispatch_outcome_indeterminate")
        self.assertEqual(self.effects.get(self.effect_id)["state"], "indeterminate")


if __name__ == "__main__":
    unittest.main()
