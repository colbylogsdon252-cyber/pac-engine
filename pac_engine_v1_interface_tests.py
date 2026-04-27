from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from pac_engine_v1_interface import evaluate_payload


def build_valid_payload() -> Dict[str, Any]:
    return {
        "signal_id": "IFACE-VALID-BASELINE",
        "description": "Valid interface signal",
        "scope": "interface_test",
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
            "source": "interface_test_harness",
        },
    }


def make_cases() -> List[Tuple[str, Dict[str, Any], str, bool]]:
    valid = build_valid_payload()

    missing_risk = deepcopy(valid)
    missing_risk["signal_id"] = "IFACE-TEST-001-MISSING-RISK"
    missing_risk.pop("risk_level")

    invalid_enum = deepcopy(valid)
    invalid_enum["signal_id"] = "IFACE-TEST-002-INVALID-ENUM"
    invalid_enum["risk_level"] = "INVALID_RISK"

    constraint_fail = deepcopy(valid)
    constraint_fail["signal_id"] = "IFACE-TEST-003-CONSTRAINT-FAIL"
    constraint_fail["constraints"]["completeness"] = False

    temporal_fail = deepcopy(valid)
    temporal_fail["signal_id"] = "IFACE-TEST-004-TEMPORAL-FAIL"
    temporal_fail["temporal"]["current_state_id"] = "STATE-B"

    valid_case = deepcopy(valid)
    valid_case["signal_id"] = "IFACE-TEST-005-VALID-APPROVE"

    return [
        ("missing_field_should_halt", missing_risk, "HALT", False),
        ("invalid_enum_should_halt", invalid_enum, "HALT", False),
        ("constraint_failure_should_reject", constraint_fail, "REJECT", False),
        ("temporal_failure_should_halt", temporal_fail, "HALT", False),
        ("valid_signal_should_approve", valid_case, "APPROVE", True),
    ]


def is_json_safe(result: Dict[str, Any]) -> bool:
    try:
        json.dumps(result)
        return True
    except TypeError:
        return False


def run_case(name: str, payload: Dict[str, Any], expected_decision: str, expected_proof: bool) -> bool:
    result = evaluate_payload(payload)

    decision_ok = result.get("decision") == expected_decision
    proof_ok = result.get("proof_complete") is expected_proof
    json_ok = is_json_safe(result)

    passed = decision_ok and proof_ok and json_ok

    print("=" * 72)
    print(f"INTERFACE TEST : {name}")
    print("-" * 72)
    print(f"Signal ID          : {result.get('signal_id')}")
    print(f"Expected Decision  : {expected_decision}")
    print(f"Actual Decision    : {result.get('decision')}")
    print(f"Decision Match     : {'PASS' if decision_ok else 'FAIL'}")
    print()
    print(f"Expected Proof     : {expected_proof}")
    print(f"Actual Proof       : {result.get('proof_complete')}")
    print(f"Proof Match        : {'PASS' if proof_ok else 'FAIL'}")
    print()
    print(f"JSON Safe          : {'PASS' if json_ok else 'FAIL'}")
    print(f"Reasons            : {result.get('reasons')}")
    print(f"Proof State        : {result.get('proof_state')}")
    print()
    print(f"OVERALL RESULT     : {'PASS' if passed else 'FAIL'}")

    return passed


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 72)
    print("PAC ENGINE v1 INTERFACE TEST HARNESS")
    print("=" * 72)

    for name, payload, expected_decision, expected_proof in make_cases():
        ok = run_case(name, payload, expected_decision, expected_proof)
        if ok:
            passed += 1
        else:
            failed += 1

    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    print(f"Total Tests : {passed + failed}")
    print(f"Passed      : {passed}")
    print(f"Failed      : {failed}")

    if failed:
        print("INTERFACE RESULT: FAIL")
        raise SystemExit(1)

    print("INTERFACE RESULT: PASS")
    print("All interface tests passed.")


if __name__ == "__main__":
    main()
