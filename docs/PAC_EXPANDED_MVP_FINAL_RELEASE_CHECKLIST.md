# PAC Expanded MVP — Final Deployment and Release Checklist

**Status:** development, not production-certified. This is the preserved release scope boundary for increments 1–5.

## Included in expanded source

- [x] Existing canonical validation, Proof Token handling, protected execution, durable execution state, external effect reconciliation, and redispatch authority remain the enforcement foundation.
- [x] Authenticated `POST /v1/validations` is **validation-only**; a valid result does not grant execution authority.
- [x] Installable Python CLI, private TypeScript validation SDK, and display-only Web Component are included.
- [x] Increment 3: SQLite-backed notification outbox with idempotent event identity, leased claims, bounded retry backoff, dead-letter state, HMAC-SHA256 event signatures, and restricted redacted metadata.
- [x] Notification sender is transport-injected; it has no PAC execution or adapter privileges.

## Explicitly excluded / not yet implemented

- [x] Atomic outbox writes now accompany execution completion, execution indeterminate transitions, and effect indeterminate transitions within their authoritative SQLite transactions. This does **not** imply every possible transition emits an event, nor guarantee end-to-end webhook delivery.
- [x] Increment 5 includes a single fixed-destination HTTPS transport with public-IP DNS validation, DNS-pinned TLS, no redirects, timeouts, and owner-only file-mounted signing key.
- [ ] Subscriber endpoint registration, tenant isolation, credential rotation, egress firewall allowlisting, and production transport certification remain outstanding.
- [x] Explicit polling worker entry point exists; it is not auto-started with the API.
- [ ] No deployed/operated worker, Slack/Discord/Twilio connection, verified customer notification delivery, or hosted endpoint.
- [ ] No public SDK/npm publication, browser/IDE extension, production multi-tenant identity, or production execution-request API.
- [ ] No external provider idempotency certification, distributed exactly-once guarantee, or production authorization.

## Mandatory release gates

- [ ] Full CI on exact final candidate SHA, including all original PAC gates, API, packaged CLI, SDK, and notification outbox tests.
- [ ] Verify candidate SHA and immutable release tag; archive logs, dependency manifest, and release artifact digest.
- [ ] Review tenant isolation, API authentication, rate limiting, public ingress, audit logging, and key rotation.
- [x] Integrate covered state transitions and notification outbox writes in the **same durable SQLite transaction**, with rollback-on-event-failure and restart tests.
- [ ] Complete transition coverage audit, concurrent/crash-injection matrix and notification retention policy for production acceptance.
- [x] Implement source-level fixed HTTPS destination validation, public-address DNS pinning, TLS hostname verification, redirect refusal, bounded timeouts, and owner-only signing-key mounts.
- [ ] Validate deployment-specific outbound egress allowlisting, certificate and key rotation, operational monitoring, and end-to-end transport acceptance.
- [ ] Exercise webhook duplicate deliveries, slow consumers, crash recovery, bounded retries, dead-letter inspection, replay-window verification, and secret rotation.
- [ ] Test persistent database backup/restore and process crash recovery on the actual deployment host.
- [ ] Verify all legacy PAC proof, execution, reconciliation, and redispatch fail-closed behavior.
- [ ] Obtain explicit owner sign-off after evidence-backed deployment acceptance.

**Release decision:** SOURCE INTEGRATION ONLY. The expanded MVP is not authorized for production deployment until every applicable release gate passes. Never reinterpret notification delivery as permission to execute or redispatch a protected action.
