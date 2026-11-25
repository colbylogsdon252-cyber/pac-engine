# PAC release completion scope

Owner authorization: primary objective only. Stop for owner check-in after verified completion.

## 1. Integration identity and credential hardening
Authenticated enrollment; subscriber-specific signing credentials; rotation and revocation; optional initialization. Preserve existing proof and execution authority. Verify that hardened delivery cannot fall back to shared credentials, that cross-tenant enrollment is denied, and that revocation prevents new dispatch authorization. Already transmitted requests cannot be recalled. Document trust boundaries and test negative cases. Require full regression evidence before merge and verify canonical main.

## 2. Operational verification — held
Exercise canonical event creation, attribution, export, signed delivery, retries, process crashes, receiver replay protection and subscriber revocation in a realistic deployment. Requires owner check-in after objective 1.

## 3. Release acceptance — held
Security, persistence, operational and external-provider acceptance; immutable evidence; explicit production-release authorization.

No production release authorized. Existing release checklist remains controlling. Independent event insertion is not proof of authoritative transition provenance.
