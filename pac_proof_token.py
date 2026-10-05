from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from pac_key_management import ProofKeyring

from pac_contract_validator import load_contract, validate_canonical


TOKEN_VERSION = "pac-proof-token-v1"


class ProofTokenError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _payload_digest(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _require_secret(secret: str) -> bytes:
    if not isinstance(secret, str) or len(secret.encode("utf-8")) < 32:
        raise ProofTokenError("proof token secret must be at least 32 bytes")
    return secret.encode("utf-8")


def _sign_claims(claims: dict, secret: str) -> str:
    return hmac.new(_require_secret(secret), _canonical_json(claims), hashlib.sha256).hexdigest()


def issue_proof_token(payload: dict, secret: str | ProofKeyring) -> dict:
    result = validate_canonical(payload)
    if not result.get("valid", False):
        raise ProofTokenError("canonical PAC validation did not authorize proof token issuance")

    contract = load_contract()
    temporal = contract.get("temporal", {})
    max_age_seconds = temporal.get("max_age_seconds")
    if not isinstance(max_age_seconds, int):
        raise ProofTokenError("temporal max_age_seconds is not enforceable")

    proof_timestamp = payload.get(temporal.get("timestamp_field", "proof_timestamp"))
    state_id_at_proof = payload.get(temporal.get("state_id_at_proof_field", "state_id_at_proof"))
    current_state_id = payload.get(temporal.get("current_state_id_field", "current_state_id"))

    key_id = secret.active_key_id if isinstance(secret, ProofKeyring) else None
    signing_secret = secret.active().secret if isinstance(secret, ProofKeyring) else secret

    claims = {
        "version": TOKEN_VERSION,
        "key_id": key_id,
        "payload_sha256": _payload_digest(payload),
        "proof_timestamp": proof_timestamp,
        "expires_at": proof_timestamp + max_age_seconds,
        "state_id_at_proof": state_id_at_proof,
        "current_state_id": current_state_id,
        "action": payload.get("action"),
        "target": payload.get("target"),
    }
    return {"claims": claims, "signature": _sign_claims(claims, signing_secret)}


def verify_execution_authorization(payload: dict, token: dict, secret: str | ProofKeyring) -> dict:
    result = validate_canonical(payload)
    if not result.get("valid", False):
        return {"authorized": False, "reason": "canonical_validation_failed", "validation": result}

    if not isinstance(token, dict):
        return {"authorized": False, "reason": "token_malformed"}

    claims = token.get("claims")
    signature = token.get("signature")
    if not isinstance(claims, dict) or not isinstance(signature, str):
        return {"authorized": False, "reason": "token_malformed"}

    try:
        if isinstance(secret, ProofKeyring):
            key_id = claims.get("key_id")
            if not isinstance(key_id, str):
                return {"authorized": False, "reason": "token_key_id_missing"}
            verification_key = secret.verification_key(key_id)
            if verification_key is None:
                return {"authorized": False, "reason": "token_key_unavailable_or_revoked"}
            signing_secret = verification_key.secret
        else:
            signing_secret = secret
        expected_signature = _sign_claims(claims, signing_secret)
    except ProofTokenError:
        return {"authorized": False, "reason": "token_secret_invalid"}

    if not hmac.compare_digest(signature, expected_signature):
        return {"authorized": False, "reason": "token_signature_invalid"}

    if claims.get("version") != TOKEN_VERSION:
        return {"authorized": False, "reason": "token_version_invalid"}

    expires_at = claims.get("expires_at")
    if not isinstance(expires_at, int):
        return {"authorized": False, "reason": "token_expiry_invalid"}

    if int(time.time()) > expires_at:
        return {"authorized": False, "reason": "token_expired"}

    if claims.get("payload_sha256") != _payload_digest(payload):
        return {"authorized": False, "reason": "payload_binding_mismatch"}

    expected_bindings = {
        "proof_timestamp": payload.get("proof_timestamp"),
        "state_id_at_proof": payload.get("state_id_at_proof"),
        "current_state_id": payload.get("current_state_id"),
        "action": payload.get("action"),
        "target": payload.get("target"),
    }
    for field, expected in expected_bindings.items():
        if claims.get(field) != expected:
            return {"authorized": False, "reason": "claim_binding_mismatch", "field": field}

    return {
        "authorized": True,
        "reason": "proof_token_verified",
        "payload_sha256": claims["payload_sha256"],
        "expires_at": expires_at,
        "key_id": claims.get("key_id"),
    }
