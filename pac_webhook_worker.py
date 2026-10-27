"""Fixed-destination HTTPS webhook sender with DNS-pinned TLS and no redirects.

Outbound notifications only. Never imports execution or Proof Token modules.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import stat
import time
from pathlib import Path
from urllib.parse import urlsplit

from pac_notification_outbox import NotificationOutbox, dispatch_one


def read_owner_secret(path: str) -> bytes:
    if not path:
        raise ValueError("Signing key file is required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise ValueError("Signing key must be an owner-only regular file")
        if not 32 <= st.st_size <= 4096:
            raise ValueError("Invalid signing key length")
        secret = os.read(fd, 4097)
        if not 32 <= len(secret) <= 4096:
            raise ValueError("Invalid signing key length")
        return secret
    finally:
        os.close(fd)


def validate_destination(url: str) -> tuple[str, str, int]:
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ValueError("Invalid destination")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError("Webhook destination must be HTTPS on port 443 without credentials")
    host = parsed.hostname
    if not host.isascii() or host.endswith(".") or not all(
        label and len(label) <= 63 and label.replace("-", "").isalnum() and not label.startswith("-") and not label.endswith("-")
        for label in host.split(".")
    ):
        raise ValueError("Invalid DNS hostname")
    if host.lower() in ("localhost",) or "." not in host:
        raise ValueError("Public DNS hostname required")
    return host, (parsed.path or "/") + (("?" + parsed.query) if parsed.query else ""), 443


def resolve_public_addresses(host: str) -> tuple[str, ...]:
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(
        host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Webhook DNS must resolve exclusively to public addresses")
    return tuple(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, timeout: float):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


class SecureWebhookSender:
    def __init__(self, destination: str, *, timeout: float = 5.0):
        self.host, self.path, _ = validate_destination(destination)
        if not 0 < timeout <= 30:
            raise ValueError("Invalid transport timeout")
        self.timeout = timeout

    def __call__(self, payload: str, headers: dict[str, str]) -> bool:
        addresses = resolve_public_addresses(self.host)
        connection = _PinnedHTTPSConnection(self.host, addresses[0], self.timeout)
        try:
            connection.request("POST", self.path, body=payload.encode("utf-8"), headers={
                **headers, "Host": self.host, "User-Agent": "PAC-Notification/1",
            })
            response = connection.getresponse()
            response.read(4096)
            # Redirects are not followed. Any non-2xx response is a failed delivery.
            return 200 <= response.status < 300
        finally:
            connection.close()


def configured_worker():
    database = os.environ.get("PAC_NOTIFICATION_DB_FILE")
    destination = os.environ.get("PAC_WEBHOOK_DESTINATION")
    key_path = os.environ.get("PAC_WEBHOOK_SECRET_FILE")
    if not database or not destination or not key_path:
        raise ValueError("Webhook worker configuration incomplete")
    secret = read_owner_secret(key_path)
    sender = SecureWebhookSender(destination)
    return NotificationOutbox(database), sender, secret


def main():
    # Explicit worker process; no hidden background thread in the PAC API.
    outbox, sender, secret = configured_worker()
    interval = float(os.environ.get("PAC_WEBHOOK_POLL_SECONDS", "2"))
    if not 0.1 <= interval <= 60:
        raise ValueError("Invalid poll interval")
    while True:
        result = dispatch_one(outbox, sender, secret)
        if result is None:
            time.sleep(interval)


if __name__ == "__main__":
    main()
