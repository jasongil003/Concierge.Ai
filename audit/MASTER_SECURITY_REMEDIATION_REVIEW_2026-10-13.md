# Security remediation and release review

Date: **2026-10-13 (Asia/Manila)**
Repository: `jasongil003/Concierge.Ai`
Baseline branch/HEAD: `codex/master-product-audit-2026-10-12` / `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`
Remote: `origin/main` was fetched twice during this review and remained at the same SHA. The starting worktree was clean.
Remediation branch: `codex/security-remediation-2026-10-13`.

## Executive review

The failed `secret-scan` job is reproducible. It found the same genuine execution-environment credential three times in a retained recovery-harness transcript. The credential is removed from current repository content; the source harnesses now use explicit environment allowlists; audit outputs with synthetic credentials are redacted. A current-tree Gitleaks scan passes with zero findings. A scan of reachable Git history still finds the three copies in commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`.

The credential must be treated as potentially compromised. Its external validity and privilege scope are not ascertainable from this repository. No rotation or history rewrite was performed. The history issue keeps the remediation **draft-only** pending credential invalidation and an authorized cleanup plan. The Gitleaks CI action remains in place; the workflow adds a checksum-verified current-tree scan because the hosting provider's PR patch must not display the removed credential. GitHub repository metadata reports branch protection disabled and no required status checks on `main`, so GitHub does not currently enforce this workflow as a merge gate.

No new authentication, RBAC, property-isolation, guest-expiry, staff-conversation, or retention exploit was confirmed in this scoped code review. Earlier master-audit findings for legacy knowledge publication and dashboard data projection remain fixed and their regression suites pass. Local verification supports **internal synthetic demo only**. It does not establish readiness for a hotel pilot or production.

## Baseline and remote CI evidence

- Run `38326687782` is CI run 205 for push commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`.
- Job `115066879977` (`secret-scan`) failed. Gitleaks 8.24.3 reported three `generic-api-key` findings in `audit/evidence/security-2026-10-12/recovery-harness-before.txt` at lines 10, 17, and 24.
- The run's backend, browser, static security, dependency, PostgreSQL/Redis, Docker, and deployment-validation jobs succeeded. The secret-scan failure was the only failed job.
- The recorded Gitleaks command scans the first-parent commit diff. Running that scope against the failed commit with text diff forced reproduced the same three findings. The broader all-ref history scan also finds those same three.
- Repository branch settings report `main` protection disabled, with no required status checks configured. The `secret-scan` job is blocking when this workflow runs, but the repository does not enforce it before merges or direct updates.
- `.gitattributes` marks only this transcript as non-text for the hosting provider's patch view. This keeps the removed value out of the PR text. It also means the historical diff scanner alone cannot inspect that file in a checkout containing the new attribute. The workflow therefore retains the Gitleaks action and adds a Gitleaks `--no-git` scan of the complete current worktree. The current-tree scan sees the redacted transcript and every other current file; it reports zero findings. The history scan is run separately with `--text` to override presentation attributes.

## Recent commit and master-audit review

The complete diffs and changed-file sets were reviewed for the latest commits: `0b0ff26` (audit/evidence and roadmap), `ecfe3f4` (guest privacy wording, responsive layout, and browser test reliability), `c4bdec5` (container networking, PostgreSQL/Redis recovery and database isolation), `a52e5ea` (PDF pagination and PostgreSQL nullable binding), `132d858` (knowledge publication authorization), and `d2d09ba` (legacy dashboard scoping and quiet-hours behavior). The three Gitleaks findings originated in the newest audit/evidence commit; the prior code fixes remain supported by their regression tests.

Cross-checks included `MASTER_FEATURE_ACCEPTANCE_MATRIX.md`, `MASTER_RELEASE_READINESS.md`, `MASTER_SECURITY_REVIEW.md`, `MASTER_REMEDIATION_LOG.md`, `MASTER_TEST_RESULTS.md`, `MASTER_UI_UX_REVIEW.md`, `MASTER_PERFORMANCE_REVIEW.md`, `MASTER_PRODUCT_GAP_ANALYSIS.md`, and the associated acceptance JSON, browser receipts, and security evidence. Current rerun results are recorded below and do not upgrade unrelated matrix requirements without new mapped evidence.

## Confirmed findings

### SEC-01 — Execution-environment credential retained in audit evidence

- **Severity:** High exposure; actual capability and validity unknown.
- **Affected artifact:** `audit/evidence/security-2026-10-12/recovery-harness-before.txt`, lines 10, 17, and 24 in commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`. No credential value is reproduced in this report.
- **Reproduction:** Gitleaks 8.24.3 over the failed first-parent commit diff reports three identical-value `generic-api-key` findings. Full-history scan with text diff forced reports the same three.
- **Classification:** Genuine execution-environment secret, not a synthetic fixture or false positive. Investigation identified the environment variable name `BROWSER_USE_ACCESS_VERIFYING_IDENTITY`; the value also matched the process environment at investigation time. The issuing system's validity, audience, and permissions could not be determined locally.
- **Root cause:** `scripts/failure_recovery_smoke.py` copied the entire caller environment into the app and integration-test child processes. Captured diagnostic evidence then retained a host credential. `playwright.config.js` had a second `process.env` inheritance path.
- **Minimal fix:** Replace environment inheritance with explicit allowlists in both harnesses; add a sentinel regression that asserts sensitive host variable names are absent from child environments; redact the three committed copies. The browser server gets a separately constructed synthetic environment. A one-file diff-presentation rule prevents the hosting provider's PR view from exposing the deleted line, and the new CI current-tree Gitleaks scan keeps the current file covered.
- **Regression and verification:** `tests/test_failure_recovery_harness.py::test_recovery_children_do_not_receive_host_credentials`; `tests/e2e/server-environment.spec.js`; complete backend and browser suites; current-tree Gitleaks scan: **PASS, zero findings**. Forced full-history Gitleaks: **FAIL, three historical findings**, as expected until history is sanitized.
- **Rotation instructions:** The owner of the browser verification identity should revoke/invalidate the old identity in its issuing control plane, issue a replacement, update the appropriate secret store/runtime injection, and verify the replacement without logging it. After invalidation, coordinate a repository-wide history cleanup covering affected refs, tags, forks, caches, and collaborator clones. No rotation or history cleanup is claimed here.

### SEC-02 — Legacy knowledge API bypassed publication permission (master finding, fixed)

- **Severity:** High.
- **Affected area:** Legacy knowledge write route in `app/main.py` and `app/knowledge_management.py`.
- **Reproduction:** An editor with `knowledge.edit` but without `knowledge.publish` attempted to set `enabled=true`, or to overwrite an already published answer through the legacy endpoint. The prior implementation could cross the guest-publication boundary, including a stale-draft race.
- **Root cause:** The legacy mutation path did not enforce the separate publication capability atomically across the read/write boundary.
- **Minimal fix already on main:** Pass the principal's publication capability to the store and reject unauthorized enable/overwrite transitions at the store boundary; keep the publisher transition atomic.
- **Regression and verification:** `tests/test_legacy_knowledge_publication.py::test_legacy_draft_editing_and_publisher_transitions_preserve_approval_boundary` and `::test_concurrent_publication_prevents_stale_draft_editor_overwrite`; both pass in the full backend suite.

### SEC-03 — Legacy dashboard returned data outside the caller's permissions (master finding, fixed)

- **Severity:** Medium.
- **Affected area:** `GET /api/admin/properties/{property_id}/dashboard` in `app/main.py` (route at line 2074) and its role-aware projection.
- **Reproduction:** A department manager, content manager, or dashboard-only role requested the legacy dashboard and could previously receive guest activity, AI/provider configuration, or unrelated department/property metrics. Cross-property access was also part of the boundary check.
- **Root cause:** The legacy response projected broad dashboard data without consistently filtering every field by permission and department scope.
- **Minimal fix already on main:** Project fields according to the authenticated role's permissions and department scope; deny the other property.
- **Regression and verification:** `tests/test_legacy_dashboard_security.py::test_legacy_dashboard_does_not_disclose_protected_guest_or_configuration_data` and `::test_legacy_dashboard_retains_authorized_property_metrics`; the department analytics scope tests also pass.

### SEC-04 — GitHub does not enforce CI status checks on `main`

- **Severity:** Medium; an unverified or failing change can reach `main` without GitHub blocking it.
- **Affected configuration:** GitHub repository branch settings for `main` (outside the source tree).
- **Reproduction:** The repository API reports `protection.enabled=false`, `required_status_checks.enforcement_level="off"`, and empty required-check lists.
- **Root cause:** No branch protection rule or ruleset currently requires successful CI status checks.
- **Minimal safe fix:** Repository administrators should enable a `main` ruleset requiring the `secret-scan` job and the intended complete CI status set before merge, and disallow bypass except for an explicitly governed emergency path. No repository-setting write operation was available during this remediation; settings were not changed.
- **Regression and verification:** Read-only repository metadata confirms the current absence of enforcement. Configuration change and enforcement behavior remain **BLOCKED** pending an administrator with repository settings access; no CI result alone verifies a required-check policy.

### Additional evidence inventory

The committed audit-output review found 11 additional credential-shaped values, all synthetic test/development values: six in `audit/evidence/security-2026-10-12/compose-proxy-before.txt` and five in `audit/evidence/master-2026-10-12/container-postgres.log`. Those current files are redacted. No other genuine credential was identified in the committed audit outputs reviewed. The static performance harness's fixed synthetic bootstrap/encryption values were replaced with per-run random values. The empty optional `GOOGLE_PLACES_API_KEY` example and a synthetic AI-provider fixture caused two current-tree Gitleaks false positives; the example is now documented as an optional private setting and the fixture is assembled at runtime. No broad rule or path exclusion was added.

## Additional security and architecture review

- Authentication, role permissions, property binding, guest session expiry/refresh/revocation, staff assignment, and transcript access were reviewed against `tests/test_security_remediation.py`, `tests/test_admin_auth.py`, `tests/test_high_rbac_boundaries.py`, `tests/test_department_rbac_scope.py`, and `tests/test_restaurant_workflows.py`. The current suite includes cross-property credential replay rejection, expired/revoked-session rejection, refresh-versus-revocation race coverage, role-specific conversation access, and assigned-restaurant scoping; all pass.
- Conversation retention is property-scoped and tested. The master readiness audit still records broader location consent/retention/checkout/opt-out lifecycle work as incomplete; this is a pilot blocker, not a newly confirmed exploit in the reviewed changes.
- Docker Compose address allocation, internal database/cache network separation, proxy-only ingress, and forwarded-header trust settings were reviewed. Compose configuration validation and repository proxy-address tests pass. The recovery harness uses random names/ports, synthetic state, and cleanup. A fresh container runtime/write/recreate smoke passes. No real hotel proxy, controller, or external network was changed.
- PostgreSQL 16 backup/restore integration passed against a fresh disposable PostgreSQL 16 container. PostgreSQL/Redis recovery passed seven phases and 16 integration tests. No persistent or production database was used.
- Responsive browser checks cover all 42 administrator destinations and five guest views at nine viewport sizes. A fresh control inventory found 2,084 visible controls and 2,048 focusable controls, with zero enabled nonfocusable controls, zero missing accessible names, and no invalid composite widgets. Control counts vary with rendered fixture state; this run does not replace the prior committed receipt or change product acceptance counts.

## Files changed by this remediation

| File | Change |
| --- | --- |
| `.gitattributes` | Suppress textual display of the one evidence file containing the removed credential; the current-tree scan covers it. |
| `.github/workflows/ci.yml` | Pin Gitleaks action's requested version to 8.24.3 and add a checksum-verified Gitleaks current-tree scan. `secret-scan` remains a blocking workflow job, but GitHub required-check enforcement for `main` is currently disabled and was not changed. |
| `.gitleaksignore` | Add one exact historical fingerprint for a synthetic performance-only value removed from source. No blanket exclusions. |
| `.env.example` | Describe the optional maps key without an empty key assignment that resembles a credential. |
| `audit/evidence/security-2026-10-12/recovery-harness-before.txt` | Redact the three execution-environment credential copies. |
| `audit/evidence/security-2026-10-12/compose-proxy-before.txt` | Redact six synthetic environment values. |
| `audit/evidence/master-2026-10-12/container-postgres.log` | Redact five synthetic test credential values. |
| `playwright.config.js`, `tests/e2e/server_environment.js`, `tests/e2e/server-environment.spec.js` | Replace inherited host environment with an explicit synthetic test-server environment and regression coverage. |
| `scripts/failure_recovery_smoke.py`, `tests/test_failure_recovery_harness.py` | Whitelist recovery child-process settings and assert host credentials are excluded without returning environment values in fixture diagnostics. |
| `scripts/phase4_performance_sample.py` | Generate bootstrap/encryption test values per run. |
| `tests/test_ai_providers.py` | Construct its synthetic credential fixture at runtime so a full current-tree scan is clean. |

Playwright-generated screenshots and the generated control inventory were restored after testing; they are not part of this remediation.

## Verification results

| Check | Result |
| --- | --- |
| Backend pytest | **PASS** — 1,133 passed, 18 skipped, 0 failed; two upstream deprecation warnings. |
| Functional Playwright suite (`--grep-invert @visual`) | **PASS** — 281 passed, 35 skipped, 0 failed. Includes the host-environment exclusion regression. |
| Administrator/guest responsive and control inventory suite | **PASS** — 11 passed; all 42 admin destinations and five guest views checked at nine viewport sizes. |
| Bandit, medium severity/confidence | **PASS** — no findings above the configured threshold; existing SQL-fragment `nosec` and comment-parser warnings remain. |
| Python compile and `git diff --check` | **PASS**. |
| Gitleaks current worktree (`--no-git`) | **PASS** — zero findings. This is the added CI coverage for current files, including the diff-suppressed evidence. |
| Gitleaks failed-run first-parent diff, forced text | **FAIL, reproduced** — the same three historical findings at lines 10, 17, and 24 of the original commit. |
| Gitleaks all reachable history, forced text | **FAIL, expected** — the same three historical findings; no suppression or history rewrite. |
| Python dependency audit (`pip-audit`) | **BLOCKED** — PyPI DNS/network unavailable in this environment. |
| Node dependency audit (`npm audit`) | **BLOCKED** — npm registry DNS/network unavailable in this environment. |
| Docker Compose base, dev, load, and Phase 6 configs | **PASS** — validated with temporary synthetic settings. Phase 6 acceptance config validator also passes. |
| PostgreSQL/Redis integration and recovery | **PASS** — 16 integration tests and seven restart/interruption/reconnect phases. |
| PostgreSQL backup/clean-database restore | **PASS** — `tests/test_postgres_backup_integration.py`, 1 passed using PostgreSQL 16 tools in a disposable container. |
| Docker runtime | **PASS** — fresh build, production-settings validation, writes/health, and volume recreation persistence. |
| Full GitHub PR CI for this remediation | **PENDING** until the pushed branch workflow finishes. The latest main run above had only the secret-scan job fail. |
| GitHub required-check enforcement on `main` | **FAIL / BLOCKED** — repository metadata shows protection disabled and zero required status checks; no settings write tool was available. |

No load result in this review proves 30,000-user capacity. No live provider, hotel/customer data, property production infrastructure, or external credential was used or modified. The native hotel host, live TLS/reverse-proxy chain, controller/PMS integrations, off-host backup/key recovery, and representative capacity/soak checks remain unverified.

## Product acceptance and release decision

The existing 384-requirement matrix remains unchanged because this security remediation adds no product requirement that meets its evidence standard. Counts remain **207 VERIFIED COMPLETE**, **71 IMPLEMENTED BUT UNVERIFIED**, **56 PARTIALLY IMPLEMENTED**, **34 BLOCKED BY EXTERNAL DEPENDENCY**, **16 MISSING**, **0 BROKEN**, and **0 DEFERRED BY PRODUCT DECISION**. Verified acceptance is **207/384 (53.91%)**; full local implementation including unverified rows is **278/384 (72.40%)**.

- **Internal demo:** Allowed only with synthetic/non-customer data and the existing local-demo limitations. The current code and tests support this scope.
- **Limited hotel pilot:** **Blocked** by property-scoped location consent/retention/checkout/opt-out lifecycle, authoritative notification eligibility/frequency/deduplication and durable delivery, actual hotel WLAN/PMS/POS integration, physical device/captive-portal acceptance, and target-environment validation.
- **Production rollout:** **Blocked** by all pilot blockers plus clean target-host install/upgrade/reboot/rollback evidence, TLS and trusted-proxy/CIDR acceptance, encrypted off-host backup/key recovery, representative load/queue/AI/database bottleneck and soak measurements, and operational incident/recovery acceptance.

### Final release decision

**Do not approve hotel pilot or production release.** Keep this remediation PR in draft until the execution credential has been invalidated by its owner and an authorized Git-history sanitization plan is agreed. Current-tree code/evidence scanning is clean, but the leaked credential remains in reachable history. No merge, deploy, credential rotation, production-data mutation, or history rewrite occurred.
