from __future__ import annotations

import json
import os
import tempfile
import time
import unittest

from pac_key_management import (
    KeyConfigurationError, ProofKey, ProofKeyring, load_keyring_from_environment,
)
from pac_proof_token import issue_proof_token, verify_execution_authorization


class SecretKeyHardeningTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "action": True,
            "target": {"id": "T-001", "type": "example"},
            "proof_timestamp": int(time.time()),
            "current_state": "draft",
            "requested_state": "validated",
            "state_id_at_proof": "STATE-A",
            "current_state_id": "STATE-A",
        }
        self.k1 = ProofKey("k1", "A" * 32)
        self.k2 = ProofKey("k2", "B" * 32)

    def test_token_carries_key_identifier(self):
        ring = ProofKeyring("k1", {"k1": self.k1})
        token = issue_proof_token(self.payload, ring)
        self.assertEqual(token["claims"]["key_id"], "k1")
        self.assertTrue(verify_execution_authorization(self.payload, token, ring)["authorized"])

    def test_rotation_keeps_old_token_verifiable(self):
        old = ProofKeyring("k1", {"k1": self.k1, "k2": self.k2})
        token = issue_proof_token(self.payload, old)
        rotated = ProofKeyring("k2", {"k1": self.k1, "k2": self.k2})
        result = verify_execution_authorization(self.payload, token, rotated)
        self.assertTrue(result["authorized"])
        self.assertEqual(result["key_id"], "k1")

    def test_revocation_blocks_old_token(self):
        token = issue_proof_token(
            self.payload, ProofKeyring("k1", {"k1": self.k1, "k2": self.k2})
        )
        revoked = ProofKey("k1", "A" * 32, revoked=True)
        ring = ProofKeyring("k2", {"k1": revoked, "k2": self.k2})
        result = verify_execution_authorization(self.payload, token, ring)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "token_key_unavailable_or_revoked")

    def test_unknown_key_identifier_fails_closed(self):
        token = issue_proof_token(self.payload, ProofKeyring("k1", {"k1": self.k1}))
        ring = ProofKeyring("k2", {"k2": self.k2})
        result = verify_execution_authorization(self.payload, token, ring)
        self.assertEqual(result["reason"], "token_key_unavailable_or_revoked")

    def test_active_key_cannot_be_revoked(self):
        with self.assertRaises(KeyConfigurationError):
            ProofKeyring("k1", {"k1": ProofKey("k1", "A" * 32, revoked=True)})

    def test_file_loader_requires_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "keys.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"keys": [{"key_id": "k1", "secret": "A" * 32}]}, handle)
            os.chmod(path, 0o644)
            with self.assertRaises(KeyConfigurationError):
                load_keyring_from_environment({
                    "PAC_PROOF_ACTIVE_KEY_ID": "k1",
                    "PAC_PROOF_KEYRING_FILE": path,
                })

    def test_file_loader_accepts_owner_only_secret_mount(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "keys.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"keys": [{"key_id": "k1", "secret": "A" * 32}]}, handle)
            os.chmod(path, 0o600)
            ring = load_keyring_from_environment({
                "PAC_PROOF_ACTIVE_KEY_ID": "k1",
                "PAC_PROOF_KEYRING_FILE": path,
            })
            self.assertEqual(ring.active_key_id, "k1")

    def test_inline_environment_secret_is_forbidden(self):
        with self.assertRaises(KeyConfigurationError):
            load_keyring_from_environment({
                "PAC_PROOF_ACTIVE_KEY_ID": "k1",
                "PAC_PROOF_KEYRING_FILE": "/unused",
                "PAC_PROOF_KEYRING_JSON": "secret",
            })

    def test_duplicate_key_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "keys.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"keys": [
                    {"key_id": "k1", "secret": "A" * 32},
                    {"key_id": "k1", "secret": "B" * 32},
                ]}, handle)
            os.chmod(path, 0o600)
            with self.assertRaises(KeyConfigurationError):
                load_keyring_from_environment({
                    "PAC_PROOF_ACTIVE_KEY_ID": "k1",
                    "PAC_PROOF_KEYRING_FILE": path,
                })


if __name__ == "__main__":
    unittest.main()
