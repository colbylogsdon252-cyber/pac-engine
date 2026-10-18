"""Security and parity tests for the additive public validation API."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from pac_api import app
from pac_contract_validator import validate_canonical


class PublicValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.keyfile = Path(self.temp.name) / "api.key"
        self.secret = "pac-integration-api-test-secret-" + "x" * 32
        self.keyfile.write_text(self.secret)
        self.keyfile.chmod(0o600)
        self.client = TestClient(app)

    def request(self, key=None, payload=None):
        headers = {"Authorization": "Bearer " + key} if key is not None else {}
        return self.client.post("/v1/validations", json=payload or {}, headers=headers)

    def test_missing_key_configuration_fails_closed(self):
        with patch.dict(os.environ, {"PAC_PUBLIC_API_KEY_FILE": ""}):
            self.assertEqual(self.request(self.secret).status_code, 503)

    def test_missing_and_invalid_credentials(self):
        with patch.dict(os.environ, {"PAC_PUBLIC_API_KEY_FILE": str(self.keyfile)}):
            self.assertEqual(self.request().status_code, 401)
            self.assertEqual(self.request("incorrect").status_code, 401)

    def test_authentic_request_preserves_canonical_result(self):
        with patch.dict(os.environ, {"PAC_PUBLIC_API_KEY_FILE": str(self.keyfile)}):
            response = self.request(self.secret)
            expected = dict(validate_canonical({}))
            expected.pop("exit_code", None)
            self.assertEqual(response.json(), expected)
            self.assertNotIn("proof_token", response.json())

    def test_insecure_key_mount_fails_closed(self):
        self.keyfile.chmod(0o644)
        with patch.dict(os.environ, {"PAC_PUBLIC_API_KEY_FILE": str(self.keyfile)}):
            self.assertEqual(self.request(self.secret).status_code, 503)

    def test_symlink_key_mount_fails_closed(self):
        alias = Path(self.temp.name) / "alias.key"
        alias.symlink_to(self.keyfile)
        with patch.dict(os.environ, {"PAC_PUBLIC_API_KEY_FILE": str(alias)}):
            self.assertEqual(self.request(self.secret).status_code, 503)

    def test_no_execution_endpoints(self):
        self.assertEqual(self.client.post("/v1/execution-requests", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
