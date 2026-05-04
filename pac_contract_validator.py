import json
import sys
from pathlib import Path


CONTRACT_PATH = Path(__file__).parent / "contracts" / "pac_frozen_contract_v1.json"


def load_json(path):
    try:
        return json.loads(Path(path).read_text()), None
    except Exception as e:
        return None, f"Failed to load JSON: {e}"


def load_contract():
    try:
        return json.loads(CONTRACT_PATH.read_text())
    except Exception as e:
        print(f"ERROR: Could not load contract: {e}")
        sys.exit(3)



def validate_temporal_validity(payload, contract):
    import time

    temporal = contract.get("temporal", {})
    if not temporal.get("enabled", False):
        return []

    timestamp_field = temporal.get("timestamp_field", "proof_timestamp")
    required_fields = temporal.get("required_fields", [])
    max_age_seconds = temporal.get("max_age_seconds")

    errors = []

    for field in required_fields:
        if field not in payload:
            errors.append(f"temporal missing required field: {field}")

    if errors:
        return errors

    proof_timestamp = payload.get(timestamp_field)

    if not isinstance(proof_timestamp, int):
        return [f"temporal.{timestamp_field} must be int epoch seconds"]

    if not isinstance(max_age_seconds, int):
        return ["temporal.max_age_seconds must be int"]

    now = int(time.time())

    if proof_timestamp > now:
        return [f"temporal.{timestamp_field} cannot be in the future"]

    if now - proof_timestamp > max_age_seconds:
        return [f"temporal proof expired: age_seconds={now - proof_timestamp}, max_age_seconds={max_age_seconds}"]

    return []


def validate_against_contract(payload, contract, path='payload'):
    errors = []

    required_fields = contract.get('required_fields', [])

    for field in required_fields:
        if field not in payload:
            errors.append(f'{path}: missing required field: {field}')

    # Basic type enforcement, if defined in contract.
    field_types = contract.get('field_types', {})

    for field, expected_type in field_types.items():
        field_path = f'{path}.{field}'
        if field in payload:
            if expected_type == 'bool' and not isinstance(payload[field], bool):
                errors.append(f'{field_path} must be bool')
            elif expected_type == 'list' and not isinstance(payload[field], list):
                errors.append(f'{field_path} must be list')
            elif expected_type == 'dict' and not isinstance(payload[field], dict):
                errors.append(f'{field_path} must be dict')
            elif expected_type == 'str' and not isinstance(payload[field], str):
                errors.append(f'{field_path} must be string')
            elif expected_type == 'int' and not isinstance(payload[field], int):
                errors.append(f'{field_path} must be int')

    # PAC-aligned recursive nested contract validation.
    nested_contracts = contract.get('nested_contracts', {})

    if not isinstance(nested_contracts, dict):
        errors.append(f'{path}.nested_contracts must be dict')
    else:
        for field, nested_contract in nested_contracts.items():
            field_path = f'{path}.{field}'

            if field not in payload:
                continue

            if not isinstance(payload[field], dict):
                errors.append(f'{field_path} must be dict for nested validation')
                continue

            if not isinstance(nested_contract, dict):
                errors.append(f'{field_path} nested contract must be dict')
                continue

            errors.extend(validate_against_contract(payload[field], nested_contract, field_path))

    return errors



def validate_state_transition(payload, contract):
    st = contract.get("state_transitions", {})
    if not st.get("enabled", False):
        return []

    current_field = st.get("current_state_field")
    requested_field = st.get("requested_state_field")
    allowed = st.get("allowed", {})

    errors = []

    current = payload.get(current_field)
    requested = payload.get(requested_field)
    # --- PAC: STRICT TRANSITION ENFORCEMENT ---
    if not isinstance(allowed, dict):
        return ["state_transition.allowed must be a dict"]

    if current not in allowed:
        errors.append(f"undefined current state: {current}")
        return errors

    allowed_targets = allowed.get(current)

    if not isinstance(allowed_targets, list):
        errors.append(f"allowed transitions for '{current}' must be a list")
        return errors

    if requested not in allowed_targets:
        errors.append(
            f"invalid state transition: {current} -> {requested} "
            f"(allowed: {allowed_targets})"
        )
        return errors
    # --- END PAC ENFORCEMENT ---


    # ----------------------------------------
    # PAC: STATE EVOLUTION ENFORCEMENT
    # ----------------------------------------

    if current_field is None or requested_field is None:
        return ["state_transition config missing field definitions"]

    if current is None:
        errors.append(f"missing current state: {current_field}")
        return errors

    if requested is None:
        errors.append(f"missing requested state: {requested_field}")
        return errors

    if not isinstance(allowed, dict):
        return ["state_transition.allowed must be a dict"]

    if current not in allowed:
        errors.append(f"no transition rules defined for current state: {current}")
        return errors

    allowed_targets = allowed.get(current)

    if not isinstance(allowed_targets, list):
        errors.append(f"allowed transitions for '{current}' must be a list")
        return errors

    if requested not in allowed_targets:
        errors.append(
            f"invalid state transition: {current} -> {requested} "
            f"(allowed: {allowed_targets})"
        )

    return errors

    if current not in allowed:
        return [f"state_transition.unknown_current_state: {current}"]

    if requested not in allowed:
        return [f"state_transition.unknown_requested_state: {requested}"]

    if requested not in allowed.get(current, []):
        return [f"state_transition.invalid: {current} -> {requested}"]

    return []

def validate_required_fields(payload, required_fields):
    missing = []
    for field in required_fields:
        if field not in payload:
            missing.append(field)
    return missing


def validate_bool_map(section, name):
    errors = []
    if not isinstance(section, dict):
        return [f"{name} must be an object"]
    for k, v in section.items():
        if not isinstance(v, bool):
            errors.append(f"{name}.{k} must be bool")
    return errors


def validate_failures(section):
    errors = []
    if not isinstance(section, dict):
        return ["failures must be an object"]

    if not isinstance(section.get("known_failures", []), list):
        errors.append("failures.known_failures must be list")

    if not isinstance(section.get("suspected_failures", []), list):
        errors.append("failures.suspected_failures must be list")

    if not isinstance(section.get("contradiction_detected", False), bool):
        errors.append("failures.contradiction_detected must be bool")

    return errors



    if not isinstance(section.get("state_id_at_proof"), str):
        errors.append("temporal.state_id_at_proof must be string")

    if not isinstance(section.get("current_state_id"), str):
        errors.append("temporal.current_state_id must be string")

    if not isinstance(section.get("stable_multi_cycle_count"), int):
        errors.append("temporal.stable_multi_cycle_count must be int")

    return errors


def validate_payload(payload, contract):
    errors = []

    required = contract.get("required_fields", [])
    errors += validate_required_fields(payload, required)

    if "constraints" in payload:
        errors += validate_bool_map(payload["constraints"], "constraints")

    if "stages" in payload:
        errors += validate_bool_map(payload["stages"], "stages")

    if "failures" in payload:
        errors += validate_failures(payload["failures"])


    return errors



def validate_state_transition_contract(contract):
    st = contract.get("state_transitions", {})

    if not isinstance(st, dict):
        return ["state_transitions must be an object"]

    if not st.get("enabled", False):
        return []

    errors = []

    current_field = st.get("current_state_field")
    requested_field = st.get("requested_state_field")
    allowed = st.get("allowed")

    if not current_field or not requested_field:
        errors.append("state_transition missing field definitions")
        return errors

    if not isinstance(allowed, dict):
        return ["state_transition.allowed must be a dict"]

    # ----------------------------------------
    # PAC: GRAPH INTEGRITY ENFORCEMENT
    # ----------------------------------------

    entry_state = st.get("entry_state")
    terminal_state = st.get("terminal_state")

    if not isinstance(entry_state, str) or not entry_state:
        errors.append("state_transitions.entry_state must be a non-empty string")

    if not isinstance(terminal_state, str) or not terminal_state:
        errors.append("state_transitions.terminal_state must be a non-empty string")

    defined_states = set(allowed.keys())
    referenced_states = set()

    for src, targets in allowed.items():
        if not isinstance(targets, list):
            errors.append(f"allowed transitions for '{src}' must be a list")
            continue

        for t in targets:
            referenced_states.add(t)

    if entry_state and entry_state not in defined_states:
        errors.append(f"entry_state must be declared in allowed: {entry_state}")

    if terminal_state and terminal_state not in defined_states:
        errors.append(f"terminal_state must be declared in allowed: {terminal_state}")

    if terminal_state in defined_states and allowed.get(terminal_state) != []:
        errors.append(f"terminal_state must have no outgoing transitions: {terminal_state}")

    undefined = referenced_states - defined_states
    if undefined:
        errors.append(f"undefined states referenced: {list(undefined)}")

    for state, targets in allowed.items():
        if targets == [] and state != terminal_state:
            errors.append(f"non-terminal state has no outgoing transitions: {state}")

    unreachable_states = defined_states - referenced_states - {entry_state}
    if unreachable_states:
        errors.append(f"unreachable states detected: {list(unreachable_states)}")

    return errors

    state_contract_errors = validate_state_transition_contract(contract)
    if state_contract_errors:
        print(json.dumps({
            "valid": False,
            "errors": state_contract_errors
        }, indent=2))
        sys.exit(3)


    # PAC: contract integrity enforcement
    if not contract.get('required_fields') and not contract.get('field_types'):
        print(json.dumps({
            "valid": False,
            "errors": ["contract defines no enforceable rules"]
        }, indent=2))
        sys.exit(3)

    temporal_errors = validate_temporal_validity(payload, contract)

    if temporal_errors:
        print(json.dumps({
            "valid": False,
            "errors": temporal_errors
        }, indent=2))
        sys.exit(3)


    state_errors = validate_state_transition(payload, contract)
    if state_errors:
        print(json.dumps({
            "valid": False,
            "errors": state_errors
        }, indent=2))
        sys.exit(3)

    schema_errors = validate_against_contract(payload, contract)
    if schema_errors:
        print(json.dumps({
            "valid": False,
            "errors": schema_errors
        }, indent=2))
        sys.exit(3)


    errors = validate_payload(payload, contract)

    if errors:
        print(json.dumps({
            "valid": False,
            "errors": errors
        }, indent=2))
        sys.exit(1)

    print(json.dumps({
        "valid": True,
        "message": "Payload conforms to PAC contract"
    }, indent=2))
    sys.exit(0)



def main():
    if len(sys.argv) != 2:
        print("Usage: python pac_contract_validator.py <payload.json>")
        sys.exit(3)

    payload_path = sys.argv[1]

    payload, err = load_json(payload_path)
    if payload is None:
        print(err)
        sys.exit(3)

    if not isinstance(payload, dict):
        print(json.dumps({
            "valid": False,
            "errors": ["payload must be an object/dict"]
        }, indent=2))
        sys.exit(3)

    contract = load_contract()

    # PAC: contract integrity enforcement
    if not contract.get('required_fields') and not contract.get('field_types'):
        print(json.dumps({
            "valid": False,
            "errors": ["contract defines no enforceable rules"]
        }, indent=2))
        sys.exit(3)

    state_contract_errors = validate_state_transition_contract(contract)
    if state_contract_errors:
        print(json.dumps({
            "valid": False,
            "errors": state_contract_errors
        }, indent=2))
        sys.exit(3)

    temporal_errors = validate_temporal_validity(payload, contract)
    if temporal_errors:
        print(json.dumps({
            "valid": False,
            "errors": temporal_errors
        }, indent=2))
        sys.exit(3)

    state_errors = validate_state_transition(payload, contract)
    if state_errors:
        print(json.dumps({
            "valid": False,
            "errors": state_errors
        }, indent=2))
        sys.exit(3)

    schema_errors = validate_against_contract(payload, contract)
    if schema_errors:
        print(json.dumps({
            "valid": False,
            "errors": schema_errors
        }, indent=2))
        sys.exit(3)

    errors = validate_payload(payload, contract)
    if errors:
        print(json.dumps({
            "valid": False,
            "errors": errors
        }, indent=2))
        sys.exit(1)

    print(json.dumps({
        "valid": True,
        "message": "Payload conforms to PAC contract"
    }, indent=2))
    sys.exit(0)

if __name__ == "__main__":
    main()
