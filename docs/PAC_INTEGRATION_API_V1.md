# PAC Integration API — Increment 1

Status: development increment; not production-certified.

## Scope

`POST /v1/validations` is a new authenticated transport for the **existing canonical validator**. It does not mint Proof Tokens, execute downstream effects, modify protected state, or grant execution authority. Legacy `POST /validate` remains unchanged for backward compatibility; do not expose that legacy route on a public ingress.

## Configuration

Set `PAC_PUBLIC_API_KEY_FILE` to a runtime-mounted file containing at least 32 bytes of random secret material. The file must be a regular file, owned by the effective process user, without group/other permissions, and not a symlink. Do not commit secrets. If the key is missing, invalid, or insecurely mounted, the new endpoint returns HTTP 503. Missing or invalid bearer credentials return HTTP 401.

```bash
curl -X POST http://127.0.0.1:8000/v1/validations \
  -H "Authorization: Bearer <configured-secret>" \
  -H "Content-Type: application/json" \
  --data-binary @test_payload.json
```

A successful response means **canonical validation only**. It is not a Proof Token or authorization to execute. The public route should be deployed only behind TLS, request-size limits, ingress rate limiting, audit logging, and a policy that blocks the unauthenticated legacy validation endpoint. Bearer keys are an initial integration credential; tenant-scoped identity and OAuth are not implemented.

## Roadmap sequencing

1. Versioned authenticated validation transport (this increment).
2. Packaged CLI, typed SDK, and read-only embedding.
3. Durable event outbox and signed outbound webhook notifications.
4. Tenant-scoped identity and downstream execution-request API only after independent authorization and recovery threat modeling.

The original PAC execution enforcement, Proof Token, persistence, and recovery modules remain authoritative and unmodified.
