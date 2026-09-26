# PAC Temporal Proof Lifecycle v1.0

## Status

MVP Temporal Enforcement Specification

## Purpose

This specification defines the minimum temporal proof lifecycle required for PAC MVP enforcement.

PAC does not model probabilistic proof decay, confidence curves, background refresh orchestration, or generalized temporal governance in v1.0.

The temporal lifecycle exists only to ensure that proof cannot authorize protected execution after the proof has become stale or after the state to which the proof was bound has materially changed.

## Core Temporal Invariant

> Proof may authorize execution only while it is fresh and remains applicable to the state for which it was validated.

If freshness or state applicability cannot be proven, execution must not proceed.

## Existing Temporal Authority

PAC already requires a proof timestamp and enforces a contract-defined maximum proof age.

The existing temporal rules remain authoritative:

- Missing required temporal proof halts validation.
- A proof timestamp in the future is invalid.
- Proof older than the configured maximum age is expired.
- Temporal failure occurs before protected execution.

## Lifecycle States

### VALID

Proof is temporally acceptable for the current evaluation.

VALID requires:

1. Required temporal proof exists.
2. The proof timestamp is structurally valid.
3. The proof timestamp is not in the future.
4. Proof age does not exceed the contract-defined freshness window.
5. The state to which the proof applies has not materially changed.

### EXPIRED

Proof has exceeded the contract-defined freshness window.

Expired proof cannot authorize execution.

### INVALIDATED

Proof was valid when established but no longer applies because the state or conditions to which the proof was bound materially changed.

Invalidated proof cannot authorize execution.

## Revalidation Requirement

REVALIDATION_REQUIRED is an enforcement condition, not an additional persisted proof lifecycle state.

Revalidation is required whenever proof is missing, expired, invalidated, or otherwise temporally unverifiable.

Protected execution remains denied until new proof is acquired and validated against the current state.

## Freshness Rule

Proof freshness is determined by the existing contract-controlled temporal boundary:

`current_time - proof_timestamp <= max_age_seconds`

If proof age exceeds `max_age_seconds`, the proof is EXPIRED.

## Future-Time Rule

A proof timestamp greater than the current evaluation time is invalid.

Future-dated proof must fail closed and cannot authorize execution.

## Mutation Invalidation Rule

A material change to the state or conditions for which proof was established invalidates that proof.

PAC must not silently carry proof authority across a material state mutation.

The canonical implementation reuses PAC's existing state-binding identifiers: `state_id_at_proof` records the state against which proof was established, and `current_state_id` records the state presented for the current evaluation. A mismatch invalidates proof. No new state-binding field is introduced.

These identifiers are required temporal inputs in the frozen contract. Missing, malformed, or mismatched state-binding data fails closed through the canonical temporal validator.

## Enforcement Rule

Only VALID temporal proof may continue through the canonical PAC enforcement pipeline.

EXPIRED, INVALIDATED, missing, or temporally unverifiable proof must halt protected execution and require revalidation.

## Fail-Closed Rule

If PAC cannot determine temporal validity from authoritative proof and contract data, PAC must deny execution.

Temporal uncertainty must never be interpreted as approval.

## Audit Requirement

A temporal denial must remain machine-observable through the canonical PAC failure and classification path.

Canonical temporal errors use the `temporal.` prefix. Expiration is emitted as `temporal.proof_expired`; state mutation is emitted as `temporal.proof_invalidated`. This corrects the prior expiration message form (`temporal proof expired`), which did not enter the temporal classification branch.

The temporal lifecycle must not introduce a second error authority or transport-specific enforcement path.

## MVP Boundary

PAC Temporal Proof Lifecycle v1.0 intentionally excludes:

- probabilistic confidence decay
- gradual proof degradation
- temporal scoring
- background proof refresh
- distributed proof synchronization
- revalidation workflow orchestration
- transport-specific temporal rules

These capabilities are outside the PAC MVP objective.

## Canonical Guarantee

PAC guarantees that unproven actions will not be executed.

Proof that is expired, invalidated, missing, or temporally unverifiable is unproven for the protected action.
