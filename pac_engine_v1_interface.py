from __future__ import annotations

from typing import Any, Dict

from pac_engine_v1_1_core import (
    PacEngine,
    PacSignal,
    ConstraintStatus,
    ValidationStages,
    FailureAnalysis,
    TemporalState,
    RiskLevel,
    EvidenceLevel,
    EnforcementDecision,
    EvaluationResult,
)


# PAC Engine Interface Layer v1
# Purpose:
# External input -> PacSignal -> canonical proof state -> enforcement result -> JSON-safe response
#
# Critical rule:
# This interface must not duplicate or override PAC proof logic.


def enum_to_name(value: Any) -> Any:
    if hasattr(value, "name"):
        return value.name
    return value


def build_signal(payload: Dict[str, Any]) -> PacSignal:
    return PacSignal(
        signal_id=payload["signal_id"],
        description=payload["description"],
        scope=payload["scope"],
        risk_level=RiskLevel[payload["risk_level"]],
        evidence_level=EvidenceLevel[payload["evidence_level"]],
        constraints=ConstraintStatus(**payload["constraints"]),
        stages=ValidationStages(**payload["stages"]),
        failures=FailureAnalysis(**payload["failures"]),
        temporal=TemporalState(**payload["temporal"]),
        metadata=payload.get("metadata", {}),
    )


def serialize_proof_state(proof_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: enum_to_name(value)
        for key, value in proof_state.items()
    }


def serialize_result(
    signal: PacSignal,
    result: EvaluationResult,
    proof_state: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "decision": result.decision.value,
        "proof_complete": result.proof_complete,
        "required_threshold": result.required_threshold.name,
        "reasons": result.reasons,
        "failed_constraints": result.failed_constraints,
        "missing_stages": result.missing_stages,
        "proof_state": serialize_proof_state(proof_state),
    }


def evaluate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    engine = PacEngine()

    try:
        signal = build_signal(payload)
        proof_state = engine.evaluate_proof_state(signal)
        result = engine.evaluate(signal)

        return serialize_result(signal, result, proof_state)

    except Exception as exc:
        return {
            "signal_id": payload.get("signal_id", "UNKNOWN"),
            "decision": EnforcementDecision.HALT.value,
            "proof_complete": False,
            "required_threshold": None,
            "reasons": [
                "Interface input error",
                str(exc),
            ],
            "failed_constraints": [],
            "missing_stages": [],
            "proof_state": {},
        }


if __name__ == "__main__":
    demo_payload = {
        "signal_id": "INTERFACE-DEMO-001",
        "description": "Valid interface signal",
        "scope": "interface_demo",
        "risk_level": "R3_CROSS_COMPONENT",
        "evidence_level": "L5_VERIFIED_EXECUTION",
        "constraints": {
            "distinctness": True,
            "boundary_integrity": True,
            "structural_independence": True,
            "referential_integrity": True,
            "context_validity": True,
            "non_aliasing": True,
            "completeness": True,
        },
        "stages": {
            "signal_detection": True,
            "structural_validation": True,
            "equality_consistency_check": True,
            "constraint_verification": True,
            "failure_mode_analysis": True,
            "global_confirmation": True,
            "enforcement_decision_ready": True,
        },
        "failures": {
            "known_failures": [],
            "suspected_failures": [],
            "contradiction_detected": False,
        },
        "temporal": {
            "state_id_at_proof": "STATE-A",
            "current_state_id": "STATE-A",
            "stable_multi_cycle_count": 2,
        },
        "metadata": {
            "source": "interface_demo",
        },
    }

    print(evaluate_payload(demo_payload))
