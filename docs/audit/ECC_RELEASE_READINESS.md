# ECC release readiness

**Decision date:** 2026-10-16 (Asia/Manila)
**Code baseline:** `main` at `7185e18df2ae3b8f100804b7c3618a3909a831b6`; local tested commit `7031cf0eca6a076d5ab80d650be0d0e05874598d` is published in draft [PR #61](https://github.com/jasongil003/Concierge.Ai/pull/61) at remote head `03f07aa9cfbe2029943cdec013524a3e85b48889`. All local changes use isolated synthetic data; no live hotel installation is claimed.

## Four independent decisions

| Release stage | Decision | Why | Gate to advance |
|---|---|---|---|
| Internal developer testing | **GO** | Local backend, browser, authorization, and reporting tests can run against synthetic state. The test harness now blocks repository `.env` loading. Historical credential exposure remains an organizational incident, so developers must not use that credential. | Keep test data isolated; maintain the known secret-scan failure visible until resolved. |
| Internal synthetic hotel demo | **GO**, isolated only | Published synthetic property content, conversation cards, maps, requests, and admin functions passed local backend and final functional browser checks. A demo may illustrate the implemented product path without real guest/location data, live credentials, or external gateway claims. | Use the approved local demo fixture; clearly label simulated integrations and unverified “open now” state. |
| External hotel proof of concept | **NO-GO** | SEC-H01 credential invalidation/history status remains unresolved. The current branch adds active-stay retention, checkout cleanup, and linked-session consent fixes with local regression evidence, but property-approved location/notification policy and live ANTlabs/PMS/network/device acceptance are absent. Property content, maps, backup/key recovery, and deployment operations also need target-site validation. | Credential issuer confirms invalidation; repository owner coordinates authorized history remediation; privacy owner approves policy and the full data lifecycle passes staging tests; gateway/PMS/device and recovery acceptance passes. |
| Production deployment | **NO-GO** | External-pilot blockers remain, the 30,000 concurrent-guest target has no representative load/soak evidence, and `main` has no required CI status checks in the accessible ruleset. | Close pilot gates, complete representative PostgreSQL/Redis/TLS load and failure-recovery tests, configure and verify required CI checks, and obtain release-owner approval. |

## Verified working scope

- Backend tests and targeted security/RBAC suites pass locally; exact counts and skipped dependencies are in `ECC_TEST_RESULTS.md`.
- Structured property data, restaurant menus, map records, request confirmation/idempotency, and admin report data have tested synthetic paths. `ECC_FEATURE_MATRIX.md` and `ECC_GUEST_EXPERIENCE.md` distinguish backend from visual and live integration acceptance.
- Route-level admin policies and server-side property checks are in place. This is evidence for tested negative cases, not a blanket security certification.
- On the 2026-10-16 working branch, active guest stays no longer expire from a short check-in retention deadline; post-checkout retention starts at checkout. Local backend suite: 1,319 passed, 21 skipped, 2 warnings. See `ECC_CONTINUOUS_PROGRESS.md` for branch files and exact checks.

## Verified broken or incomplete scope

- SEC-H01 remains a reachable Git-history credential exposure. The credential value is excluded from these reports. No revocation, rotation, history rewrite, or remote repository change was performed.
- SEC-H02 property/privacy approval for location collection, retention, audiences, and full deletion remains absent. The 2026-10-16 branch implements/test-covers active-stay retention and checkout cleanup locally, but does not establish policy approval or live ingestion/admin/export acceptance. Do not collect real guest location data for a pilot until the full gate is closed.
- Property-local `today`/`yesterday` analytics are not guaranteed because `app/observability.py:28-43` uses the server clock rather than each property's timezone. “Open now” dining filtering similarly relies on configured status, not a timezone-aware schedule calculation (`app/main.py:7821-7886`).
- A dedicated QR/NFC provisioning and tested mobile captive-browser handoff is absent. Existing URL entry is insufficient proof of those platform flows.

## Unverified external and operational dependencies

Real AI provider accounts and privacy terms, ANTlabs SG5/PMS/WLAN feeds, physical iPhone Safari/Android Chrome/captive browsers, screen readers, target-host install/reboot, off-host encrypted backup and key recovery, and production-scale load were not verified here. CI run [#246](https://github.com/jasongil003/Concierge.Ai/actions/runs/38835174052) completed on PR #61: backend (1,321 passed, 19 skipped), browser (339 passed, 39 skipped), PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed; secret scan failed at its redacted current-worktree step, and its later forced-text history step did not run. The branch-protection API returned 403; the accessible ruleset only rejects deletion and non-fast-forward updates. The unresolved credential finding and current secret-scan failure remain release blockers.

## Decision ownership

An engineering test pass cannot waive the credential and privacy blockers. Credential invalidation belongs to the issuer owner; Git history cleanup and remote controls belong to the repository owner; location policy belongs to the property/privacy owner; external pilot and production release belong to the accountable release owner after the listed evidence is complete.
