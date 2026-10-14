# ECC release readiness

**Decision date:** 2026-10-14 (Asia/Manila)  
**Code baseline:** `82f9df2bafb4b3a632912762364fd6c7dff4a532`; this audit's changes remain local and uncommitted. The decisions below are based on isolated synthetic evidence, not a live hotel installation.

## Four independent decisions

| Release stage | Decision | Why | Gate to advance |
|---|---|---|---|
| Internal developer testing | **GO** | Local backend, browser, authorization, and reporting tests can run against synthetic state. The test harness now blocks repository `.env` loading. Historical credential exposure remains an organizational incident, so developers must not use that credential. | Keep test data isolated; maintain the known secret-scan failure visible until resolved. |
| Internal synthetic hotel demo | **GO**, isolated only | Published synthetic property content, conversation cards, maps, requests, and admin functions passed local backend and final functional browser checks. A demo may illustrate the implemented product path without real guest/location data, live credentials, or external gateway claims. | Use the approved local demo fixture; clearly label simulated integrations and unverified “open now” state. |
| External hotel proof of concept | **NO-GO** | SEC-H01 historical credential status is unresolved, SEC-H02 location-data consent/retention/deletion is incomplete, and live ANTlabs/PMS/network/device acceptance is absent. Property opening status, approved content, backup/key recovery, and deployment operations also need target-site validation. | Credential issuer confirms invalidation/rotation; repository owner authorizes history remediation; approved privacy lifecycle passes tests; staging gateway/PMS/device and recovery acceptance passes. |
| Production deployment | **NO-GO** | External-pilot blockers remain, and the 30,000 concurrent-guest target has no representative load/soak evidence. Current local smoke results do not validate production topology, provider capacity, failover, or operational SLO. | Close every pilot gate, complete representative PostgreSQL/Redis/TLS load and failure-recovery tests, verify CI required checks and rollback/restore, and obtain release-owner approval. |

## Verified working scope

- Backend tests and targeted security/RBAC suites pass locally; exact counts and skipped dependencies are in `ECC_TEST_RESULTS.md`.
- Structured property data, restaurant menus, map records, request confirmation/idempotency, and admin report data have tested synthetic paths. `ECC_FEATURE_MATRIX.md` and `ECC_GUEST_EXPERIENCE.md` distinguish backend from visual and live integration acceptance.
- Route-level admin policies and server-side property checks are in place. This is evidence for tested negative cases, not a blanket security certification.

## Verified broken or incomplete scope

- SEC-H01 remains a reachable Git-history credential exposure. The credential value is excluded from these reports. No revocation, rotation, history rewrite, or remote repository change was performed.
- SEC-H02 location observations lack an approved full privacy lifecycle; do not collect real guest location data for a pilot until this is closed.
- Property-local `today`/`yesterday` analytics are not guaranteed because `app/observability.py:28-43` uses the server clock rather than each property's timezone. “Open now” dining filtering similarly relies on configured status, not a timezone-aware schedule calculation (`app/main.py:7821-7886`).
- A dedicated QR/NFC provisioning and tested mobile captive-browser handoff is absent. Existing URL entry is insufficient proof of those platform flows.

## Unverified external and operational dependencies

Real AI provider accounts and privacy terms, ANTlabs SG5/PMS/WLAN feeds, physical iPhone Safari/Android Chrome/captive browsers, screen readers, target-host install/reboot, PostgreSQL/Redis acceptance on this host, off-host encrypted backup and key recovery, and production-scale load were not verified here. CI configuration was reviewed locally; no new remote CI success for these uncommitted changes is claimed. The prior forced-text secret-scan run intentionally failed on the historical credential, as recorded in `docs/audit/SECURITY_REMEDIATION.md`.

## Decision ownership

An engineering test pass cannot waive the credential and privacy blockers. Credential invalidation belongs to the issuer owner; Git history cleanup and remote controls belong to the repository owner; location policy belongs to the property/privacy owner; external pilot and production release belong to the accountable release owner after the listed evidence is complete.
