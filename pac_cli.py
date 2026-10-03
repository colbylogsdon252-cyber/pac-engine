import json
import sys
from pathlib import Path

from pac_contract_validator import validate_canonical


def load_json(path):
    try:
        return json.loads(Path(path).read_text()), None
    except Exception as exc:
        return None, str(exc)


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "validate":
        print("Usage: pac validate <input.json>")
        sys.exit(3)

    payload, error = load_json(sys.argv[2])
    if error is not None:
        print(json.dumps({
            "valid": False,
            "errors": [f"Failed to load JSON: {error}"],
            "error_classification": [],
            "exit_code": 3,
        }, indent=2))
        sys.exit(3)

    result = validate_canonical(payload)
    print(json.dumps(result, indent=2))
    sys.exit(result.get("exit_code", 3))


if __name__ == "__main__":
    main()
