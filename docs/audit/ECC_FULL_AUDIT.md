# Concierge.Ai ECC full audit

**Review date:** 2026-10-14 (Asia/Manila)  
**Baseline:** `82f9df2bafb4b3a632912762364fd6c7dff4a532`, branch `codex/guest-concierge-premium-2026-10-13`  
**Latest comparison:** `0c40582..82f9df2` (three audit-document changes). `origin/main` resolved to the same commit when the local review began. The working tree was clean at baseline. This review makes local, uncommitted changes only.

## Method and evidence boundary

This is an engineering audit of the checkout, reachable local history, isolated tests, and local browser behavior. Earlier reports in `docs/audit/` and `docs/audits/` were read as leads; their claims were not promoted to current acceptance without fresh code or runtime evidence. No production hotel data, live PMS/ANTlabs gateway, live AI credentials, or production deployment was used. The full backend suite used isolated databases; the persistent `state/concierge.db` safety check reported unchanged. Current GitHub CI was inspected as source, while remote status is distinguished in the test report.

Repository discovery covered `app/` (FastAPI, stores, guest/admin UI), `migrations/`, `tests/`, `deploy/`, `scripts/`, `loadtest/`, `.github/workflows/`, dependency manifests, README, architecture/product plans, and previous ECC material. There are 233 FastAPI route declarations in `app/main.py`; route existence alone is not feature acceptance. The current UI is a Python-served static application, with a separate feature-flagged guest UI in `app/guest_v2/`. There is no independent frontend compilation pipeline in `package.json`; its scripts run Playwright.

Available locally: Python 3.11.16 in `.venv`, Node 26.7.0, npm/Playwright, Bandit, Docker Compose configuration parser, `shellcheck`, and macOS `plutil`. A Docker daemon, PostgreSQL/Redis services, `systemd-analyze`, local Gitleaks executable, GitHub CLI, and a usable local pip-audit advisory run were unavailable. The repository URL was opened read-only for current CI status but GitHub content could not be fetched in this environment; no current remote pass is claimed. The latest commit and parent were reviewed with `git show HEAD` and `git diff HEAD^ HEAD`, and reachable history was examined without printing secret values.

The branch has 245 reachable commits. This audit inspected the latest commit and parent, historical security provenance, prior audit documents, and current implementation; it did not manually review every historical patch line by line. A complete clean-history verdict requires an authorized scanner that can process forced-text diffs across all refs, plus owner resolution of SEC-H01.

## Architecture and dependency map

| Component and responsibility | Upstream input | Downstream dependency / consumer | Principal failure mode | Relevant tests |
|---|---|---|---|---|
| `app/main.py`: HTTP routing, guest/admin orchestration | Browser, reverse proxy, API clients | Stores, AI adapters, static UI | Wrong tenant/session/role or response contract | `tests/test_intelligent_ui.py`, `tests/test_operational_admin.py`, `tests/e2e/` |
| `app/static/`, `app/guest_v2/`: guest and admin presentation | Guest/admin APIs and published design | Guest/staff browsers | Chat overlap, stale content, inaccessible controls | `tests/e2e/guest*.spec.js`, `admin.spec.js`, `visual.spec.js` |
| `app/admin_auth.py`, `app/rbac.py`, `app/network_access.py`: identity, route policy, network boundary | Admin credentials/cookies and client network | All administrative handlers | Privilege escalation or management access from guest network | `tests/test_admin_auth.py`, `test_high_rbac_boundaries.py`, `test_network_access.py` |
| `app/session_store.py`, `app/guest_identity.py`, `app/antlabs.py`: guest identity and network handoff | Guest cookies, synthetic gateway/PMS assertions | Chat, service requests, personalization | Expired/revoked session accepted or misbound stay | `tests/test_guest_credential_migration_sqlite.py`, `test_antlabs_adapter.py`, guest E2E |
| `app/properties.py`, `app/database.py`, `app/schema_bootstrap.py`, `migrations/`: tenancy and persistence | Admin configuration, startup state | All property-scoped stores | Legacy schema incompatibility, tenant leakage, failed upgrade | `tests/test_properties.py`, `test_schema_compatibility.py`, PostgreSQL tests |
| `app/hospitality.py`, `app/zones.py`, `app/knowledge_management.py`: published content, dining, maps, requests | Admin-edited structured records and approved documents | Guest retrieval and cards | Stale/unpublished content, false directions/prices | `tests/test_restaurant_workflows.py`, `test_knowledge_management.py`, map upload tests |
| `app/guest_grounding.py`, `app/intelligent_ui.py`, `app/ai.py`, `app/ai_providers.py`: intent, grounding, UI schema, provider calls | Property data, guest message, provider configuration | Guest answer/SSE stream | Hallucinated claim, provider failure, unsafe tool execution | `tests/test_guest_grounding.py`, `test_ai_providers.py`, `test_intelligent_ui.py` |
| `app/operations.py`, `app/guest_actions.py`: request lifecycle and controlled actions | Confirmed guest/admin operations | Staff queue, guest status | Duplicate or falsely confirmed request | `tests/test_service_catalog.py`, `test_guest_personal_home.py` |
| `app/observability.py`, `app/reporting.py`, `app/location_analytics.py`: telemetry and exports | Session, AI, request and location records | Admin dashboard, XLSX/PDF | Misleading empty-state metric, privacy leakage, wrong time window | `tests/test_observability_reporting.py`, `test_operational_admin.py` |
| `app/backup.py`, `deploy/`, `scripts/`, `.github/workflows/`: install and recovery | Environment, database, host services | Running application and CI | Unsafe migration, lost key/data, unverifiable release gate | `tests/test_backup_restore.py`, `test_source_install.py`, `test_deployment_hardening.py` |

## Independently checked product areas

- **Guest conversation and action:** property-scoped structured answers, streaming, restaurant/menu cards, map content, and explicit service-request confirmation have backend and browser test surfaces. The guest report records the exact prompt/visual acceptance and the limits of emulated browsers. Live hotel content and live provider behavior remain unverified.
- **Admin and editor:** `app/main.py:4880-4943` saves draft design, publishes, discards, and restores a version to draft, with revision-conflict responses. Browser tests in `tests/e2e/admin.spec.js` cover design publication and guest output. This is local synthetic acceptance, not every editor control or physical device.
- **Admin navigation and control inventory:** the functional Playwright run visited 42 admin destinations and 5 guest views, counting 2,125 visible control instances. The inventory reported zero enabled non-focusable controls and zero controls missing an accessible name. It explicitly checked entry/focus/name behavior rather than clicking every control; named workflow tests provide the separate interaction evidence.
- **Analytics and exports:** `app/observability.py:221-280` derives request/AI/session measures from stored records; `app/main.py:4022-4040` scopes export construction through an admin principal. Empty periods use `None` for unsupported rates. A verified low-severity PDF wording defect was corrected; see the remediation log.
- **AI adapters:** `app/ai_providers.py:739-1055` implements OpenAI-compatible, Gemini, Claude, and local adapters and deliberately marks Copilot unavailable. OAuth token consumption is present for Gemini, but an end-to-end OAuth consent/token flow is not implemented. Local endpoint selection is allowlisted in `app/ai_providers.py:27-62`. Live provider quality, rate/price, and privacy acceptance are unverified.
- **Access and scale:** the route-policy inventory and network guard are explicit. `playwright.config.js` defines Desktop Chrome and Pixel 7 projects; it does not define WebKit/iPhone Safari. The 30,000 concurrent-guest target is unverified; local samples cannot establish it.

## Findings and disposition

| ID | Severity | Evidence | Disposition |
|---|---|---|---|
| SEC-H01 | High, production blocker | Reachable history includes a previously documented credential-bearing evidence blob at commit `0b0ff26a`; three detections were confirmed in earlier GitHub CI and local history inspection without exposing the value. | Credential owner must confirm invalidation/rotation; authorized repository owner must plan full-ref history cleanup. No rewrite or rotation in this review. |
| SEC-H02 | High, external-pilot blocker | Location observation write and location tables lack a complete consent, opt-out, export, retention, and deletion lifecycle; see `app/main.py:5375-5396` and `app/location_analytics.py`. | Privacy/product owner must approve policy, then implement and test lifecycle and checkout cleanup. |
| INT-H01 | High acceptance gap | Live ANTlabs/PMS/WLAN contracts and physical captive browsers were unavailable. | Validate on an authorized staging hotel network with approved synthetic stay data. |
| OPS-H01 | High acceptance gap | No representative 30,000-session capacity or soak evidence. | Provision isolated representative PostgreSQL/Redis/provider setup and run staged load tests. |
| DATA-P1 | High, fixed locally | `app/backup.py:437-439` removed the existing SQLite DB before a staged replacement was known to succeed. Failure injection reproduced the data-loss risk. | Removed the pre-unlink and added a regression that preserves the existing DB and uploads when replacement fails. |
| TST-P1 | Medium, fixed locally | The test harness allowed repository `.env` values to enter isolated app imports. | Disabled dotenv loading in pytest and Playwright test server; added boundary assertions. |
| ANA-M01 | Medium, source-confirmed | `app/observability.py:28-43` calculates `today` and `yesterday` from the server's local clock, while properties store their own timezone (`app/properties.py:371`). A multi-property report can therefore use the wrong calendar day. | Pass the validated property timezone through report, dashboard history, and restaurant diagnostics; test two zones and a daylight-saving transition. |
| PROD-M01 | Medium missing feature | No dedicated QR/NFC guest product flow was identified in `app/` routes or UI assets. | Define and implement entry/auth handoff with platform testing if required for pilot. |
| GUEST-P2 | Medium, fixed locally | Legacy chat scrolled a non-scrolling element and checked the near-bottom state after re-render; a 390×700 before screenshot showed a cut-off long reply. | Corrected scroll target and anchoring; focused Chromium and Pixel 7 tests passed with an after screenshot. |
| REP-L01 | Low, fixed locally | Empty management PDF rendered `Not enough prior data%.` in `app/reporting.py`. | Conditional value formatting and regression coverage added. |

For detailed classifications, role outcomes, guest evidence, security findings, performance data, and command results, see the other `ECC_*.md` reports in this directory. A feature is marked **implemented and verified** only for the tested behavior, with synthetic data and environment stated.

## Outcome by required category

- **Verified working features:** locally tested admin authentication and RBAC boundaries, property-scoped guest knowledge, published dining/menu retrieval, request proposal/confirmation and duplicate protection, map fallback, report generation, SQLite backup/restore, and selected browser flows. Their exact evidence and narrower acceptance scope are in `ECC_FEATURE_MATRIX.md`.
- **Verified broken or incomplete features:** the long-reply scroll defect and SQLite restore pre-unlink were reproduced and fixed; property-local calendar-day analytics and truthful calculated restaurant “open now” remain incomplete. The external location-data lifecycle is incomplete.
- **Missing features:** dedicated QR/NFC guest entry and a production Copilot adapter; optional OAuth and semantic retrieval are only partial or absent as classified in the feature matrix.
- **Improvements implemented:** chat scroll anchoring, dotenv test isolation, failure-safe SQLite replacement, and PDF empty-period wording, each with a regression check.
- **Outstanding security findings:** SEC-H01 historical credential and SEC-H02 guest location-data privacy lifecycle. Neither is waived by passing tests.
- **Deferred architectural changes:** timezone-aware operational periods, authoritative restaurant opening state, full notification delivery, and representative multi-node capacity are proposals rather than silent behavior changes.
- **Unverified external dependencies:** live AI accounts, ANTlabs/PMS/WLAN, physical devices and screen readers, PostgreSQL/Redis on this host, target-host installer/reboot, off-host key recovery, and required remote CI for the uncommitted changes.
- **Remaining release blockers:** SEC-H01 and SEC-H02 for an external hotel pilot; external integration, recovery and scale gates also prevent production release.

## Re-audit boundary

Local changes are reviewed with focused tests and the final verification ledger. The high-risk external conditions remain open. No server, hotel dataset, Git history, credential, remote branch, or deployment was changed by this audit.
