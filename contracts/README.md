# PAC Contracts

This directory contains portable PAC contract artifacts.

## Frozen Contract

`pac_frozen_contract_v1.json` defines the executable-signal input contract frozen at:

`PAC-V1-FROZEN`

## Purpose

The contract externalizes the required PAC payload structure without changing engine logic.

## Rule

No action is executed unless proof is complete.

## Decision / Exit Code Contract

- `APPROVE` -> exit code `0`
- `HALT` -> exit code `1`
- `REJECT` -> exit code `2`

## Boundary

This contract is a portable schema/reference artifact. It does not replace, override, or mutate the PAC engine.
