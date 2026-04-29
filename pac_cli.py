import sys
import json
from pathlib import Path

from pac_engine_v1_interface import evaluate_payload


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        print(json.dumps({
            "decision": "HALT",
            "reason": "Invalid JSON input",
            "error": str(e)
        }, indent=2))
        sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print("Usage: pac validate <input.json>")
        sys.exit(1)

    command = sys.argv[1]
    file_path = sys.argv[2]

    if command != "validate":
        print("Unknown command:", command)
        sys.exit(1)

    payload = load_json(file_path)

    result = evaluate_payload(payload)

    print(json.dumps(result, indent=2))
    decision = result.get("decision")

    if decision == "APPROVE":
        exit_code = 0
    elif decision == "HALT":
        exit_code = 1
    elif decision == "REJECT":
        exit_code = 2
    else:
        exit_code = 3

    sys.exit(exit_code)



if __name__ == "__main__":
    main()
