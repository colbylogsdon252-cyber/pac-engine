from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Tuple

from pac_engine_v1_interface import evaluate_payload


def valid_payload() -> Dict[str, Any]:
    return {
        "signal_id": "IFACE-ATTACK-BASELINE",
        "description": "Valid baseline payload for interface attack testing",
        "scope": "interface_attack_test",
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
            "source": "interface_attack_test",
        },
    }


def attack_cases() -> List[Tuple[str, Dict[str, Any]]]:
    base = valid_payload()

    missing_constraints = deepcopy(base)
    missing_constraints["signal_id"] = "IFACE-ATTACK-001-MISSING-CONSTRAINTS"
    missing_constraints.pop("constraints")

    missing_stages = deepcopy(base)
    missing_stages["signal_id"] = "IFACE-ATTACK-002-MISSING-STAGES"
    missing_stages.pop("stages")

    string_boolean = deepcopy(base)
    string_boolean["signal_id"] = "IFACE-ATTACK-003-STRING-BOOLEAN"
    string_boolean["constraints"]["completeness"] = "True"

    poisoned_failure_list = deepcopy(base)
    poisoned_failure_list["signal_id"] = "IFACE-ATTACK-004-POISONED-FAILURE-LIST"
    poisoned_failure_list["failures"]["known_failures"] = "KNOWN_FAILURE"

    injected_proof_true = deepcopy(base)
    injected_proof_true["signal_id"] = "IFACE-ATTACK-005-INJECTED-PROOF-TRUE"
    injected_proof_true["proof_complete"] = True
    injected_proof_true["proof_state"] = {"proof": True}
    injected_proof_true["decision"] = "APPROVE"
    injected_proof_true["constraints"]["completeness"] = False

    fake_threshold_override = deepcopy(base)
    fake_threshold_override["signal_id"] = "IFACE-ATTACK-006-FAKE-THRESHOLD-OVERRIDE"
    fake_threshold_override["required_threshold"] = "L1_ASSUMPTION"
    fake_threshold_override["evidence_level"] = "L1_ASSUMPTION"

    temporal_type_poison = deepcopy(base)
    temporal_type_poison["signal_id"] = "IFACE-ATTACK-007-TEMPORAL-TYPE-POISON"
    temporal_type_poison["temporal"]["stable_multi_cycle_count"] = "2"

    nested_shape_poison = deepcopy(base)
    nested_shape_poison["signal_id"] = "IFACE-ATTACK-008-NESTED-SHAPE-POISON"
    nested_shape_poison["constraints"] = ["distinctness", "completeness"]

    contradiction_masked = deepcopy(base)
    contradiction_masked["signal_id"] = "IFACE-ATTACK-009-CONTRADICTION-MASKED"
    contradiction_masked["failures"]["contradiction_detected"] = True
    contradiction_masked["metadata"]["claimed_safe"] = True

    high_evidence_missing_stage = deepcopy(base)
    high_evidence_missing_stage["signal_id"] = "IFACE-ATTACK-010-HIGH-EVIDENCE-MISSING-STAGE"
    high_evidence_missing_stage["risk_level"] = "R1_NON_MUTATING"
    high_evidence_missing_stage["evidence_level"] = "L6_STABLE_MULTI_CYCLE_PROOF"
    high_evidence_missing_stage["stages"]["global_confirmation"] = False

    return [
        ("missing_constraints_block", missing_constraints),
        ("missing_stages_block", missing_stages),
        ("string_boolean_poison", string_boolean),
        ("poisoned_failure_list", poisoned_failure_list),
        ("injected_proof_true", injected_proof_true),
        ("fake_threshold_override", fake_threshold_override),
        ("temporal_type_poison", temporal_type_poison),
        ("nested_shape_poison", nested_shape_poison),
        ("contradiction_masked", contradiction_masked),
        ("high_evidence_missing_stage", high_evidence_missing_stage),
    ]


def json_safe(result: Dict[str, Any]) -> bool:
    try:
        json.dumps(result)
        return True
    except TypeError:
        return False


def false_approve(result: Dict[str, Any]) -> bool:
    return result.get("decision") == "APPROVE" and result.get("proof_complete") is True


def run_case(name: str, payload: Dict[str, Any]) -> bool:
    result = evaluate_payload(payload)

    no_false_approve = not false_approve(result)
    json_ok = json_safe(result)
    safe_decision = result.get("decision") in {"HALT", "REJECT"}

    passed = no_false_approve and json_ok and safe_decision

    print("=" * 72)
    print(f"INTERFACE ATTACK : {name}")
    print("-" * 72)
    print(f"Signal ID        : {result.get('signal_id')}")
    print(f"Decision         : {result.get('decision')}")
    print(f"Proof Complete   : {result.get('proof_complete')}")
    print(f"Safe Decision    : {'PASS' if safe_decision else 'FAIL'}")
    print(f"False Approve    : {'NO' if no_false_approve else 'YES'}")
    print(f"JSON Safe        : {'PASS' if json_ok else 'FAIL'}")
    print(f"Reasons          : {result.get('reasons')}")
    print(f"Proof State      : {result.get('proof_state')}")
    print()
    print(f"OVERALL RESULT   : {'PASS' if passed else 'FAIL'}")

    return passed


def main() -> None:
    passed = 0
    failed = 0
    false_approves = 0

    print("=" * 72)
    print("PAC ENGINE v1 INTERFACE ATTACK TEST HARNESS")
    print("=" * 72)

    for name, payload in attack_cases():
        result = evaluate_payload(payload)
        if false_approve(result):
            false_approves += 1

        ok = run_case(name, payload)
        if ok:
            passed += 1
        else:
            failed += 1

    print("=" * 72)
    print("FINAL SUMMARY")
    print("=" * 72)
    print(f"Total Attacks   : {passed + failed}")
    print(f"Passed          : {passed}")
    print(f"Failed          : {failed}")
    print(f"False Approves  : {false_approves}")

    if failed or false_approves:
        print("INTERFACE ATTACK RESULT: FAIL")
        raise SystemExit(1)

    print("INTERFACE ATTACK RESULT: PASS")
    print("No false approvals detected under interface attack conditions.")


if __name__ == "__main__":
    main()
