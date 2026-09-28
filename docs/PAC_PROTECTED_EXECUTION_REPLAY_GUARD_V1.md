# PAC Protected Execution / Replay Guard v1.0

## Status
MVP Protected-Execution Specification

## Purpose
PAC already proves a payload and binds that proof to a signed execution-authorization token. This phase closes the next enforcement gap: the protected side effect itself must be reachable only through a gate that verifies PAC authorization and rejects reuse of the same authorization within the MVP execution boundary.

## Execution Invariant
A protected action is invoked only after:
1. current canonical PAC validation succeeds through proof-token verification;
2. the proof-token signature and exact payload binding are valid;
3. the authorization has not already been claimed by this execution boundary.

Failure at any gate means the action callable is not invoked.

## Replay Identity
The MVP execution identity is the SHA-256 digest of the complete canonical proof-token object. Identical signed authorization therefore maps deterministically to the same execution identity.

## Atomic Claim
ExecutionReplayStore.claim performs check-and-claim under a lock. Concurrent presentations of the same authorization cannot both obtain the process-local execution claim.

## Failure Semantics
Authorization failure is fail-closed and returns executed=false.

Replay is fail-closed and returns executed=false with reason authorization_replayed.

If the protected action raises before completion, the MVP store releases the claim so an operator-controlled retry may occur. A successfully completed action retains its claim for the lifetime of the store.

## Persistence Boundary
The v1.0 MVP replay store is intentionally process-local and in-memory. It proves the execution-gate and atomic replay-control semantics without introducing a database or distributed subsystem.

Process restart loses replay history. Multi-process/distributed exactly-once enforcement therefore remains outside this phase and must not be claimed.

## Architectural Boundary
The protected-execution module does not evaluate proof independently. It delegates authorization to verify_execution_authorization, which itself delegates current proof validity to the canonical PAC validator.

The protected action is injected as a callable. PAC does not define application-specific side effects.

## Canonical Guarantee
PAC does not attempt to be correct. PAC enforces proof before action.

Within this MVP execution boundary, an action without valid current PAC authorization is not invoked, and a successfully consumed authorization cannot invoke the action a second time in the same replay-store lifetime.
