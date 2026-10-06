# PAC Engine

**Proof-Aware Constraint Validation (PAC)**

PAC is a deterministic proof-gated execution system. Its governing invariant is:

> PAC does not attempt to be correct. PAC enforces that correctness must be proven before action.

The current MVP extends beyond validation. It binds canonical proof to execution authority, durably consumes that authority, protects external effects, reconciles ambiguous downstream outcomes, and permits redispatch only through evidence-backed recovery authority.

## Current MVP architecture

The active enforcement path is:

```text
proposed action
    |
validate_canonical()
    |
temporal + state validity
    |
signed Proof Token
    |
execution-authorization verification
    |
durable execution claim
    |
deterministic effect_id
    |
durable external-effect ledger
    |
Class A / B / C downstream adapter
    |
dispatch
    |
reconciliation evidence
    |
+-- CONFIRMED --> effect confirmed --> execution completed
+-- FAILED -----> effect failed
+-- UNKNOWN ----> INDETERMINATE
+-- NOT_FOUND --> PAC capability-policy evaluation
                      |
                      +-- insufficient evidence --> INDETERMINATE
                      +-- proven safe Class A/B recovery
                              |
                              durable single-use redispatch authority
                              |
                              exact binding + atomic consumption
                              |
                              recovery dispatch + reconciliation
```

Adapters supply evidence. They do not grant execution authority, complete PAC executions directly, release execution claims, or independently authorize redispatch.

## Active runtime

The active MVP runtime is at the repository root:

- `pac_contract_validator.py` — canonical validation authority through `validate_canonical()`.
- `pac_cli.py` — thin CLI transport to canonical validation.
- `pac_api.py` — thin API transport to canonical validation.
- `pac_proof_token.py` — signed proof-token issuance and exact execution-authorization verification.
- `pac_protected_execution.py` — durable execution claims and protected execution state.
- `pac_external_effect.py` — deterministic external-effect identity, durable effect ledger, dispatch and reconciliation state machine.
- `pac_downstream_adapter.py` — immutable Class A/B/C capability declarations and authoritative-NOT_FOUND policy evaluation.
- `pac_redispatch_recovery.py` — durable, single-consumption redispatch authorization and recovery.

Historical engines, interfaces, attack harnesses, backups, and failure artifacts live under `provenance/` and are not active runtime alternatives.

## Proof Tokens

Canonical validation approval alone is not a transferable execution credential. `issue_proof_token()` reruns canonical validation and creates a signed token binding the approved payload to its proof timestamp, expiry, state identities, action, target, and complete payload digest.

`verify_execution_authorization()` revalidates the current payload and verifies the token signature, expiry, digest, explicit bindings, and—when managed keys are used—the signed key identifier and revocation state before protected execution may proceed. A token therefore authorizes only the exact proven payload while its proof and signing key remain valid.\n\nManaged deployments use `ProofKeyring` with a runtime-mounted owner-only key file. Rotation changes the active key ID while retaining old non-revoked verification keys for the remaining token lifetime; revocation fails closed immediately. Signing secrets must not be committed or supplied inline through environment variables. See `docs/PAC_SECRET_KEY_HANDLING.md`.

## Secret and key handling

Hardened deployments use a file-mounted `ProofKeyring` with an explicit active `key_id`. New Proof Tokens bind that identifier into their signed claims. Rotation retains prior non-revoked verification keys while changing the active signing key; revocation fails closed immediately for tokens bound to the revoked key.

Production key material is loaded from an owner-only secret file configured by `PAC_PROOF_KEYRING_FILE` and `PAC_PROOF_ACTIVE_KEY_ID`. Inline keyring secrets in environment variables are rejected. See `docs/PAC_SECRET_KEY_HANDLING.md`.

## Durable execution

`DurableExecutionStore` persists execution authority consumption in SQLite. The execution identity is derived from the complete canonical Proof Token.

Execution states are `claimed`, `completed`, and `indeterminate`. Claims survive process restart. A completed execution cannot automatically execute again. Crash-ambiguous executions remain blocked rather than silently regaining authority.

For external effects, execution claim and initial `PREPARED` effect persistence are committed atomically in the shared PAC database. This closes the crash boundary in which an execution claim could otherwise exist without its corresponding effect record.

PAC does **not** claim generic end-to-end exactly-once execution for arbitrary non-transactional external systems.

## External effects and reconciliation

Every downstream operation receives a deterministic `effect_id` derived from:

- execution identity;
- downstream system identity;
- operation;
- canonical external-effect payload.

The durable effect ledger uses the lifecycle:

```text
PREPARED -> DISPATCHING -> ACKNOWLEDGED -> CONFIRMED
                    \                    -> FAILED
                     \------------------> INDETERMINATE
```

Legal transitions are enforced by PAC. `CONFIRMED` and `FAILED` are terminal and cannot be reopened through ordinary state transitions.

A transport exception, malformed adapter response, malformed reconciliation evidence, crash ambiguity, `UNKNOWN`, or insufficient `NOT_FOUND` evidence fails closed. PAC does not blindly redispatch an ambiguous effect.

## Class A / B / C adapters

Every downstream adapter declares immutable `AdapterCapabilities` and implements dispatch and reconciliation.

### Class A — native idempotency

Class A requires downstream-native idempotency. PAC's deterministic `effect_id` must map to the provider's idempotency mechanism.

An authoritative `NOT_FOUND` can support redispatch eligibility only when the adapter's declared reconciliation policy is satisfied, the required observation/consistency window has elapsed, the original request cannot complete late, and native idempotency remains available.

### Class B — authoritatively reconciliable

Class B does not rely on native idempotent dispatch but provides authoritative reconciliation. An ambiguous dispatch must be reconciled before another dispatch can be considered.

Authoritative `NOT_FOUND` can support redispatch eligibility only after PAC verifies the declared observation window, eventual-consistency bound, and no-late-completion condition.

### Class C — non-idempotent / non-authoritative

Class C supplies neither a sufficient native idempotency guarantee nor authoritative reconciliation. `NOT_FOUND` and `UNKNOWN` never create automatic redispatch authority.

An ambiguous Class C effect remains `INDETERMINATE` until sufficient evidence resolves it through a separately authorized process.

## Redispatch recovery

`REDISPATCH_ELIGIBLE` is a PAC policy decision, not a persisted effect state.

For an existing `INDETERMINATE` Class A/B effect, PAC may create durable redispatch authority only after authoritative reconciliation evidence satisfies the adapter capability policy. The authorization binds:

- the existing `effect_id`;
- reconciliation-evidence digest;
- policy reason.

Recovery verifies the original downstream system, operation, and canonical request digest. Redispatch authority is single-use. Consumption of that authority and transition of the effect back to `DISPATCHING` occur atomically in the shared PAC database.

An ambiguous recovery dispatch returns to `INDETERMINATE`; consumed authority is not recreated. Another recovery requires fresh evidence and new authorization.

## Deployment boundary

The current persistence architecture is intentionally **single-host SQLite**.

A supported MVP deployment may run concurrent local workers only when every PAC process shares the same durable SQLite database. The execution ledger, external-effect ledger, and redispatch-authorization ledger depend on that common transactional boundary.

The current MVP does not establish distributed-host execution safety. Multiple independent PAC hosts must not use separate SQLite databases while acting as one execution authority. Moving to distributed hosts requires a shared transactional datastore that preserves PAC's uniqueness, atomic-consumption, state-transition, and durability semantics.

SQLite is configured with WAL journaling, `synchronous=FULL`, a busy timeout, primary-key uniqueness, and `BEGIN IMMEDIATE` around authority/state mutations.

The SQLite database must reside on persistent local storage appropriate for SQLite locking and durability. Do not treat ephemeral container storage or independently replicated database files as a valid PAC durability boundary.

## Crash and restart behavior

PAC intentionally fails closed across ambiguous boundaries:

- durable claims survive restart;
- `DISPATCHING`, `ACKNOWLEDGED`, and `INDETERMINATE` effects are not automatically redispatched after restart;
- restart may reconcile an existing effect without dispatching it again;
- malformed or unavailable adapter evidence cannot manufacture terminal state or recovery authority;
- terminal effect states cannot be reopened;
- redispatch authority cannot be consumed concurrently more than once.

A downstream side effect cannot participate atomically in PAC's local SQLite transaction. End-to-end exactly-once behavior therefore requires downstream-native idempotency or a reconciliation contract strong enough to resolve ambiguity.

## CLI and API validation

CLI:

```bash
python pac_cli.py test_payload.json
```

API:

```bash
python -m uvicorn pac_api:app --host 0.0.0.0 --port 8000
curl -X POST http://127.0.0.1:8000/validate \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

The CLI and API are transports over the same canonical validator. They are not alternate enforcement implementations.

## Verification

The GitHub Actions MVP gate covers Proof Tokens, temporal lifecycle, protected execution/replay, durable execution state, external-effect reconciliation, downstream adapter contracts, redispatch authorization/recovery, crash/race/state hardening, active-runtime boundaries, and CLI/API parity.

## Architecture specifications

See:

- `docs/PAC_TEMPORAL_PROOF_LIFECYCLE_V1.md`
- `docs/PAC_PROOF_TOKEN_EXECUTION_AUTHORIZATION_V1.md`
- `docs/PAC_PROTECTED_EXECUTION_REPLAY_GUARD_V1.md`
- `docs/PAC_DURABLE_EXECUTION_STATE_V1.md`
- `docs/PAC_EXTERNAL_EFFECT_IDEMPOTENCY_RECONCILIATION_V1.md`
- `docs/PAC_DOWNSTREAM_ADAPTER_CONTRACT_V1.md`
- `docs/PAC_REDISPATCH_AUTHORIZATION_RECOVERY_V1.md`
- `docs/PAC_MVP_DEPLOYMENT.md`

## Guarantee boundary

PAC enforces proof before action and evidence before recovery. It does not assert that arbitrary downstream systems are correct, available, transactional with PAC, or universally exactly-once.
