"""Fresh-process PAC deployment smoke verification (no production dispatch)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        secret = base / "keyring.json"
        secret.write_text(json.dumps({"keys": [{"key_id": "smoke-1", "secret": "s" * 40}]}))
        secret.chmod(0o600)
        database = base / "pac.sqlite3"
        env = {**os.environ, "PAC_DEPLOYMENT_MODE": "production",
               "PAC_PROOF_ACTIVE_KEY_ID": "smoke-1",
               "PAC_PROOF_KEYRING_FILE": str(secret)}
        startup = """
from pac_api import validate_startup_configuration
from pac_proof_token import issue_proof_token, verify_execution_authorization
from pac_protected_execution import DurableExecutionStore
from pac_external_effect import ExternalEffectStore
from pac_redispatch_recovery import RedispatchAuthorizationStore
import json, os, time
keyring = validate_startup_configuration()
payload = {
    "action": True,
    "target": {"id": "T-001", "type": "example"},
    "proof_timestamp": int(time.time()),
    "current_state": "draft",
    "requested_state": "validated",
    "state_id_at_proof": "STATE-A",
    "current_state_id": "STATE-A",
}
token = issue_proof_token(payload, keyring)
assert verify_execution_authorization(payload, token, keyring)["authorized"]
db = os.environ["PAC_SMOKE_DB"]
execution = DurableExecutionStore(db)
effects = ExternalEffectStore(db)
recovery = RedispatchAuthorizationStore(db)
assert execution.claim("smoke-execution")
assert execution.state("smoke-execution") == "claimed"
print("SMOKE_READY")
"""
        env["PAC_SMOKE_DB"] = str(database)
        result = subprocess.run([sys.executable, "-c", startup], cwd=ROOT,
                                env=env, capture_output=True, text=True, timeout=25)
        assert result.returncode == 0, result.stderr
        assert "SMOKE_READY" in result.stdout
        restart = subprocess.run([sys.executable, "-c",
            "from pac_protected_execution import DurableExecutionStore; import os; "
            "s=DurableExecutionStore(os.environ['PAC_SMOKE_DB']); "
            "assert s.state('smoke-execution')=='claimed'; "
            "assert not s.claim('smoke-execution')"], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=25)
        assert restart.returncode == 0, restart.stderr
        for bad in (
            {**env, "PAC_PROOF_ACTIVE_KEY_ID": "unknown"},
            {k: v for k, v in env.items() if k != "PAC_PROOF_KEYRING_FILE"},
        ):
            failure = subprocess.run([sys.executable, "-c",
                "from pac_api import validate_startup_configuration; "
                "validate_startup_configuration()"], cwd=ROOT, env=bad,
                capture_output=True, text=True, timeout=25)
            assert failure.returncode != 0, "invalid production startup was accepted"
        print("PAC deployment smoke: PASS (key mount, token, persistent restart, fail-closed startup)")


if __name__ == "__main__":
    run()
