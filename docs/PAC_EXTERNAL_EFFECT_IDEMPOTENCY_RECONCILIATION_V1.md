# PAC External Effect Idempotency & Reconciliation v1.0

## Status
MVP External Side-Effect Boundary Specification

## Purpose
PAC already proves execution authority and durably consumes that authority before protected execution. This phase extends the enforcement boundary across a downstream system where network failure can make the outcome ambiguous.

## Effect Identity
Every external operation receives a deterministic effect_id derived from execution_id, downstream system identity, operation, and the canonical external-effect payload.

The same authorized intended effect therefore retains the same identity across restart and reconciliation. A materially different external payload produces a different identity and cannot masquerade as the persisted effect.

## Durable Effect Ledger
PAC persists an external-effect record before dispatch. States are:

PREPARED -> DISPATCHING -> ACKNOWLEDGED -> CONFIRMED

Ambiguous evidence transitions to INDETERMINATE. Definitive downstream failure may transition to FAILED.

Credentials, authorization headers, and arbitrary secrets are not part of the effect ledger.

## Dispatch Rule
PAC must durably claim execution authority, persist PREPARED, and atomically transition to DISPATCHING before calling the downstream adapter.

An exception after dispatch begins is treated as an ambiguous outcome. PAC does not release execution authority and does not blindly redispatch.

## Adapter Contract
Adapters expose dispatch(effect_id, operation, payload) and reconcile(effect_id, downstream_reference).

The effect_id is the PAC idempotency identity. A real downstream adapter must map it to the provider's supported idempotency mechanism when one exists.

Reconciliation returns structured evidence: CONFIRMED, NOT_FOUND, FAILED, or UNKNOWN.

Adapters provide evidence; they do not grant PAC execution authority.

## Reconciliation Rule
CONFIRMED permits PAC to record the effect as confirmed.

FAILED permits a terminal failed effect record.

UNKNOWN is insufficient evidence and remains fail-closed.

NOT_FOUND is not treated as permission to retry merely because no effect is currently visible. Even an authoritative NOT_FOUND remains blocked in v1.0 until an explicit adapter-specific redispatch policy proves that redispatch is safe.

## Restart / Crash Semantics
DISPATCHING, ACKNOWLEDGED, and INDETERMINATE records survive restart. They are never automatically redispatched.

A restart may reconcile them against the downstream system. If downstream evidence confirms the effect, the effect becomes CONFIRMED without another dispatch.

## Guarantee Boundary
PAC does not claim universal exactly-once semantics for arbitrary downstream systems.

PAC guarantees that it will not knowingly redispatch an ambiguous external effect without evidence and a permitted idempotency/reconciliation contract. Where downstream evidence is insufficient, PAC remains fail-closed.

A provider with native idempotency can use effect_id as its idempotency key. A provider without such support requires authoritative reconciliation or manual resolution.

## Completion Standard
The phase is complete when tests prove that:
- valid authorized effects can be confirmed;
- confirmed effects are not dispatched twice;
- response loss after a downstream effect becomes indeterminate rather than retried;
- restart reconciliation can discover an already-created effect without redispatch;
- non-authoritative NOT_FOUND and UNKNOWN remain fail-closed;
- effect identity changes with a materially changed external payload;
- invalid PAC authorization never reaches downstream dispatch.

PAC does not attempt to be correct. PAC enforces proof before action, and evidence before ambiguous external redispatch.
