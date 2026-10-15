# Feature achievement matrix — 2026-10-15

Baseline: fetched `origin/main` `8ee80d2d688584795b6140582d609f81479b2137`, plus the guest scroll and offline mirror preparation changes on `codex/ecc-ci-guest-audit-20261015`. This is the current category-level assessment; the existing [384-row acceptance inventory](../../audit/MASTER_FEATURE_ACCEPTANCE_MATRIX.md) and [granular ECC matrix](ECC_FEATURE_MATRIX.md) retain the individual requirements. `Working` means demonstrated with synthetic/local data where stated. `Production verified` requires evidence from an actual authorized hotel environment. Status values are **YES**, **PARTIAL**, **NO**, or **UNVERIFIED**.

Continuation: fetched merged `origin/main` `d4649ff138c8ee9b6b8a681aae2132874894a7a2` on 2026-10-15 and reviewed the existing uncommitted `codex/priority-features-20261015` checkout. Rows that name the uncommitted priority branch are local acceptance only and do not change the production-verification column.

Release-hardening continuation (2026-10-15): fetched `origin/main` at `7185e18df2ae3b8f100804b7c3618a3909a831b6`. Redundant draft PR #58 was closed because its tree exactly matched `main`. Facility closure/reopen notifications are in draft [PR #59](https://github.com/jasongil003/Concierge.Ai/pull/59); run #240's targeted browser retry passed 339 tests (39 skipped), but `secret-scan` failed. Nearby intent/category permission fixes are in draft [PR #60](https://github.com/jasongil003/Concierge.Ai/pull/60); run #242 passed browser, backend, PostgreSQL/Redis, Docker, dependency, static-security, and deployment jobs, with `secret-scan` failing. Follow-up run #243 was in progress at the last check.

| Feature | Implemented | Working | Tested | Production verified | Evidence / limit |
| --- | --- | --- | --- | --- | --- |
| Property branding and guest welcome | YES | YES | YES | UNVERIFIED | `app/guest_v2/app.js`, `tests/e2e/guest.spec.js`; local synthetic property. |
| Personalized welcome from authorized guest context | PARTIAL | PARTIAL | YES | UNVERIFIED | `app/guest_memory.py`, guest tests; live PMS context absent. |
| Responsive conversation and fixed composer | YES | YES | YES | UNVERIFIED | 390/768/1440 browser screenshots and composer geometry regression. Physical keyboard untested. |
| Long-chat reading anchor and follow latest | YES | YES | YES | UNVERIFIED | `app/guest_v2/app.js:1648-1661`, `tests/e2e/guest.spec.js:2521`; before-fix 2/24 failures, after-fix 24/24 repeat pass. |
| Rich restaurant cards, menu, image, prices | YES | PARTIAL | YES | UNVERIFIED | Browser menu/card test and `tests/test_intelligent_ui.py`; real published hotel data and image rights not verified. |
| Published hotel facts and facilities | YES | PARTIAL | YES | UNVERIFIED | `app/knowledge_management.py`, `app/main.py`, grounded response tests; actual property content unverified. |
| Indoor map assets and floor switching | YES | PARTIAL | YES | UNVERIFIED | `app/guest_v2/app.js`, `tests/test_intelligent_ui.py`; local configured maps only. |
| Map revision draft, publication, and rollback | YES | YES | YES | UNVERIFIED | Uncommitted priority branch; `tests/test_map_revisions.py` and admin browser workflow use synthetic property maps. Real geometry approval remains outstanding. |
| Accessible indoor route graph | YES | PARTIAL | YES | UNVERIFIED | `app/zones.py`, `tests/test_intelligent_ui.py`; real building graph and physical routes unverified. |
| Graceful no-map fallback | YES | YES | YES | UNVERIFIED | `tests/test_intelligent_ui.py`; local synthetic absence. |
| Guest service proposal and confirmation | YES | YES | YES | UNVERIFIED | `tests/test_service_catalog.py` direct API and `tests/test_intelligent_ui.py`; actual department receipt unverified. |
| Request idempotency, assignment, status | YES | PARTIAL | YES | UNVERIFIED | `tests/test_service_catalog.py`, staff/browser tests; live notification and staff operations unverified. |
| Nearby external places | PARTIAL | PARTIAL | YES | UNVERIFIED | `app/places.py`, `tests/test_places.py`, and `tests/test_guest_privacy_consent.py`; complete-word intent matching and independent restaurant/attraction permission checks pass locally. External provider, freshness, approved privacy policy, and live consent behavior remain unverified. |
| Guest external-processing and location consent controls | PARTIAL | PARTIAL | YES | UNVERIFIED | Uncommitted priority branch; `tests/test_guest_privacy_consent.py` covers local consent, denial, withdrawal, checkout, and retention. Approved property policy and live collection are absent. |
| Guest notification inbox and dispatch | PARTIAL | PARTIAL | YES | UNVERIFIED | `tests/test_notification_delivery.py` and guest browser flow use synthetic events. Facility closure/reopen notices are proposed in [PR #59](https://github.com/jasongil003/Concierge.Ai/pull/59). Actual guest delivery and staff operations are unverified. |
| Tonight recommendations in property timezone | PARTIAL | UNVERIFIED | PARTIAL | UNVERIFIED | Schedule/content paths exist; local-time precedence and live event data not accepted. |
| Draft preservation, retry, session recovery | YES | YES | YES | UNVERIFIED | `tests/e2e/guest.spec.js` failed-send, duplicate, new-chat, history, expiry regressions. |
| Knowledge upload, review, publication | YES | YES | YES | UNVERIFIED | `app/knowledge_management.py`, backend and admin browser tests; real content governance unverified. |
| Source-grounded hotel claims | YES | PARTIAL | YES | UNVERIFIED | `app/guest_grounding.py`, `tests/test_intelligent_ui.py:661`; deterministic claim rejection, live AI outputs unverified. |
| AI provider fallback and encrypted credentials | YES | PARTIAL | YES | UNVERIFIED | `app/ai_providers.py`, `tests/test_ai_providers.py`; live provider failure and credential deployment unverified. |
| Safe streaming progress and interruption | YES | PARTIAL | YES | UNVERIFIED | Guarded SSE in `app/main.py`, browser pending-state test; live TTFT, memory, and concurrent generations unmeasured. |
| Admin authentication and role policies | YES | YES | YES | UNVERIFIED | `app/rbac.py`, `tests/test_high_rbac_boundaries.py`, direct API negative cases; production identity setup unverified. |
| Property, department, restaurant boundaries | YES | YES | YES | UNVERIFIED | `tests/test_department_rbac_scope.py`, `tests/test_service_catalog.py`; local synthetic tenants. |
| Admin content, settings, reports, exports | YES | PARTIAL | YES | UNVERIFIED | Admin browser/backend tests; property-timezone analytics defect remains in ECC backlog. |
| Restaurant and menu operations | YES | PARTIAL | YES | UNVERIFIED | Admin workflow tests; live schedules and status precedence unverified. |
| Health, diagnostics, and audit trail | YES | PARTIAL | YES | UNVERIFIED | `app/operations.py`, tests and CI; deployed alert delivery and observability unverified. |
| ANTlabs gateway simulator contract | YES | YES | YES | UNVERIFIED | `app/antlabs.py`, `tests/test_antlabs_adapter.py`; no physical SG5 or captive portal acceptance. |
| PMS authoritative stay synchronization | PARTIAL | UNVERIFIED | PARTIAL | UNVERIFIED | Adapter/boundary paths reviewed; no live PMS contract or data tested. |
| macOS and Ubuntu deployment configuration | YES | PARTIAL | YES | UNVERIFIED | CI run 38579415155 deployment jobs passed; actual target host install not observed. |
| Docker/PostgreSQL/Redis runtime | YES | PARTIAL | YES | UNVERIFIED | CI PostgreSQL/Redis job passed; local production Compose runtime not exercised here. |
| Backup, restore, encryption-key recovery | PARTIAL | PARTIAL | YES | UNVERIFIED | Local restore tests; off-host/key recovery and target host drill outstanding. |
| Current tracked secret hygiene | YES | YES | YES | UNVERIFIED | Gitleaks 8.24.3 tracked snapshot: 0 findings; ignored local `.env` is outside tracked snapshot. |
| Reachable-history secret hygiene | NO | NO | YES | NO | Forced-text Gitleaks: 3 known historical credential detections; CI `secret-scan` fails closed. |
| 30,000 connected guests / simultaneous AI capacity | NO | UNVERIFIED | NO | UNVERIFIED | Target only; representative connection and AI-generation loads are distinct and unmeasured. |
