from __future__ import annotations

import multiprocessing
import os
import tempfile
import time
import unittest

from pac_proof_token import issue_proof_token
from pac_protected_execution import DurableExecutionStore, execute_protected, execution_id_for_token


def _claim_in_process(path: str, execution_id: str, queue) -> None:
    queue.put(DurableExecutionStore(path).claim(execution_id))


class DurableExecutionStateTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "pac-execution.sqlite3")
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

    def tearDown(self):
        self.tempdir.cleanup()

    def test_completed_authorization_survives_store_restart(self):
        calls = {"count": 0}
        def action():
            calls["count"] += 1
            return {"done": True}

        first = execute_protected(
            self.payload, self.token, self.secret, action, DurableExecutionStore(self.db_path)
        )
        second = execute_protected(
            self.payload, self.token, self.secret, action, DurableExecutionStore(self.db_path)
        )
        self.assertTrue(first["executed"])
        self.assertFalse(second["executed"])
        self.assertEqual(second["reason"], "authorization_replayed")
        self.assertEqual(second["execution_state"], "completed")
        self.assertEqual(calls["count"], 1)

    def test_crash_after_durable_claim_fails_closed_after_restart(self):
        execution_id = execution_id_for_token(self.token)
        store = DurableExecutionStore(self.db_path)
        self.assertTrue(store.claim(execution_id))

        restarted = DurableExecutionStore(self.db_path)
        calls = {"count": 0}
        def action():
            calls["count"] += 1

        result = execute_protected(self.payload, self.token, self.secret, action, restarted)
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "authorization_replayed")
        self.assertEqual(result["execution_state"], "claimed")
        self.assertEqual(calls["count"], 0)

    def test_completed_state_is_durable(self):
        execution_id = execution_id_for_token(self.token)
        store = DurableExecutionStore(self.db_path)
        self.assertTrue(store.claim(execution_id))
        store.complete(execution_id, {"ok": True})
        self.assertEqual(DurableExecutionStore(self.db_path).state(execution_id), "completed")

    def test_explicit_action_failure_releases_claim_for_retry(self):
        attempts = {"count": 0}
        def action():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("controlled failure")
            return "ok"

        store = DurableExecutionStore(self.db_path)
        with self.assertRaises(RuntimeError):
            execute_protected(self.payload, self.token, self.secret, action, store)

        retry = execute_protected(
            self.payload, self.token, self.secret, action, DurableExecutionStore(self.db_path)
        )
        self.assertTrue(retry["executed"])
        self.assertEqual(attempts["count"], 2)

    def test_atomic_claim_across_processes(self):
        execution_id = execution_id_for_token(self.token)
        queue = multiprocessing.Queue()
        processes = [
            multiprocessing.Process(target=_claim_in_process, args=(self.db_path, execution_id, queue))
            for _ in range(4)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)

        outcomes = [queue.get(timeout=2) for _ in processes]
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 3)

    def test_claimed_state_is_not_automatically_released_on_restart(self):
        execution_id = execution_id_for_token(self.token)
        self.assertTrue(DurableExecutionStore(self.db_path).claim(execution_id))
        self.assertEqual(DurableExecutionStore(self.db_path).state(execution_id), "claimed")
        self.assertFalse(DurableExecutionStore(self.db_path).claim(execution_id))


if __name__ == "__main__":
    unittest.main()
