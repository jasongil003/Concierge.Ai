# ECC security report

Date: 2026-10-14 (Asia/Manila)  
Audited HEAD: `82f9df2bafb4b3a632912762364fd6c7dff4a532`  
Scope: local source, reachable Git objects, configuration, and isolated tests. No live hotel system or external credential issuer was accessed.

## Release blockers

| ID | Severity | Evidence and exploitability | Required remediation |
|---|---|---|---|
| SEC-H01 | High; release blocker | Commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9` is reachable from the audited branch and `main`. Its `audit/evidence/security-2026-10-12/recovery-harness-before.txt` blob contains three references to `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` and no redaction marker. The current tracked file is a short placeholder, but that does not remove the historical blob. The prior sanitized investigation in `docs/audit/SECURITY_REMEDIATION.md` classifies the value as a genuine execution credential. Its current validity and privileges are unknown. Anyone able to read the affected history may have obtained it. No value was printed in this audit. | Credential issuer owner must establish whether the credential was invalidated and revoke/rotate if needed. Repository owner must authorize a coordinated history-cleanup plan covering all refs, forks, mirrors, caches, and collaborators, then verify the forced-text history scan. No history rewrite or remote action was performed. |
| SEC-H02 | High pilot privacy risk; release blocker for location-enabled hotel pilot | `app/main.py:5375-5396` records property-scoped AP/zone observations using a supplied device or MAC identifier without a consent or opt-out check. `app/location_analytics.py:17-66` stores observations, visits, transitions, interactions, and conversions; it has no subject deletion, export, or retention cleanup methods. Stay checkout at `app/main.py:5361-5371` clears stay memory and applies personalization policy but does not clear location rows. This permits retained location history after checkout. | Property/privacy owner must approve consent, opt-out, retention, checkout, export, and deletion rules. Implement and test the approved lifecycle, including cross-property negative cases, before collecting real guest location data. |

## Controls verified locally

| Area | Evidence | Result and limit |
|---|---|---|
| Admin authentication | `app/admin_auth.py:230-257`, `app/admin_auth.py:469-527`; `app/main.py:1903-1926` | Scrypt password hashes, account/IP lockout, database-backed sessions, HttpOnly and SameSite Strict cookie. Production/staging configuration requires a secure cookie and non-default bootstrap secret (`app/config.py:257-354`). Focused tests passed. |
| Route authorization | `app/rbac.py:18-100`, `app/admin_route_policies.json`; `app/main.py:397-447` | All 188 admin method/path policies are explicit: 181 permission-gated, four authentication-only, three public auth endpoints. Middleware rejects unregistered routes, checks permission and property, and requires CSRF for mutations. |
| Object scope | `app/admin_auth.py:653-787`, `app/main.py:802-891`; tests listed below | Role delegation is capped by actor permissions; property, department, and assigned restaurant negative tests passed. This test coverage does not prove every object-level path is sound. |
| Management network | `app/main.py:3665-3695`, `app/config.py:329-340` | Admin/metrics routes are subject to a management CIDR gate; production/staging require configured restricted CIDRs. |
| AI tool boundary | `app/admin_copilot.py:22-42`, `app/main.py:3227-3276`, `app/observability.py:357` | Planner names are filtered to server-registered, permission-allowed tools; registry checks again during execution. The configuration assistant uses a separate confirmation route. Prompt/output filtering is defense in depth, not an authorization boundary. |
| Input and output safety | `app/guardrails.py:460-505`, `app/main.py:349-366`, `app/main.py:3700-3789`, focused tests | Sanitization, security headers, guest origin checks, outbound HTTP/upload/SQL regression suites passed. A source and test review cannot establish safety against every prompt injection or browser payload. |
| Secret handling | `.gitignore:1`, `.github/workflows/ci.yml:85-110` | `.env` is ignored and untracked. CI has pinned redacted Gitleaks scans of current tree and `--all --text` reachable history. The known historical finding is intentionally unsuppressed. Local Gitleaks executable was unavailable, so no fresh Gitleaks result is claimed. |

## Scanner and regression evidence

- `.venv/bin/python -m pytest -q tests/test_admin_auth.py tests/test_high_rbac_boundaries.py tests/test_department_rbac_scope.py tests/test_rbac_policy_inventory.py tests/test_security_remediation.py tests/test_supply_chain_controls.py`: **472 passed**.
- `.venv/bin/python -m pytest -q tests/test_guest_credential_migration_sqlite.py tests/test_legacy_dashboard_security.py tests/test_floor_map_upload_security.py tests/test_outbound_http.py tests/test_sql_injection_regression.py tests/test_guardrails.py tests/test_network_access.py tests/test_restaurant_workflows.py`: **166 passed**.
- `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium -f json`: **0 findings**.
- `npm audit --offline --audit-level=high --json`: **0 vulnerabilities reported** by the offline cache. This is weaker than a fresh online advisory check.
- `.venv/bin/pip-audit -r requirements-dev.txt --timeout 5`: **incomplete**. Its isolated environment failed while upgrading pip before producing an audit report; no Python dependency conclusion is claimed.
- Gitleaks binary was unavailable locally. A value-free `git show` blob check independently confirmed the known historical artifact is reachable; the prior CI Gitleaks result is documented in `docs/audit/SECURITY_REMEDIATION.md`.

No local code change was made to the two blockers: credential revocation/history cleanup require the respective owners, and location lifecycle behavior requires approved privacy policy before implementation. No secrets, production data, or remote settings were changed.
