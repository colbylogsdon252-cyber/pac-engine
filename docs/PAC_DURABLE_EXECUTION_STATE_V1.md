# PAC Durable Execution State v1.0

## Status
MVP Persistent Protected-Execution Specification

## Purpose
This phase replaces process-local replay memory with durable atomic execution-state persistence. A successfully consumed PAC authorization remains consumed across process restart, and an authorization durably claimed before an unexpected crash remains blocked after restart.

## Persistence Model
PAC uses SQLite as the MVP durable execution-state store. The database records execution identity as a primary key and persists one of three states: claimed, completed, or indeterminate.

SQLite is used here because it supplies transactional uniqueness, crash-safe local persistence, and no new network subsystem. WAL mode, FULL synchronous durability, BEGIN IMMEDIATE, and the execution_id primary key provide the atomic local claim boundary.

## Atomic Claim
The execution identity remains the SHA-256 digest of the complete canonical proof token.

Claim is a transactional INSERT OR IGNORE against the execution_id primary key. Across threads or processes sharing the same database, only one claimant can create the execution record.

## Restart Semantics
completed survives restart and cannot execute again.

claimed survives restart and cannot execute again automatically. This is deliberately fail-closed: after a crash PAC cannot prove whether an external side effect occurred after claim but before completion was recorded.

indeterminate is also non-executable and requires explicit reconciliation outside this automatic execution path.

No startup routine deletes or expires claimed records.

## Action Failure Semantics
If the protected action raises synchronously back to PAC, PAC knows the action did not report completion and releases the active claim for a controlled retry.

If the action returns but durable completion recording fails, PAC marks the execution indeterminate when possible and raises. It does not authorize an automatic replay.

## Crash Boundary
No generic wrapper can prove exactly-once completion of an arbitrary non-transactional external side effect across a crash between the side effect and local completion persistence. PAC therefore does not claim that property.

The enforced guarantee is stronger and auditable: authorization consumption is durable before the side effect begins; after an ambiguous crash, PAC fails closed rather than risking duplicate execution.

True end-to-end exactly-once semantics require the downstream side effect to participate in the same transaction or provide an idempotency key / reconciliation contract.

## Deployment Boundary
This store is suitable for a single-host persistent PAC deployment and concurrent local worker processes that share the same durable SQLite database.

Distributed hosts require a shared transactional datastore with equivalent uniqueness and durability semantics.

## Canonical Guarantee
PAC does not attempt to be correct. PAC enforces proof before action.

For persistent local deployment, a valid authorization must be durably claimed before action, and a consumed or crash-ambiguous authorization cannot silently regain execution authority after restart.
