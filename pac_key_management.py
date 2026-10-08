from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class KeyConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProofKey:
    key_id: str
    secret: str
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not self.key_id.strip():
            raise KeyConfigurationError("key_id must be a non-empty string")
        if not isinstance(self.secret, str) or len(self.secret.encode("utf-8")) < 32:
            raise KeyConfigurationError("proof token secret must be at least 32 bytes")


@dataclass(frozen=True)
class ProofKeyring:
    active_key_id: str
    keys: Mapping[str, ProofKey]

    def __post_init__(self) -> None:
        if self.active_key_id not in self.keys:
            raise KeyConfigurationError("active key_id is not present in keyring")
        for key_id, key in self.keys.items():
            if key_id != key.key_id:
                raise KeyConfigurationError("keyring mapping does not match key_id")
        if self.keys[self.active_key_id].revoked:
            raise KeyConfigurationError("active key must not be revoked")

    def active(self) -> ProofKey:
        return self.keys[self.active_key_id]

    def verification_key(self, key_id: str) -> ProofKey | None:
        key = self.keys.get(key_id)
        if key is None or key.revoked:
            return None
        return key


def load_keyring_from_environment(
    environ: Mapping[str, str] | None = None,
) -> ProofKeyring:
    env = os.environ if environ is None else environ
    active_key_id = env.get("PAC_PROOF_ACTIVE_KEY_ID")
    keyring_file = env.get("PAC_PROOF_KEYRING_FILE")
    inline = env.get("PAC_PROOF_KEYRING_JSON")

    if inline is not None:
        raise KeyConfigurationError(
            "PAC_PROOF_KEYRING_JSON is forbidden; secrets must not be stored in environment variables"
        )
    if not active_key_id or not keyring_file:
        raise KeyConfigurationError(
            "PAC_PROOF_ACTIVE_KEY_ID and PAC_PROOF_KEYRING_FILE are required"
        )

    path = Path(keyring_file)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        if path.is_symlink():
            raise KeyConfigurationError("symlink secret mounts are forbidden")
        fd = os.open(path, flags)
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise KeyConfigurationError("proof keyring must be a regular file")
            if metadata.st_uid != os.geteuid():
                raise KeyConfigurationError("proof keyring must be owned by the runtime user")
            if metadata.st_mode & 0o077:
                raise KeyConfigurationError("proof keyring file permissions must be owner-only")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
                raw = json.load(handle)
        finally:
            os.close(fd)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KeyConfigurationError("proof keyring file is unavailable or invalid") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("keys"), list):
        raise KeyConfigurationError("proof keyring must contain a keys array")

    keys: dict[str, ProofKey] = {}
    for entry in raw["keys"]:
        if not isinstance(entry, dict):
            raise KeyConfigurationError("proof key entry must be an object")
        allowed = {"key_id", "secret", "revoked"}
        if set(entry) - allowed:
            raise KeyConfigurationError("proof key entry contains unsupported fields")
        key = ProofKey(
            entry.get("key_id"),
            entry.get("secret"),
            entry.get("revoked", False),
        )
        if not isinstance(key.revoked, bool):
            raise KeyConfigurationError("revoked must be boolean")
        if key.key_id in keys:
            raise KeyConfigurationError("duplicate proof key_id")
        keys[key.key_id] = key

    return ProofKeyring(active_key_id, keys)
