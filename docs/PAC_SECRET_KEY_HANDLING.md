# PAC Secret and Key Handling Hardening

PAC Proof Token signing keys are deployment secrets. They must not be committed to the repository, embedded in application configuration, logged, returned through APIs, or supplied through command-line arguments.

## Deployment contract

The supported MVP configuration uses two non-secret environment variables:

- `PAC_PROOF_ACTIVE_KEY_ID` identifies the key used for new Proof Tokens.
- `PAC_PROOF_KEYRING_FILE` points to a runtime-mounted JSON secret file.

`PAC_PROOF_KEYRING_JSON` is explicitly rejected because environment variables are routinely exposed through process inspection, diagnostics, crash tooling, and deployment metadata.

The keyring file must be owner-only (no group/other permission bits) and must be supplied by the deployment secret mechanism. PAC reads it; PAC does not provision or persist plaintext signing keys itself.

Example schema (placeholder values only):

```json
{
  "keys": [
    {"key_id": "2026-10-primary", "secret": "<at least 32 bytes>", "revoked": false},
    {"key_id": "2026-09-retiring", "secret": "<at least 32 bytes>", "revoked": false}
  ]
}
```

Do not commit a populated keyring.

## Rotation

Rotation is overlap-based:

1. Mount the new key alongside the current verification key.
2. Change `PAC_PROOF_ACTIVE_KEY_ID` to the new key ID.
3. New tokens are signed with the new key ID.
4. Existing unexpired tokens continue verifying against their bound old key ID.
5. After the old-token validity window has elapsed, remove the retired key unless audit/operational policy requires retaining it outside PAC.

Key IDs are signed claims. Verification selects exactly the bound key; PAC never tries every secret.

## Revocation

Set `revoked: true` for a compromised or administratively invalid key while keeping a different non-revoked key active. Tokens bound to a revoked key fail closed immediately, even if their temporal expiry has not elapsed.

A revoked key cannot be configured as the active signing key. Unknown key IDs also fail closed.

## Storage boundary

The MVP deliberately does not implement a new secret vault or KMS. Production orchestration should mount the keyring from the platform's secret store onto persistent/runtime-protected storage with owner-only permissions. This preserves the current PAC architecture while separating key material from source code and ordinary configuration.

The legacy direct-string signing API remains supported for compatibility and tests, but deployment code should use `ProofKeyring`. Direct-string tokens have no key ID and therefore do not provide managed rotation/revocation semantics.
