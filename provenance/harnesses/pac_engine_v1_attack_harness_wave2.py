from __future__ import annotations

from dataclasses import replace
from typing import Callable, List

from pac_engine_v1_0_core import (
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
# Scope: Wave 2
# Objective: compound false-approval resistance testing


def build_known_good_signal() -> PacSignal:
    return PacSignal(
        signal_id="PAC-W2-BASELINE",
        description="Known-good wave 2 baseline",
        scope="attack_harness_wave2",
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


class AttackCase:
    def __init__(
        self,
        name: str,
        mutate: Callable[[PacSignal], PacSignal],
        expected_decision: EnforcementDecision,
        expected_proof_complete: bool,
        expected_reason_fragments: List[str],
    ):
        self.name = name
        self.mutate = mutate
        self.expected_decision = expected_decision
        self.expected_proof_complete = expected_proof_complete
        self.expected_reason_fragments = expected_reason_fragments


def stringify_reasons(reasons: List[str]) -> str:
    return " | ".join(reasons).lower()


def run_attack(engine: PacEngine, case: AttackCase):
    base = build_known_good_signal()
    attacked = case.mutate(base)
    result = engine.evaluate(attacked)

    decision_ok = result.decision == case.expected_decision
    proof_ok = result.proof_complete == case.expected_proof_complete

    reason_blob = stringify_reasons(result.reasons)
    reasons_ok = all(fragment.lower() in reason_blob for fragment in case.expected_reason_fragments)

    false_approve = result.decision == EnforcementDecision.APPROVE and not case.expected_proof_complete
    passed = decision_ok and proof_ok and reasons_ok and not false_approve

    print("=" * 72)
    print(f"ATTACK CASE: {case.name}")
    print("-" * 72)
    print("Expected Decision :", case.expected_decision)
    print("Actual Decision   :", result.decision)
    print("Decision Match    :", "PASS" if decision_ok else "FAIL")
    print()
    print("Expected Proof    :", case.expected_proof_complete)
    print("Actual Proof      :", result.proof_complete)
    print("Proof Match       :", "PASS" if proof_ok else "FAIL")
    print()
    print("Expected Reasons  :", case.expected_reason_fragments)
    print("Actual Reasons    :", result.reasons)
    print("Reason Match      :", "PASS" if reasons_ok else "FAIL")
    print()
    print("False Approve     :", "YES" if false_approve else "NO")
    print("OVERALL RESULT    :", "PASS" if passed else "FAIL")
    print()

    return passed, false_approve


# ---------------- WAVE 2 COMPOUND ATTACKS ----------------

def w2_a01_high_evidence_missing_stage_temporal_drift(sig):
    return replace(
        sig,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        stages=replace(sig.stages, global_confirmation=False),
        temporal=replace(sig.temporal, current_state_id="STATE-B"),
    )


def w2_a02_constraint_failure_plus_contradiction(sig):
    return replace(
        sig,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        constraints=replace(sig.constraints, distinctness=False),
        failures=replace(sig.failures, contradiction_detected=True),
    )


def w2_a03_r4_high_evidence_missing_stage_low_cycles(sig):
    return replace(
        sig,
        risk_level=RiskLevel.R4_SYSTEM_CRITICAL,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        stages=replace(sig.stages, failure_mode_analysis=False),
        temporal=replace(sig.temporal, stable_multi_cycle_count=1),
    )


def w2_a04_known_failure_plus_temporal_mismatch(sig):
    return replace(
        sig,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        failures=replace(sig.failures, known_failures=["REUSED_INVALID_PROOF"]),
        temporal=replace(sig.temporal, current_state_id="STATE-C"),
    )


def w2_a05_multi_vector_false_completeness(sig):
    return replace(
        sig,
        risk_level=RiskLevel.R4_SYSTEM_CRITICAL,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        constraints=replace(sig.constraints, completeness=False),
        stages=replace(sig.stages, global_confirmation=False),
        failures=replace(sig.failures, suspected_failures=["PARTIAL_SCOPE_CONFIRMATION"]),
        temporal=replace(sig.temporal, stable_multi_cycle_count=1, current_state_id="STATE-Z"),
    )


def build_attack_suite():
    return [
        AttackCase(
            "W2_A01_high_evidence_missing_stage_temporal_drift",
            w2_a01_high_evidence_missing_stage_temporal_drift,
            EnforcementDecision.HALT,
            False,
            ["missing stages", "temporal invalidation", "proof incomplete"],
        ),
        AttackCase(
            "W2_A02_constraint_failure_plus_contradiction",
            w2_a02_constraint_failure_plus_contradiction,
            EnforcementDecision.REJECT,
            False,
            ["constraint failure detected"],
        ),
        AttackCase(
            "W2_A03_r4_high_evidence_missing_stage_low_cycles",
            w2_a03_r4_high_evidence_missing_stage_low_cycles,
            EnforcementDecision.HALT,
            False,
            ["missing stages", "insufficient multi-cycle validation", "proof incomplete"],
        ),
        AttackCase(
            "W2_A04_known_failure_plus_temporal_mismatch",
            w2_a04_known_failure_plus_temporal_mismatch,
            EnforcementDecision.HALT,
            False,
            ["failure condition present", "temporal invalidation", "proof incomplete"],
        ),
        AttackCase(
            "W2_A05_multi_vector_false_completeness",
            w2_a05_multi_vector_false_completeness,
            EnforcementDecision.REJECT,
            False,
            ["constraint failure detected"],
        ),
    ]


def main():
    engine = PacEngine()
    suite = build_attack_suite()

    passed = 0
    failed = 0
    false_approves = 0

    print("=" * 72)
    print("PAC ENGINE v1 ADVERSARIAL HARNESS - WAVE 2")
    print("=" * 72)
    print()

    for case in suite:
        ok, fa = run_attack(engine, case)
        if ok:
            passed += 1
        else:
            failed += 1
        if fa:
            false_approves += 1

    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    print("Total:", len(suite))
    print("Passed:", passed)
    print("Failed:", failed)
    print("False Approves:", false_approves)

    if false_approves > 0:
        print("CRITICAL FAILURE: False approval occurred.")
    else:
        print("No false approvals detected.")

    print("=" * 72)


if __name__ == "__main__":
    main()
