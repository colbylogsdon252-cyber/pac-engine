# Increment 6 — Optional third-party webhook keyway

This is an **opt-in local integration**, not a public multi-tenant service or a production-ready subscriber control plane.

A trusted host can initialize `WebhookKeyway(path)`, provision an HTTPS destination using `provision(verified_tenant_id, destination)`, and explicitly enqueue a tenant-bound event with `enqueue_verified(tenant_id, event_id, payload, verified_tenant_id)`. The host must obtain `verified_tenant_id` from an authenticated, authoritative identity source; an untrusted client cannot supply its own proof of tenancy. The host can invoke `deliver_one(keyway, tenant_id, signing_secret)` using a separately secured secret and may revoke a subscription with `revoke(tenant_id, subscription_id)`.

No registration endpoint is exposed by PAC. The third party's host application owns authentication, provisioning, worker lifecycle, and secret storage. No PAC Proof Token, execution authority, or downstream adapter is delegated.

**Critical boundary:** Current PAC atomic notification events do not contain authoritative tenant IDs. They are not automatically imported or broadcast through this keyway. A trusted tenant-attribution adapter and end-to-end state/event/delivery proof are required before this optional integration can be attached to PAC's canonical outbox.

Per-subscription secret isolation, rotation, delivery in-flight revocation, concurrent worker fencing, and deployed transport acceptance are not certified. This increment demonstrates isolated local provisioning and delivery semantics, not production multi-tenant authorization.
