import json
import os
import tempfile
import unittest
from pathlib import Path

from pac_api import validate_startup_configuration
from pac_key_management import KeyConfigurationError, load_keyring_from_environment


class DeploymentStartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "keys.json"
        self.path.write_text(json.dumps({"keys": [{"key_id": "current", "secret": "x" * 32}]}))
        self.path.chmod(0o600)
        self.env = {"PAC_DEPLOYMENT_MODE": "production",
                    "PAC_PROOF_ACTIVE_KEY_ID": "current",
                    "PAC_PROOF_KEYRING_FILE": str(self.path)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_production_accepts_valid_mount(self):
        self.assertEqual(validate_startup_configuration(self.env).active_key_id, "current")

    def test_missing_mode_fails_closed(self):
        with self.assertRaises(RuntimeError):
            validate_startup_configuration({})

    def test_explicit_test_mode_does_not_require_production_secret(self):
        self.assertIsNone(validate_startup_configuration({"PAC_DEPLOYMENT_MODE": "test"}))

    def test_missing_mount_fails_closed(self):
        with self.assertRaises(KeyConfigurationError):
            validate_startup_configuration({"PAC_DEPLOYMENT_MODE": "production"})

    def test_wrong_active_key_fails_closed(self):
        with self.assertRaises(KeyConfigurationError):
            validate_startup_configuration({**self.env, "PAC_PROOF_ACTIVE_KEY_ID": "missing"})

    def test_world_readable_mount_fails_closed(self):
        self.path.chmod(0o644)
        with self.assertRaises(KeyConfigurationError):
            validate_startup_configuration(self.env)

    def test_symlink_mount_fails_closed(self):
        alias = Path(self.tmp.name) / "alias.json"
        alias.symlink_to(self.path)
        with self.assertRaises(KeyConfigurationError):
            validate_startup_configuration({**self.env, "PAC_PROOF_KEYRING_FILE": str(alias)})

    def test_directory_mount_fails_closed(self):
        with self.assertRaises(KeyConfigurationError):
            validate_startup_configuration({**self.env, "PAC_PROOF_KEYRING_FILE": self.tmp.name})

    def test_revoked_active_key_fails_closed(self):
        self.path.write_text(json.dumps({"keys": [{"key_id": "current", "secret": "x" * 32, "revoked": True}]}))
        with self.assertRaises(KeyConfigurationError):
            validate_startup_configuration(self.env)

    def test_empty_inline_secret_environment_is_rejected(self):
        with self.assertRaises(KeyConfigurationError):
            load_keyring_from_environment({**self.env, "PAC_PROOF_KEYRING_JSON": ""})


if __name__ == "__main__":
    unittest.main()
