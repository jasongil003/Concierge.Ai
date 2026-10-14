# Release blockers

**Starting HEAD:** `e4bbd7493fe9d90a513d8224749b54c9e25ddc90`
**Implementation and tested commit:** `a30f95eb8db2ff05151c3473e453f9f38d0dec2d`
**Earlier audit code baseline:** `d5d006e89c38c0d901256d545679fee753175ef8`
**Date:** 2026-10-14 (Asia/Manila)
**Recommendation:** local synthetic demo only. Do not approve a hotel pilot or production rollout on this evidence.

| Priority | Blocker | Required acceptance to close |
|---|---|---|
| P0 / security | A prior security review identified a genuine execution-environment credential in reachable Git history (`audit/MASTER_SECURITY_REMEDIATION_REVIEW_2026-10-13.md`, SEC-01). The value and path contents are not repeated here. Issuer, audience and current validity are unknown from the sanitized evidence. | The issuing owner invalidates/replaces it; a repository owner completes history cleanup across relevant refs/forks/caches; an exhaustive history scan passes. This audit did not rotate credentials or rewrite history. |
| P1 / privacy | Guest location/AP association lifecycle lacks an approved property-scoped consent, retention, checkout, deletion, and opt-out policy. Prior release review names this as the highest-priority pilot blocker. | Approve policy and notification audiences first; implement/enforce it across ingestion, storage, admin views, exports, and expiry/deletion; add retention, opt-out, reconnection, and cross-property regression evidence. |
| P1 / integration | No target ANTlabs SG5, PMS, WLAN, RADIUS/ACS, or physical captive-network environment was available. Adapter tests and browser handoff are not live authentication evidence. | Run `audit/ANTLABS_ACCEPTANCE.md` on an authorized staging network with disposable guests; validate redirect, methods, property binding, Internet admission, logout, expiry, roaming, and recovery with the hotel's network/PMS owner. |
| P1 / content accuracy | No approved hotel's published inventory, menus, prices, hours, policies, facility locations, map geometry, room data, or licensed photos were supplied. Synthetic fixtures cannot establish guest truth. | Import and publish owner-approved data per property; verify guest answers, availability, image rights, and floor/route geometry with the property owner. |
| P1 / AI | No live provider credentials, authorization policy, model/provider quality test, rate-limit exercise, or measured recovery was available. OAuth access through consumer subscriptions is not supported by evidence. | Approve data-sharing policy per provider; configure API credentials through the supported secret path; test provider-specific retrieval, streaming, timeout, cost, rate limit, fallback, and failure without leaking private guest data. |
| P1 / request operations | Local proposal replay and concurrent idempotency are now verified (`tests/test_guest_personal_home.py`, `tests/test_service_catalog.py`); real staff fulfillment/delivery and SLAs remain unverified. | Validate staff queue permissions, delivery, acknowledgement, status transitions and property-approved SLA on an operational staging workflow. |
| P1 / capacity | No production-like measurements for the requested 100 through 30,000 concurrent-user steps. | Run isolated progressive load and soak tests; record throughput, p50/p95/p99 latency, errors, CPU, memory, database/Redis load, provider quotas, and recovery at each step. Do not infer 30,000-user support from unit tests. |
| P1 / recovery | No fresh native target-host install/upgrade/rollback/reboot or encrypted off-host backup/key recovery was performed. Prior isolated container receipts do not establish appliance reboot or off-host recovery. | Complete the clean-host Ubuntu and Apple Silicon acceptance runbooks, failure/reboot drills, and encrypted off-host restore/key recovery with synthetic data. |
| P2 / governance | The previous read-only review reported GitHub `main` without required CI status checks (2026-10-13). This audit could not refresh GitHub metadata. | Repository administrator rechecks branch rules and requires the intended CI, secret-scan, and security gates before changes reach `main`. |

## Current remote and evidence boundary

The cached local refs point to the code baseline, but `git ls-remote origin refs/heads/main` failed because `github.com` could not be resolved. No current remote branch protection or hosted CI status is claimed. No gateway, customer data, production database, deployment configuration, or external provider was changed.
