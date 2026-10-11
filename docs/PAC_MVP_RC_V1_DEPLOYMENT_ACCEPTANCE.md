# PAC MVP RC v1.0 — Deployment Acceptance Checklist

**Status:** NOT PRODUCTION CERTIFIED. Checklist is a release-management control, not execution authority.

## Source and release provenance

- [x] Canonical baseline merged commit: `540c1f3296143ad43bd33a4fd99c3ddc8da8325c`.
- [x] Candidate branch CI run [#54](https://github.com/colbylogsdon252-cyber/pac-engine/actions/runs/38108259646) passed at `7de5e41fb935360eff08ecc2e339d23570016aa6`.
- [x] Verified merge commit identical to `main` at time of candidate selection.
- [ ] Create annotated immutable release-candidate tag `pac-mvp-rc-v1.0` pointing **exactly** to `540c1f3296143ad43bd33a4fd99c3ddc8da8325c`; verify remote tag target and tag type. Do not retarget or force-update. Tag creation is not implied by this checklist.
- [ ] Confirm protected tag rules prevent deletion and updates; retain immutable CI evidence.
- [ ] Run the complete CI gate on the exact tagged commit (not merely an earlier PR head); archive run URL and SHA.

## Deployment-specific acceptance

- [ ] Record target host, OS, Python runtime, deployment identity, network ingress, and rollback owner.
- [ ] Install dependencies in a clean environment with pinned, reviewed versions; preserve build logs and artifact digest.
- [ ] Mount production keyring from approved secret store as regular owner-owned file with owner-only permissions; no symlinks or inline secrets.
- [ ] Set `PAC_DEPLOYMENT_MODE=production`, `PAC_PROOF_KEYRING_FILE`, and `PAC_PROOF_ACTIVE_KEY_ID`; verify startup fails with missing/revoked keys and insecure mount permissions.
- [ ] Verify key rotation and immediate revocation with separate test keys; do not expose secret values in logs.
- [ ] Configure persistent local SQLite storage on a supported filesystem; verify exclusive access, permissions, backups, restore, and durability after process restart.
- [ ] Exercise clean restart, abrupt termination, PREPARED resume, CONFIRMED repair, INDETERMINATE blocking, and single-consumption redispatch authority.
- [ ] Verify invalid proof, stale state, mismatched target/payload, malformed adapter evidence, and illegal state transitions fail closed.
- [ ] Verify health/monitoring, failure alerts, audit-log retention, access controls, incident escalation, and rollback steps.
- [ ] Record recovery time and data integrity from a tested backup restore.
- [ ] Validate actual downstream adapter idempotency and authoritative reconciliation against provider documentation and controlled sandbox effects; Class C ambiguous outcomes remain non-retryable.
- [ ] Explicitly approve network exposure and credential scope only after environment-specific security review.

## Release decision

**Automated MVP baseline:** PASS, as evidenced by CI #54.

**Tagged release candidate:** PENDING until the annotated tag exists and its exact target is independently verified.

**Deployment acceptance:** PENDING until every applicable item above is supported by evidence.

**Production authorization:** DENIED by default. Requires a separate explicit release decision after deployment-specific acceptance.

## Immutable-tag operator procedure

Use a clean local clone with Git push authorization. Verify `git rev-parse origin/main` matches the expected SHA before tagging. Create the annotated tag at the exact commit, then push without force:

```bash
git tag -a pac-mvp-rc-v1.0 540c1f3296143ad43bd33a4fd99c3ddc8da8325c -m "PAC MVP release candidate v1.0 — feature frozen"
git push origin refs/tags/pac-mvp-rc-v1.0
```

Verify the remote annotated tag object resolves to the expected commit:

```bash
git fetch origin tag pac-mvp-rc-v1.0
git rev-parse pac-mvp-rc-v1.0^{}
```

The output MUST be `540c1f3296143ad43bd33a4fd99c3ddc8da8325c`. If the tag already exists, stop and inspect it; never overwrite it.
