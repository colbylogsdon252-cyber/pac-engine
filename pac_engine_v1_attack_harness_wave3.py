from __future__ import annotations

import random
from dataclasses import replace
from typing import List, Tuple

from pac_engine_v1_1_core import (
    EvidenceLevel,
    RiskLevel,
    EnforcementDecision,
    ConstraintStatus,
    ValidationStages,
    FailureAnalysis,
    TemporalState,
    PacSignal,
    PacEngine,
)


# PAC Engine v1 Attack Harness
# Status: ADVERSARIAL VALIDATION HARNESS
# Scope: Wave 3
# Objective: randomized stress + emergent behavior testing


SEED = 42
ITERATIONS = 50


def build_known_good_signal() -> PacSignal:
    return PacSignal(
        signal_id="PAC-W3-BASELINE",
        description="Known-good wave 3 baseline",
        scope="attack_harness_wave3",
        risk_level=RiskLevel.R3_CROSS_COMPONENT,
        evidence_level=EvidenceLevel.L5_VERIFIED_EXECUTION,
        constraints=ConstraintStatus(
            distinctness=True,
            boundary_integrity=True,
            structural_independence=True,
            referential_integrity=True,
            context_validity=True,
            non_aliasing=True,
            completeness=True,
        ),
        stages=ValidationStages(
            signal_detection=True,
            structural_validation=True,
            equality_consistency_check=True,
            constraint_verification=True,
            failure_mode_analysis=True,
            global_confirmation=True,
            enforcement_decision_ready=True,
        ),
        failures=FailureAnalysis(
            known_failures=[],
            suspected_failures=[],
            contradiction_detected=False,
        ),
        temporal=TemporalState(
            state_id_at_proof="STATE-A",
            current_state_id="STATE-A",
            stable_multi_cycle_count=3,
        ),
    )


def random_evidence(rng: random.Random) -> EvidenceLevel:
    return rng.choice(list(EvidenceLevel))


def random_risk(rng: random.Random) -> RiskLevel:
    return rng.choice(list(RiskLevel))


def mutate_constraints(sig: PacSignal, rng: random.Random) -> Tuple[PacSignal, List[str], bool]:
    constraints = sig.constraints
    notes: List[str] = []
    invalid = False

    fields = [
        "distinctness",
        "boundary_integrity",
        "structural_independence",
        "referential_integrity",
        "context_validity",
        "non_aliasing",
        "completeness",
    ]

    for field in fields:
        if rng.random() < 0.2:
            constraints = replace(constraints, **{field: False})
            notes.append(f"constraint:{field}=False")
            invalid = True

    return replace(sig, constraints=constraints), notes, invalid


def mutate_stages(sig: PacSignal, rng: random.Random) -> Tuple[PacSignal, List[str], bool]:
    stages = sig.stages
    notes: List[str] = []
    invalid = False

    fields = [
        "signal_detection",
        "structural_validation",
        "equality_consistency_check",
        "constraint_verification",
        "failure_mode_analysis",
        "global_confirmation",
        "enforcement_decision_ready",
    ]

    for field in fields:
        if rng.random() < 0.15:
            stages = replace(stages, **{field: False})
            notes.append(f"stage:{field}=False")
            invalid = True

    return replace(sig, stages=stages), notes, invalid


def mutate_failures(sig: PacSignal, rng: random.Random) -> Tuple[PacSignal, List[str], bool]:
    failures = sig.failures
    notes: List[str] = []
    invalid = False

    if rng.random() < 0.2:
        failures = replace(failures, contradiction_detected=True)
        notes.append("failure:contradiction_detected=True")
        invalid = True

    if rng.random() < 0.2:
        failures = replace(failures, known_failures=["KNOWN_ATTACK_FAILURE"])
        notes.append("failure:known_failures=present")
        invalid = True

    if rng.random() < 0.2:
        failures = replace(failures, suspected_failures=["SUSPECTED_ATTACK_FAILURE"])
        notes.append("failure:suspected_failures=present")
        invalid = True

    return replace(sig, failures=failures), notes, invalid


def mutate_temporal(sig: PacSignal, rng: random.Random) -> Tuple[PacSignal, List[str], bool]:
    temporal = sig.temporal
    notes: List[str] = []
    invalid = False

    if rng.random() < 0.3:
        temporal = replace(temporal, current_state_id="STATE-B")
        notes.append("temporal:state_mismatch")
        invalid = True

    if rng.random() < 0.3:
        temporal = replace(temporal, stable_multi_cycle_count=rng.choice([0, 1]))
        notes.append(f"temporal:stable_multi_cycle_count={temporal.stable_multi_cycle_count}")
        # only invalid for R4, but still suspicious
        invalid = True

    return replace(sig, temporal=temporal), notes, invalid


def mutate_core(sig: PacSignal, rng: random.Random) -> Tuple[PacSignal, List[str], bool]:
    notes: List[str] = []
    invalid = False

    risk = random_risk(rng)
    evidence = random_evidence(rng)

    if risk != sig.risk_level:
        notes.append(f"risk={risk.name}")
    if evidence != sig.evidence_level:
        notes.append(f"evidence={evidence.name}")

    sig = replace(sig, risk_level=risk, evidence_level=evidence)

    threshold = PacEngine().required_threshold(risk)
    if evidence < threshold:
        invalid = True

    return sig, notes, invalid
    sig = build_known_good_signal()
    notes: List[str] = []
    incomplete_by_construction = False

    sig, n, bad = mutate_core(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_constraints(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_stages(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_failures(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_temporal(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig = replace(sig, signal_id=f"PAC-W3-{index:03d}")

    return sig, notes, incomplete_by_construction



def generate_attack_case(index: int, rng: random.Random) -> Tuple[PacSignal, List[str], bool]:
    sig = build_known_good_signal()
    notes: List[str] = []
    incomplete_by_construction = False

    sig, n, bad = mutate_core(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_constraints(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_stages(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_failures(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig, n, bad = mutate_temporal(sig, rng)
    notes.extend(n)
    incomplete_by_construction = incomplete_by_construction or bad

    sig = replace(sig, signal_id=f"PAC-W3-{index:03d}")

    return sig, notes, incomplete_by_construction

def main():
    rng = random.Random(SEED)
    engine = PacEngine()

    total = 0
    passed = 0
    failed = 0
    false_approves = 0

    print("=" * 72)
    print("PAC ENGINE v1 ADVERSARIAL HARNESS - WAVE 3")
    print("=" * 72)
    print(f"Seed       : {SEED}")
    print(f"Iterations : {ITERATIONS}")
    print()

    for i in range(1, ITERATIONS + 1):
        total += 1
        sig, notes, incomplete = generate_attack_case(i, rng)
        result = engine.evaluate(sig)

        false_approve = result.decision == EnforcementDecision.APPROVE and incomplete
        ok = not false_approve

        if ok:
            passed += 1
        else:
            failed += 1
            false_approves += 1

        print("-" * 72)
        print(f"CASE {i:03d}")
        print("Signal ID      :", sig.signal_id)
        print("Mutations      :", notes if notes else ["none"])
        print("Decision       :", result.decision)
        print("Proof Complete :", result.proof_complete)
        print("Reasons        :", result.reasons)
        print("False Approve  :", "YES" if false_approve else "NO")
        print("RESULT         :", "PASS" if ok else "FAIL")

    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    print("Total Cases    :", total)
    print("Passed         :", passed)
    print("Failed         :", failed)
    print("False Approves :", false_approves)

    if false_approves > 0:
        print("CRITICAL FAILURE: false approval occurred under randomized stress.")
    else:
        print("No false approvals detected under randomized stress.")

    print("=" * 72)


if __name__ == "__main__":
    main()
