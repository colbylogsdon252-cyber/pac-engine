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



def _halt_interface_error(signal_id, message):
    return {
        "signal_id": signal_id,
        "decision": "HALT",
        "proof_complete": False,
        "required_threshold": None,
        "reasons": ["Interface input error", message],
        "failed_constraints": [],
        "missing_stages": [],
        "proof_state": {},
    }


def _require_dict(payload, key):
    value = payload.get(key)
    if not isinstance(value, dict):
        return False, f'"{key}" must be an object/dict'
    return True, None


def _require_bool_map(section, section_name):
    for key, value in section.items():
        if type(value) is not bool:
            return False, f'"{section_name}.{key}" must be bool'
    return True, None


def _validate_interface_schema(payload):
    if not isinstance(payload, dict):
        return False, "payload must be an object/dict"

    signal_id = payload.get("signal_id", "UNKNOWN")

    for required in ("risk_level", "evidence_level", "constraints", "stages", "failures", "temporal"):
        if required not in payload:
            return False, f'missing required field "{required}"'

    for section_name in ("constraints", "stages", "failures", "temporal"):
        ok, error = _require_dict(payload, section_name)
        if not ok:
            return False, error

    ok, error = _require_bool_map(payload["constraints"], "constraints")
    if not ok:
        return False, error

    ok, error = _require_bool_map(payload["stages"], "stages")
    if not ok:
        return False, error

    failures = payload["failures"]
    if not isinstance(failures.get("known_failures", []), list):
        return False, '"failures.known_failures" must be list'
    if not isinstance(failures.get("suspected_failures", []), list):
        return False, '"failures.suspected_failures" must be list'
    if type(failures.get("contradiction_detected", False)) is not bool:
        return False, '"failures.contradiction_detected" must be bool'

    temporal = payload["temporal"]
    if not isinstance(temporal.get("state_id_at_proof"), str):
        return False, '"temporal.state_id_at_proof" must be string'
    if not isinstance(temporal.get("current_state_id"), str):
        return False, '"temporal.current_state_id" must be string'
    if type(temporal.get("stable_multi_cycle_count")) is not int:
        return False, '"temporal.stable_multi_cycle_count" must be int'

    return True, None

def evaluate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    schema_valid, schema_error = _validate_interface_schema(payload)
    if not schema_valid:
        return _halt_interface_error(payload.get("signal_id", "UNKNOWN") if isinstance(payload, dict) else "UNKNOWN", schema_error)
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
