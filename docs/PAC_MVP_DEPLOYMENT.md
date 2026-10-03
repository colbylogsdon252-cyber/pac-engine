# PAC MVP Deployment

## Scope

This document defines the supported deployment boundary for the current PAC MVP. It covers the active proof-to-execution architecture: canonical validation, Proof Tokens, durable execution authority, external-effect persistence, Class A/B/C adapters, reconciliation, redispatch recovery, and the single-host SQLite persistence boundary.

It is an operational contract, not a claim of distributed exactly-once execution.

## Supported topology

The MVP is designed for one PAC host with one persistent SQLite database shared by all PAC worker processes on that host.

```text
                    single PAC host
+------------------------------------------------------+
| API / application / worker processes                 |
|          |                                           |
|          v                                           |
| canonical validation -> Proof Token verification     |
|          |                                           |
|          v                                           |
| durable execution / effect / redispatch state        |
|          |                                           |
|          v                                           |
|       one shared SQLite database                     |
|          |                                           |
|          v                                           |
| Class A/B/C adapter -> external downstream system    |
+------------------------------------------------------+
```

Multiple local processes may contend for authority because the database supplies the common transaction and uniqueness boundary.

Multiple independent hosts using separate SQLite files are **not** a supported PAC execution topology.

## Persistent database requirement

Instantiate `DurableExecutionStore`, `ExternalEffectStore`, and `RedispatchAuthorizationStore` against the same persistent database path whenever they participate in one protected external-effect workflow.

The database must survive process restart and host-service restart. Ephemeral container layers, temporary directories, or independently copied/replicated SQLite files do not satisfy this requirement.

The current implementation uses:

- SQLite transactional persistence;
- WAL journal mode;
- `synchronous=FULL`;
- `busy_timeout=30000`;
- `BEGIN IMMEDIATE` for authority/state mutations;
- primary-key uniqueness and conditional updates.

The external-effect path atomically creates the execution claim and initial `PREPARED` effect in the shared database. Redispatch recovery atomically consumes recovery authority and acquires the effect's recovery `DISPATCHING` state.

## Proof and execution flow

A deployment must preserve this authority sequence:

1. Submit the payload to canonical `validate_canonical()`.
2. Issue a Proof Token only from a payload that passes canonical validation.
3. At execution time, verify the token against the exact current payload.
4. Durably claim the execution identity before protected action.
5. For external effects, derive the deterministic `effect_id` and persist the effect before downstream dispatch.
6. Dispatch only through the declared downstream adapter.
7. Reconcile downstream evidence.
8. Complete only from sufficient confirmation; otherwise fail closed into the appropriate blocked state.
9. If an indeterminate Class A/B effect becomes proven safe to redispatch, create and atomically consume explicit redispatch recovery authority.

Do not implement an application-level shortcut from validation `APPROVE` directly to a mutating downstream call. Validation is proof; the Proof Token and protected execution path carry execution authority.

## Proof Token secret

The current Proof Token implementation uses HMAC-SHA256 and requires signing-secret material of at least 32 UTF-8 bytes.

Treat the signing secret as deployment secret material:

- do not commit it to the repository;
- do not put it into effect payloads, logs, effect evidence, or SQLite records;
- keep issuance and verification on trusted PAC infrastructure;
- rotate only with an explicit compatibility/migration plan because existing tokens depend on the signing key.

Secret-management infrastructure and distributed key management are outside the current MVP implementation.

## Adapter deployment contract

Every external adapter must expose a stable `system_id`, immutable `AdapterCapabilities`, `dispatch(effect_id, operation, payload)`, and `reconcile(effect_id, downstream_reference)`.

Adapter classification is an enforcement input, not descriptive metadata.

### Class A

Use Class A only when the provider offers native idempotency strong enough for PAC's deterministic `effect_id` to protect equivalent repeated submission.

The adapter must map `effect_id` to that provider mechanism. If the provider cannot preserve this property, the integration is not Class A.

### Class B

Use Class B only when the provider supplies authoritative reconciliation capable of establishing whether the original effect exists or definitively does not exist.

If `NOT_FOUND` can be eventual, incomplete, or followed by late completion, declare those constraints accurately. PAC will not treat absence as redispatch evidence until the declared policy proves it safe.

### Class C

Use Class C when neither sufficient native idempotency nor authoritative reconciliation exists. Ambiguous Class C effects are not automatically redispatched.

Do not upgrade an adapter class to obtain recovery behavior. Classification must reflect documented downstream guarantees.

## Reconciliation

Reconciliation evidence is one of `CONFIRMED`, `FAILED`, `NOT_FOUND`, or `UNKNOWN`.

`CONFIRMED` can resolve an eligible effect to terminal `confirmed`.

`FAILED` can resolve an eligible effect to terminal `failed`.

`UNKNOWN` is insufficient and remains blocked.

`NOT_FOUND` is not inherently permission to dispatch again. PAC evaluates the adapter class and capability policy, including authoritative reconciliation, observation/consistency windows, late-completion behavior, and Class A native idempotency.

Malformed evidence or adapter exceptions fail closed rather than manufacturing resolution.

## Redispatch recovery

Automatic ordinary retries are not a substitute for PAC recovery.

Only an existing `INDETERMINATE` Class A/B effect may become eligible. PAC first reconciles it. If authoritative NOT_FOUND evidence satisfies the declared capability policy, PAC may persist a redispatch authorization bound to the effect, evidence digest, and policy reason.

Recovery then verifies the persisted downstream system, operation, and request digest before atomically consuming that authorization and transitioning the existing effect to `DISPATCHING`.

A recovery authorization is single-use. If recovery is ambiguous, the effect returns to `INDETERMINATE`; fresh evidence and a new authorization are required for any later recovery.

Class C has no automatic redispatch path.

## Restart and crash handling

On startup, do not clear, expire, or reinterpret durable execution/effect records merely because the process restarted.

Important recovery cases:

- `completed`: already consumed; do not execute again.
- `claimed`: blocked after restart unless an explicitly supported resolution path proves what happened.
- `indeterminate` execution: blocked pending resolution.
- `dispatching`, `acknowledged`, or `indeterminate` effect: reconcile; do not blindly dispatch again.
- `confirmed` or `failed` effect: terminal; do not reopen.

The system deliberately prefers a blocked ambiguous operation over a duplicate external side effect.

## Process concurrency

Concurrent local PAC workers are supported only against the same durable SQLite database.

Do not add application-level read-then-write authority checks in place of the transactional store operations. Authority acquisition and state transitions depend on database-level conditional mutation.

The hardening suite exercises concurrent initial execution and concurrent redispatch-authority consumption to ensure one caller obtains the relevant dispatch authority.

## Filesystem and backup considerations

The SQLite file is part of PAC's execution-authority state, not disposable cache.

Operationally:

- place it on persistent local storage with normal SQLite file-locking semantics;
- protect the database and its WAL-related files according to SQLite operational requirements;
- take backups using a SQLite-consistent mechanism rather than copying a live database as unrelated files;
- restore the database as a coherent authority ledger;
- never run two divergent restored copies as simultaneous authorities for the same workload.

A backup can preserve history; it must not create a second live authority domain.

## Unsupported distributed topology

The current MVP must not be represented as distributed-safe merely by placing the SQLite file on shared or replicated storage.

A future multi-host PAC deployment requires a shared transactional datastore that can preserve, at minimum:

- unique execution claims;
- atomic execution/effect creation;
- legal conditional effect-state transitions;
- single-consumption redispatch authority;
- crash durability;
- concurrency semantics equivalent to the current local transaction boundary.

That migration requires its own validation and adversarial race testing.

## External exactly-once boundary

PAC's local database transaction cannot atomically include an arbitrary remote provider.

Accordingly:

- Class A uses provider-native idempotency to reduce duplicate-effect risk.
- Class B uses authoritative reconciliation and controlled recovery.
- Class C fails closed when outcome is ambiguous.

PAC does not claim universal exactly-once external side effects. It claims durable authority consumption and evidence-gated recovery within the implemented boundary.

## Pre-deployment verification

Before deploying a build:

1. Run the repository's `PAC MVP Verification` workflow successfully for the exact commit.
2. Confirm CLI/API parity remains green.
3. Confirm the adapter's declared class matches the actual provider contract.
4. Confirm all PAC stores use the intended shared persistent SQLite path.
5. Confirm the Proof Token signing secret is supplied securely and is not repository content.
6. Confirm the database path survives process/service restart.
7. Exercise provider reconciliation in a non-production environment, including timeout/unknown behavior.
8. Verify no application path bypasses Proof Token verification and durable authority consumption for protected effects.

## Production claim boundary

The current MVP architecture supports a single-host persistent PAC deployment with concurrent local workers sharing one SQLite authority database.

It does not yet authorize a multi-host distributed PAC deployment. It does not turn a downstream timeout into proof of failure. It does not let an adapter recreate execution authority. It does not automatically retry an ambiguous Class C effect.

Within this boundary, PAC enforces proof before action and evidence before recovery.
