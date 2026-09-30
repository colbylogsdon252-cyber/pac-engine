# PAC Downstream Adapter Contract v1.0

## Authority Boundary
Adapters dispatch already-authorized effects and return downstream evidence. They never grant PAC execution authority, complete PAC executions directly, release execution claims, or independently authorize redispatch.

Every adapter declares immutable AdapterCapabilities and implements dispatch(effect_id, operation, payload) plus reconcile(effect_id, downstream_reference).

## Class A — Native Idempotency
Class A requires native_idempotency=true. The PAC effect_id MUST be mapped to the downstream provider's idempotency mechanism. Repeated submission of the same effect identity must not create an additional equivalent effect under the provider contract.

Authoritative NOT_FOUND may make redispatch eligible only when the adapter declares authoritative reconciliation and authoritative NOT_FOUND, the required observation/consistency window has elapsed, the original request cannot complete late, and native idempotency remains available.

## Class B — Authoritatively Reconciliable
Class B requires authoritative_reconciliation=true and native_idempotency=false. An ambiguous dispatch is reconciled before any further dispatch decision.

Authoritative NOT_FOUND may make redispatch eligible only after the declared observation and eventual-consistency windows have elapsed and the original request cannot later materialize. Absence before those conditions is insufficient evidence.

## Class C — Non-Idempotent / Non-Authoritative
Class C declares neither native idempotency nor authoritative reconciliation. NOT_FOUND and UNKNOWN never authorize automatic redispatch. Ambiguous outcomes remain INDETERMINATE until separately resolved by sufficient evidence.

## Reconciliation Evidence
Adapters return CONFIRMED, FAILED, NOT_FOUND, or UNKNOWN evidence.

CONFIRMED permits effect state CONFIRMED.
FAILED permits effect state FAILED.
UNKNOWN remains INDETERMINATE.
Non-authoritative NOT_FOUND remains INDETERMINATE.
Authoritative NOT_FOUND is evaluated by PAC against AdapterCapabilities; the adapter itself cannot authorize retry.

## Terminal States
CONFIRMED and FAILED are terminal effect states. Existing terminal effects are not reopened by ordinary reconciliation.

INDETERMINATE is terminal for automatic Class C execution. For Class A/B it remains blocked unless PAC's capability-policy evaluation establishes redispatch eligibility or later reconciliation supplies CONFIRMED/FAILED evidence.

## NOT_FOUND Enforcement
PAC evaluates:
- adapter class;
- authoritative reconciliation capability;
- authoritative NOT_FOUND capability;
- minimum observation window;
- eventual-consistency bound;
- whether the original request can complete late;
- native idempotency for Class A.

A positive result is REDISPATCH_ELIGIBLE as an enforcement decision, not a persisted lifecycle state. The v1 contract does not itself perform redispatch.

## Invariant
Evidence may resolve ambiguity. Absence of evidence cannot silently recreate execution authority.
