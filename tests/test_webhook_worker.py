"""Security regression for outbound-only PAC webhook transport."""
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pac_webhook_worker import (
    SecureWebhookSender, configured_worker, read_owner_secret,
    resolve_public_addresses, validate_destination,
)


class WebhookWorkerTests(unittest.TestCase):
    def test_rejects_insecure_destination(self):
        for url in ("http://example.com/hook", "https://localhost/hook",
                    "https://127.0.0.1/hook", "https://example.com:8443/hook",
                    "https://user:pass@example.com/hook", "https://example.com/hook#fragment",
                    "https://example.com\\r\\nHost:evil.test/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_destination(url)

    def test_rejects_mixed_private_dns(self):
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
        ]
        with patch("pac_webhook_worker.socket.getaddrinfo", return_value=answers):
            with self.assertRaises(ValueError):
                resolve_public_addresses("example.com")

    def test_pins_dns_address_without_redirects(self):
        class FakeResponse:
            status = 302
            def read(self, amount):
                return b""
        class FakeConnection:
            def __init__(self, host, ip, timeout):
                self.host, self.ip = host, ip
            def request(self, method, path, body, headers):
                self.requested = (method, path, body, headers)
            def getresponse(self):
                return FakeResponse()
            def close(self):
                pass
        with patch("pac_webhook_worker.resolve_public_addresses", return_value=("8.8.8.8",)):
            with patch("pac_webhook_worker._PinnedHTTPSConnection", FakeConnection):
                self.assertFalse(SecureWebhookSender("https://example.com/hook")("{}", {}))

    def test_signing_secret_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_bytes(b"k" * 32)
            path.chmod(0o600)
            self.assertEqual(read_owner_secret(str(path)), b"k" * 32)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_owner_secret(str(path))
            path.chmod(0o600)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                read_owner_secret(str(link))

    def test_fail_closed_configuration(self):
        with patch.dict(os.environ, {"PAC_NOTIFICATION_DB_FILE": "", "PAC_WEBHOOK_DESTINATION": "",
                                     "PAC_WEBHOOK_SECRET_FILE": ""}):
            with self.assertRaises(ValueError):
                configured_worker()


if __name__ == "__main__":
    unittest.main()
