# PAC Proof Token / Execution Authorization Binding v1.0

## Status
MVP Execution-Authorization Specification

## Purpose
This phase binds canonical PAC proof to the exact protected action that may execute. A successful PAC validation alone is not a transferable execution credential. PAC emits a portable proof token only after canonical validation succeeds. A protected execution boundary must verify that token against the exact payload before action.

## Authorization Invariant
Protected execution is authorized only when current canonical PAC validation succeeds and a valid PAC proof token is cryptographically bound to the exact payload, action, target, proof time, and state. Neither canonical validation nor possession of a token substitutes for the other.

## Token Issuance
issue_proof_token(payload, secret):
1. Runs the existing canonical validator.
2. Refuses issuance if canonical validation fails.
3. Binds the token to the canonical JSON SHA-256 digest of the complete payload.
4. Records the action, target, proof timestamp, state at proof, current state, and temporal expiry.
5. Signs the claims with HMAC-SHA256 using operator-controlled secret material.

The secret is not stored in the token or repository.

## Determinism
For identical payload content after canonical JSON normalization, identical contract temporal limits, and identical secret material, token claims and signature are deterministic. No random identifier or wall-clock issuance timestamp is introduced.

## Execution Authorization
verify_execution_authorization(payload, token, secret) fails closed unless current canonical validation succeeds, token structure and HMAC signature are valid, the token version is supported, expiry has not passed, the complete payload digest matches, and action/target/proof-time/state bindings match exactly.

A protected executor must treat authorized=false as denial.

## Mutation and Replay Boundary
Any payload mutation changes the payload digest and invalidates authorization. State mutation also fails current canonical temporal validation and/or explicit token binding. A token cannot extend proof beyond the contract-defined temporal window.

This MVP does not implement distributed replay registries or one-time nonce consumption. A still-valid token may be presented more than once for the same unchanged payload. One-time execution semantics belong to a later execution-adapter/replay-control phase.

## Secret Boundary
MVP signing uses HMAC-SHA256 and requires at least 32 bytes of operator-controlled secret material. Secret distribution, rotation, hardware-backed key custody, asymmetric verification, and multi-tenant key management are outside this MVP phase.

## Architectural Boundary
The canonical validator remains the proof authority. The proof-token module does not create a second proof evaluator. It consumes the canonical validator result and adds execution authorization binding. The module authorizes or denies execution; it does not perform the protected action itself.

## Canonical Guarantee
PAC does not attempt to be correct. PAC enforces proof before action. A protected action presented without current canonical proof and a valid payload-bound execution authorization token is not authorized to execute.
