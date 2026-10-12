# Concierge.AI ECC Audit — Functional and Architecture Findings

## Scope and result

The current working tree was exercised with the backend suite and the non-visual Playwright scenarios. Existing application changes were present before the audit; they were preserved. Local functional evidence supports the current tested flows but does not certify external providers, production infrastructure, or unrun database/cache combinations.

### Confirmed defects

No new Critical, High, or Medium application-logic defect was reproduced in the local checks. The guest expiry issue is tracked separately as `ECC-SES-001`, now `FIXED-VERIFIED`.

### Follow-up items

#### `OPS-021` — Breakfast answer behavior needs a direct acceptance assertion

- **Severity/status:** Low functional coverage gap; **FIXED-UNVERIFIED**.
- **Historical context:** Existing audit files conflict: `audit/18_FINDINGS_REGISTER.md` records a generic dining answer, while `audit/23_REMEDIATION_PASS.md` says the issue was fixed. Historical mobile Chromium evidence also reported a breakfast/dining mismatch.
- **Current evidence:** `app/main.py:6408-6490` contains deterministic property-based breakfast handling, filters guest-visible restaurants by meal period and hours, and can tell a guest to confirm with the desk when hours are not known. The source path appears corrected. The current E2E suite does not contain a direct assertion that the exact question “What time is breakfast?” returns the expected property-specific answer on both desktop and mobile. The evaluation JSON is not a substitute for an executed acceptance test.
- **Recommendation:** Add a deterministic test fixture and assert the exact user-visible answer, restaurant eligibility, and unknown-hours fallback for both browser projects. Do not infer real-world answer correctness from a successful API status.

#### `ECC-OPS-001` — Target runtime and lifecycle acceptance outstanding

- **Severity/status:** Medium operational blocker; **BLOCKED** pending target infrastructure.
- **Evidence:** `docs/PRODUCTION_ACCEPTANCE.md` and `docs/CONTROLLED_POC_ACCEPTANCE.md` require clean installation, TLS/reverse-proxy validation, gateway/network checks, reboot, update failure rollback, backup and off-host restore, and PDF worker resource acceptance. These were not run as part of the local test suite.
- **Recommendation:** Execute those checklists on a disposable appliance with synthetic data before an external pilot.

## Functional areas reviewed

- **Guest portal and session lifecycle:** start/resume, auth, expiry, revoked credentials, property binding, personalization, logout/cookie behavior, and activity renewal passed applicable tests.
- **Admin and property workflows:** RBAC, tenant selection, admin workflows, catalog and restaurant management, and existing NULL `hotel_name`/missing `brand_assets` repair coverage passed in the local backend/browser suites.
- **Service requests:** existing authenticated proposal/confirm workflow is retained by Intelligent UI; the UI does not submit model-selected actions. Existing service workflow browser and backend coverage passed.
- **Migrations:** SQLite compatibility/migration checks ran locally. PostgreSQL Alembic/migration integration was skipped because its service was unavailable.
- **AI/provider behavior:** adapter delegates to established chat policy, retrieval, provider selection, and rate limiting. Live provider availability, real credential secrecy in a production deployment, provider outage recovery, and factual guest answer quality were not tested.
- **Reports, analytics, visual editor, and deployment lifecycle:** local UI/backend coverage exercised relevant existing functionality. This audit did not perform production deployment, destructive updates, or restore on an external host.
- **Background/resource control:** worker code has explicit time and resource bounds; high-expansion PDF acceptance remains unverified (`FILE-DOS-01`).

## Architecture notes

The Intelligent UI runs alongside the legacy portal. Its frontend assets are allowlisted and served only when both flags permit the feature. The chat adapter uses the existing chat handler and shapes its answer into a versioned Pydantic schema. Card data comes from the authenticated session property. The browser uses an allowlisted component renderer and text content rather than HTML parsing. See [UI readiness](ECC_INTELLIGENT_UI_READINESS.md).

The significant architecture gaps are non-streaming responses (`ECC-UI-001`) and a process-restart global rollback (`ECC-UI-002`). These limit rollout readiness but were not found to be current access-control bypasses.
