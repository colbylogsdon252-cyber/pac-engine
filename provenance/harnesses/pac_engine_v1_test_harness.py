from __future__ import annotations

from dataclasses import replace
from typing import Callable, List, Tuple

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


# PAC Engine v1 Test Harness
# Status: ACTIVE VALIDATION HARNESS
# Target artifact: pac_engine_v1_0_core.py


def build_known_good_signal() -> PacSignal:
    return PacSignal(
        signal_id="PAC-TEST-BASELINE",
        description="Known-good signal for deterministic harness validation",
        scope="harness",
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
            stable_multi_cycle_count=2,
        ),
        metadata={"source": "test_harness"},
    )


class TestCase:
    def __init__(
        self,
        name: str,
        mutate: Callable[[PacSignal], PacSignal],
        expected_decision: EnforcementDecision,
        expected_proof_complete: bool,
        expected_reason_fragments: List[str],
    ) -> None:
        self.name = name
        self.mutate = mutate
        self.expected_decision = expected_decision
        self.expected_proof_complete = expected_proof_complete
        self.expected_reason_fragments = expected_reason_fragments


def stringify_reasons(reasons: List[str]) -> str:
    return " | ".join(reasons).lower()


def run_test(engine: PacEngine, test: TestCase) -> Tuple[bool, str]:
    base_signal = build_known_good_signal()
    mutated_signal = test.mutate(base_signal)
    result = engine.evaluate(mutated_signal)

    decision_ok = result.decision == test.expected_decision
    proof_ok = result.proof_complete == test.expected_proof_complete

    reason_blob = stringify_reasons(result.reasons)
    reasons_ok = all(fragment.lower() in reason_blob for fragment in test.expected_reason_fragments)

    passed = decision_ok and proof_ok and reasons_ok

    output = []
    output.append("=" * 72)
    output.append(f"TEST: {test.name}")
    output.append("-" * 72)
    output.append(f"Expected Decision      : {test.expected_decision}")
    output.append(f"Actual Decision        : {result.decision}")
    output.append(f"Decision Match         : {'PASS' if decision_ok else 'FAIL'}")
    output.append("")
    output.append(f"Expected Proof Complete: {test.expected_proof_complete}")
    output.append(f"Actual Proof Complete  : {result.proof_complete}")
    output.append(f"Proof Match            : {'PASS' if proof_ok else 'FAIL'}")
    output.append("")
    output.append(f"Expected Reason Parts  : {test.expected_reason_fragments}")
    output.append(f"Actual Reasons         : {result.reasons}")
    output.append(f"Reason Match           : {'PASS' if reasons_ok else 'FAIL'}")
    output.append("")
    output.append(f"OVERALL RESULT         : {'PASS' if passed else 'FAIL'}")

    return passed, "\n".join(output)


# ----------------------------------------------------------------------
# Test Mutators
# ----------------------------------------------------------------------

def baseline_approval(sig: PacSignal) -> PacSignal:
    return sig


def insufficient_evidence(sig: PacSignal) -> PacSignal:
    return replace(sig, evidence_level=EvidenceLevel.L4_REPRODUCIBLE_NON_MUTATING)


def failed_constraint(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        constraints=replace(sig.constraints, distinctness=False),
    )


def missing_stage(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        stages=replace(sig.stages, global_confirmation=False),
    )


def known_failure_present(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        failures=replace(sig.failures, known_failures=["KNOWN_DUPLICATION_FAILURE"]),
    )


def contradiction_present(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        failures=replace(sig.failures, contradiction_detected=True),
    )


def temporal_invalidation(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        temporal=replace(sig.temporal, current_state_id="STATE-B"),
    )


def r4_not_enough_cycles(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        risk_level=RiskLevel.R4_SYSTEM_CRITICAL,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        temporal=replace(sig.temporal, stable_multi_cycle_count=1),
    )


def r4_enough_cycles(sig: PacSignal) -> PacSignal:
    return replace(
        sig,
        risk_level=RiskLevel.R4_SYSTEM_CRITICAL,
        evidence_level=EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
        temporal=replace(sig.temporal, stable_multi_cycle_count=3),
    )


# ----------------------------------------------------------------------
# Test Suite
# ----------------------------------------------------------------------

def build_test_suite() -> List[TestCase]:
    return [
        TestCase(
            name="01_baseline_approval_path",
            mutate=baseline_approval,
            expected_decision=EnforcementDecision.APPROVE,
            expected_proof_complete=True,
            expected_reason_fragments=["proof complete"],
        ),
        TestCase(
            name="02_insufficient_evidence_should_halt",
            mutate=insufficient_evidence,
            expected_decision=EnforcementDecision.HALT,
            expected_proof_complete=False,
            expected_reason_fragments=["insufficient evidence level", "proof incomplete"],
        ),
        TestCase(
            name="03_failed_constraint_should_reject",
            mutate=failed_constraint,
            expected_decision=EnforcementDecision.REJECT,
            expected_proof_complete=False,
            expected_reason_fragments=["constraint failure detected"],
        ),
        TestCase(
            name="04_missing_stage_should_halt",
            mutate=missing_stage,
            expected_decision=EnforcementDecision.HALT,
            expected_proof_complete=False,
            expected_reason_fragments=["missing stages", "proof incomplete"],
        ),
        TestCase(
            name="05_known_failure_should_halt",
            mutate=known_failure_present,
            expected_decision=EnforcementDecision.HALT,
            expected_proof_complete=False,
            expected_reason_fragments=["failure condition present", "proof incomplete"],
        ),
        TestCase(
            name="06_contradiction_should_halt",
            mutate=contradiction_present,
            expected_decision=EnforcementDecision.HALT,
            expected_proof_complete=False,
            expected_reason_fragments=["failure condition present", "proof incomplete"],
        ),
        TestCase(
            name="07_temporal_invalidation_should_halt",
            mutate=temporal_invalidation,
            expected_decision=EnforcementDecision.HALT,
            expected_proof_complete=False,
            expected_reason_fragments=["temporal invalidation", "proof incomplete"],
        ),
        TestCase(
            name="08_r4_without_enough_cycles_should_halt",
            mutate=r4_not_enough_cycles,
            expected_decision=EnforcementDecision.HALT,
            expected_proof_complete=False,
            expected_reason_fragments=["insufficient multi-cycle validation", "proof incomplete"],
        ),
        TestCase(
            name="09_r4_with_enough_cycles_should_approve",
            mutate=r4_enough_cycles,
            expected_decision=EnforcementDecision.APPROVE,
            expected_proof_complete=True,
            expected_reason_fragments=["proof complete"],
        ),
    ]


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:
    engine = PacEngine()
    suite = build_test_suite()

    passed_count = 0
    failed_count = 0
    failed_names: List[str] = []

    print("=" * 72)
    print("PAC ENGINE v1 DETERMINISTIC TEST HARNESS")
    print("=" * 72)
    print("Target Artifact: pac_engine_v1_0_core.py")
    print("Harness Mode   : deterministic validation")
    print("")

    for test in suite:
        passed, report = run_test(engine, test)
        print(report)
        print("")

        if passed:
            passed_count += 1
        else:
            failed_count += 1
            failed_names.append(test.name)

    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    print(f"Total Tests : {len(suite)}")
    print(f"Passed      : {passed_count}")
    print(f"Failed      : {failed_count}")

    if failed_names:
        print("Failed Tests:")
        for name in failed_names:
            print(f"- {name}")
    else:
        print("All tests passed.")

    print("=" * 72)


if __name__ == "__main__":
    main()
