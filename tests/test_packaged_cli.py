"""Verify installable CLI from an isolated location, preserving canonical behavior."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PackagedCliTests(unittest.TestCase):
    def test_installed_cli_matches_canonical_validator(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "site"
            install = subprocess.run([sys.executable, "-m", "pip", "install",
                "--no-deps", "--no-build-isolation", "--target", str(target), str(root)],
                capture_output=True, text=True, timeout=90)
            self.assertEqual(install.returncode, 0, install.stderr)
            payload = base / "input.json"
            payload.write_text("{}")
            env = {**os.environ, "PYTHONPATH": str(target)}
            invocation = subprocess.run([sys.executable, "-c",
                "from pac_entrypoint import main; import sys; "
                "sys.argv=['pac','validate',sys.argv[1]]; main()", str(payload)],
                cwd=base, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(invocation.returncode, 3)
            output = json.loads(invocation.stdout)
            self.assertFalse(output["valid"])
            self.assertTrue(output["errors"])
            self.assertTrue((target / "contracts" / "pac_frozen_contract_v1.json").is_file())


if __name__ == "__main__":
    unittest.main()
