import json
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path("/workspaces/pac-engine")
EXAMPLES = ROOT / "examples"
API_URL = "http://127.0.0.1:8000/validate"

TEST_FILES = [
    "approve_payload.json",
    "halt_payload.json",
    "reject_payload.json",
    "missing_fields.json",
    "bad_nested_payload.json",
    "invalid_state_transition_payload.json",
]

EXPECTED_HTTP_BY_CATEGORY = {
    "state_transition": 409,
    "payload_type": 400,
    "validation": 400,
    "schema": 422,
    "contract": 500,
}

def refresh_timestamps():
    now = int(time.time())
    for p in EXAMPLES.glob("*.json"):
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            data["proof_timestamp"] = now
            p.write_text(json.dumps(data, indent=2) + "\n")

def normalize_cli_json(data):
    data = dict(data)
    data.pop("exit_code", None)
    return data

def expected_http(result):
    if result.get("valid") is True:
        return 200

    classifications = result.get("error_classification") or []
    if classifications:
        category = classifications[0].get("category")
        return EXPECTED_HTTP_BY_CATEGORY.get(category, 400)

    return 400

def run_cli(path):
    proc = subprocess.run(
        ["python", "pac_contract_validator.py", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"CLI did not return JSON for {path.name}\n"
            f"exit={proc.returncode}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )

    return proc.returncode, normalize_cli_json(body)

def run_api(path):
    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json"},
        data=path.read_text(),
        timeout=10,
    )

    try:
        body = response.json()
    except Exception:
        raise RuntimeError(
            f"API did not return JSON for {path.name}\n"
            f"http={response.status_code}\n"
            f"body={response.text}"
        )

    return response.status_code, body

print("=" * 70)
print("PAC CLI/API CANONICAL PARITY TEST — TRANSPORT-AWARE")
print("=" * 70)

refresh_timestamps()
print("TIMESTAMPS REFRESHED")

failures = 0

for name in TEST_FILES:
    path = EXAMPLES / name

    cli_exit, cli_json = run_cli(path)
    api_http, api_json = run_api(path)

    json_parity = cli_json == api_json
    expected_status = expected_http(cli_json)
    transport_ok = api_http == expected_status

    print("=" * 70)
    print(f"TEST: {name}")
    print("-" * 70)
    print(f"CLI EXIT              : {cli_exit}")
    print(f"API HTTP              : {api_http}")
    print(f"EXPECTED API HTTP     : {expected_status}")
    print(f"CANONICAL JSON PARITY : {json_parity}")
    print(f"TRANSPORT MAPPING OK  : {transport_ok}")

    if not json_parity or not transport_ok:
        failures += 1
        print()
        print("CLI JSON:")
        print(json.dumps(cli_json, indent=2))
        print()
        print("API JSON:")
        print(json.dumps(api_json, indent=2))

if failures:
    print("=" * 70)
    print(f"GLOBAL RESULT: FAIL — {failures} mismatch(es)")
    raise SystemExit(1)

print("=" * 70)
print("GLOBAL RESULT: PASS")
print("PAC API IS CANONICALLY BOUND TO CLI VALIDATOR")
print("HTTP TRANSPORT MAPPING IS VALID")
print("=" * 70)
