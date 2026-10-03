# PAC Provenance Archive

This directory contains historical PAC engine implementations, frozen copies, legacy interfaces, historical test/attack harnesses, and recorded failure artifacts retained for provenance.

## Authority boundary

Nothing under `provenance/` is part of the active PAC MVP runtime or canonical validation path. Production callers must not import modules from this directory.

The active runtime remains at the repository root:
- `pac_contract_validator.py` — canonical validation authority via `validate_canonical()`
- `pac_cli.py` — thin CLI transport
- `pac_api.py` — thin API transport
- `pac_proof_token.py`
- `pac_protected_execution.py`
- `pac_external_effect.py`
- `pac_downstream_adapter.py`
- `pac_redispatch_recovery.py`

Historical files are preserved here so implementation history and adversarial-development evidence remain reviewable without presenting legacy engines as active runtime alternatives.

## Archived artifacts

### engines
- pac_engine_v1_0_core.py
- pac_engine_v1_0_core_pre_hardening.py
- pac_engine_v1_1_core.py
- pac_engine_v1_1_core_frozen.py

### interfaces
- pac_engine_v1_interface.py

### harnesses
- pac_engine_v1_attack_harness.py
- pac_engine_v1_attack_harness_wave2.py
- pac_engine_v1_attack_harness_wave3.py
- pac_engine_v1_attack_harness_wave3_frozen.py
- pac_engine_v1_interface_attack_tests.py
- pac_engine_v1_interface_tests.py
- pac_engine_v1_test_harness.py
- test_no_double_dict.py

### failure-cases
- pac_failure_case_w3_024.md

### backups
The former `.pac_backups/` files are retained under `provenance/backups/`.

Git history remains authoritative for exact historical movement and prior paths.
