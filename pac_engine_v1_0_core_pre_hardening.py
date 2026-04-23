from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import List, Optional, Dict, Any


# PAC Engine v1.0-core
# Status: FROZEN PROTOTYPE
# Canonical artifact name: pac_engine_v1_0_core.py


class EvidenceLevel(IntEnum):
    L0_NONE = 0
    L1_ASSUMPTION = 1
    L2_STATIC_INSPECTION = 2
    L3_OBSERVATIONAL_RUNTIME = 3
    L4_REPRODUCIBLE_NON_MUTATING = 4
    L5_VERIFIED_EXECUTION = 5
    L6_STABLE_MULTI_CYCLE_PROOF = 6


class RiskLevel(IntEnum):
    R1_NON_MUTATING = 1
    R2_LOCAL_REVERSIBLE = 2
    R3_CROSS_COMPONENT = 3
    R4_SYSTEM_CRITICAL = 4


class EnforcementDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    HALT = "HALT"


THRESHOLD_MATRIX: Dict[RiskLevel, EvidenceLevel] = {
    RiskLevel.R1_NON_MUTATING: EvidenceLevel.L2_STATIC_INSPECTION,
    RiskLevel.R2_LOCAL_REVERSIBLE: EvidenceLevel.L4_REPRODUCIBLE_NON_MUTATING,
    RiskLevel.R3_CROSS_COMPONENT: EvidenceLevel.L5_VERIFIED_EXECUTION,
    RiskLevel.R4_SYSTEM_CRITICAL: EvidenceLevel.L6_STABLE_MULTI_CYCLE_PROOF,
}


@dataclass
class ConstraintStatus:
    distinctness: bool = True
    boundary_integrity: bool = True
    structural_independence: bool = True
    referential_integrity: bool = True
    context_validity: bool = True
    non_aliasing: bool = True
    completeness: bool = True

    def all_satisfied(self) -> bool:
        return all(vars(self).values())

    def failed_constraints(self) -> List[str]:
        return [k for k, v in vars(self).items() if not v]


@dataclass
class ValidationStages:
    signal_detection: bool = False
    structural_validation: bool = False
    equality_consistency_check: bool = False
    constraint_verification: bool = False
    failure_mode_analysis: bool = False
    global_confirmation: bool = False
    enforcement_decision_ready: bool = False

    def all_passed(self) -> bool:
        return all(vars(self).values())

    def missing_stages(self) -> List[str]:
        return [k for k, v in vars(self).items() if not v]


@dataclass
class FailureAnalysis:
    known_failures: List[str] = field(default_factory=list)
    suspected_failures: List[str] = field(default_factory=list)
    contradiction_detected: bool = False

    def has_blocking_failure(self) -> bool:
        return bool(self.known_failures or self.suspected_failures or self.contradiction_detected)


@dataclass
class TemporalState:
    state_id_at_proof: Optional[str] = None
    current_state_id: Optional[str] = None
    stable_multi_cycle_count: int = 0

    def state_valid(self) -> bool:
        return self.state_id_at_proof == self.current_state_id


@dataclass
class PacSignal:
    signal_id: str
    description: str
    scope: str
    risk_level: RiskLevel
    evidence_level: EvidenceLevel
    constraints: ConstraintStatus
    stages: ValidationStages
    failures: FailureAnalysis
    temporal: TemporalState
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    decision: EnforcementDecision
    required_threshold: EvidenceLevel
    proof_complete: bool
    reasons: List[str]
    failed_constraints: List[str]
    missing_stages: List[str]


class PacEngine:

    def required_threshold(self, risk_level: RiskLevel) -> EvidenceLevel:
        return THRESHOLD_MATRIX[risk_level]

    def proof_complete(self, signal: PacSignal) -> bool:
        threshold = self.required_threshold(signal.risk_level)

        if not signal.stages.all_passed():
            return False
        if not signal.constraints.all_satisfied():
            return False
        if signal.evidence_level < threshold:
            return False
        if signal.failures.has_blocking_failure():
            return False
        if not signal.temporal.state_valid():
            return False
        if (
            signal.risk_level == RiskLevel.R4_SYSTEM_CRITICAL
            and signal.temporal.stable_multi_cycle_count < 2
        ):
            return False
        return True

    def evaluate(self, signal: PacSignal) -> EvaluationResult:
        threshold = self.required_threshold(signal.risk_level)
        reasons: List[str] = []

        failed_constraints = signal.constraints.failed_constraints()
        missing_stages = signal.stages.missing_stages()

        if failed_constraints:
            reasons.append("Constraint failure detected")
            return EvaluationResult(
                EnforcementDecision.REJECT,
                threshold,
                False,
                reasons,
                failed_constraints,
                missing_stages,
            )

        if missing_stages:
            reasons.append(f"Missing stages: {missing_stages}")

        if signal.evidence_level < threshold:
            reasons.append("Insufficient evidence level")

        if signal.failures.has_blocking_failure():
            reasons.append("Failure condition present")

        if not signal.temporal.state_valid():
            reasons.append("Temporal invalidation")

        if (
            signal.risk_level == RiskLevel.R4_SYSTEM_CRITICAL
            and signal.temporal.stable_multi_cycle_count < 2
        ):
            reasons.append("Insufficient multi-cycle validation")

        proof = self.proof_complete(signal)

        if proof:
            decision = EnforcementDecision.APPROVE
            reasons.append("Proof complete")
        else:
            decision = EnforcementDecision.HALT
            reasons.append("Proof incomplete")

        return EvaluationResult(
            decision,
            threshold,
            proof,
            reasons,
            failed_constraints,
            missing_stages,
        )


# ---------- DEMO ----------

if __name__ == "__main__":

    signal = PacSignal(
        signal_id="PAC-DEMO-1",
        description="Test signal",
        scope="demo",
        risk_level=RiskLevel.R3_CROSS_COMPONENT,
        evidence_level=EvidenceLevel.L5_VERIFIED_EXECUTION,
        constraints=ConstraintStatus(),
        stages=ValidationStages(
            signal_detection=True,
            structural_validation=True,
            equality_consistency_check=True,
            constraint_verification=True,
            failure_mode_analysis=True,
            global_confirmation=True,
            enforcement_decision_ready=True,
        ),
        failures=FailureAnalysis(),
        temporal=TemporalState(
            state_id_at_proof="A",
            current_state_id="A",
            stable_multi_cycle_count=2,
        ),
    )

    engine = PacEngine()
    result = engine.evaluate(signal)

    print("Decision:", result.decision)
    print("Proof Complete:", result.proof_complete)
    print("Reasons:")
    for r in result.reasons:
        print("-", r)
