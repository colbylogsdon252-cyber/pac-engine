# PAC Redispatch Authorization & Recovery v1.0

## Purpose
This phase converts a proven-safe redispatch eligibility decision into durable, single-consumption recovery authority for an existing external effect. It does not create new execution authority.

## Authorization
Only an existing INDETERMINATE effect may enter redispatch authorization.

Class C is never eligible.

Class A/B must first reconcile. PAC creates redispatch authority only when the existing adapter capability policy returns redispatch_eligible=true from authoritative NOT_FOUND evidence.

The authorization binds effect_id, the reconciliation evidence digest, and the policy reason. It is persisted before recovery and may be consumed once.

## Recovery
Recovery verifies the existing effect binding: downstream system, operation, and canonical request digest. Mutation fails closed.

PAC atomically consumes redispatch authority before transitioning the existing effect back to DISPATCHING. No ordinary retry path can substitute for this authorization.

Successful downstream reconciliation transitions the effect to CONFIRMED and resolves the existing indeterminate execution to COMPLETED.

An ambiguous redispatch returns the effect to INDETERMINATE. The consumed authority is not restored. A later recovery requires fresh reconciliation evidence and a new authorization; v1 intentionally prevents automatic retry loops.

## Authority Boundary
Adapters supply dispatch and reconciliation evidence. Adapter code cannot manufacture or consume PAC redispatch authority.

Redispatch authorization does not alter the original proof token, execution_id, or effect_id.

## Guarantee
An ambiguous external effect cannot be redispatched merely because a process restarted or a caller retried. PAC requires authoritative reconciliation evidence, adapter capability policy approval, a durable redispatch authorization, exact effect binding, and atomic single consumption before recovery dispatch.
