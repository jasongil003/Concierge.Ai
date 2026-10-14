# Latest commit review and audit baseline

Date: 2026-10-14 (Asia/Manila)

## Repository state

- Repository: `jasongil003/Concierge.Ai`.
- Fresh fetch completed successfully. `HEAD`, `origin/main`, and `main` resolve to `6bc9fbba880389c08d8fc011383fc2274e632665` (`admin`).
- Parent: `4b36b5ecd39d8cda2e1c240dc1450d971244d77f`.
- Working branch: `codex/guest-concierge-premium-2026-10-13`.
- Working tree was clean before this report was created; no pre-existing user changes were present.
- The reference SHA supplied in the request is still the latest fetched `origin/main` commit.

## Commit change review

The complete parent-to-HEAD diff was reviewed. It changes ten files:

| File | Change and impact |
|---|---|
| `.gitleaksignore` | Adds one exact historical fingerprint for the former local-demo empty environment assignment false positive. The exception is scoped to a commit, file, rule, and line. |
| `README.md` | Removes the fixed `root` / `admin` quickstart credential and describes retrieving the generated source-install password from the host. |
| `app/properties.py` | Adds two narrow Bandit B608 suppressions for SQL with identifiers from the fixed `COLUMNS` tuple and values bound separately. No query behavior changes. |
| `docker-compose.yml` | Removes the production Compose fallback password and makes the variable mandatory. This closes a weak-default startup path. |
| `docs/RELEASE_CONTROLS.md` | Corrects the documented CI job inventory from seven to ten and explains that each must be required by repository rules. |
| `docs/audit/RELEASE_REMEDIATION_VERIFICATION_2026-10-14.md` | Records prior local remediation and test claims, including their limitations. These are historical receipts, not fresh results for this review. |
| `scripts/local-demo.sh` | Uses `unset` for provider credential variables instead of empty assignments. This preserves the local-demo intent and avoids a secret-scanner false positive. |
| `tests/test_compose_proxy_address_isolation.py` | Supplies an isolated synthetic bootstrap password to rendered Compose tests. |
| `tests/test_deployment_config.py` | Adds a regression asserting production Compose requires an explicit bootstrap password. |
| `tests/test_local_demo_isolation.py` | Adds a regression asserting the local demo unsets external-provider credentials. |

No production service, database, or deployment setting was changed by the commit. The source/configuration changes are fail-closed or scanner/test hygiene changes; no product path is intentionally removed.

## Baseline findings before remediation

| ID | Severity | Finding | Baseline disposition |
|---|---|---|---|
| SEC-H01 | High exposure | The prior sanitized security report identifies a genuine browser identity execution credential in `audit/evidence/security-2026-10-12/recovery-harness-before.txt`, commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`, with three historical detections. The report identifies the variable name as `BROWSER_USE_ACCESS_VERIFYING_IDENTITY`; its value is intentionally omitted. The issuing service, audience, validity, and permissions are unknown. This commit is reachable from the current branch and several local and cached remote refs. | Unresolved. No issuer evidence of invalidation exists. No credential was rotated, and no Git history was rewritten. Treat the credential as potentially compromised. |
| SEC-H02 | High pilot risk | Existing audits report that property-scoped location/AP observations lack an approved consent, opt-out, retention, checkout, export, and deletion lifecycle. | Unresolved; needs property policy and end-to-end lifecycle acceptance. |
| DEP-M01 | Medium | Before this commit, production Compose could supply the weak bootstrap-password fallback even though application production validation rejected it. | The current commit removes the fallback and adds regression coverage; fresh test and runtime verification pending. |
| GOV-M01 | Medium | The 2026-10-13 report recorded `main` protection and required checks disabled. No fresh remote settings evidence is present in the repository. | Remote governance status is unverified in this run. No settings changed. |
| DATA-M01 | High pilot risk | No owner-approved hotel content, prices, hours, menu data, map geometry, imagery rights, or accessibility routes are present as acceptance evidence. Synthetic tests cannot prove factual correctness. | Unresolved external acceptance requirement. |
| EXT-M01 | High pilot risk | Live AI provider, ANTlabs SG5/PMS/WLAN, target-host recovery, and representative capacity evidence are not supplied by local mocks or source review. | Unverified/blocked on external systems and approved test data. |

## Verification state at baseline

Fresh backend/browser tests, configured security scans, dependency checks, deployment checks, and a complete final diff review are pending. Prior receipts in `docs/audit/` are not counted as current-run verification. This report will be updated with current evidence and any changes made during remediation.

## Current-run review and remediation update

The baseline pending statement above is superseded by this section.

### Confirmed CI gap and local correction

The configured Gitleaks history action did not catch the known historical credential in the non-diffable evidence artifact. Gitleaks 8.24.3 returned zero findings for its default history diff, but returned three `generic-api-key` detections when scanning all reachable refs with `--text`, at lines 10, 17, and 24 of the same artifact in commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`.

Added a second, redacted Gitleaks history command to `.github/workflows/ci.yml` using `--log-opts="--all --text"`, and added `test_secret_scan_forces_redacted_text_diff_across_all_reachable_history` in `tests/test_supply_chain_controls.py`. The command is intentionally fail-closed while those historical detections remain. It does not suppress the credential or rewrite repository history. A nearby B608 rationale was also added to the `PropertyStore.create_if_absent` query in `app/properties.py`; query behavior is unchanged.

### Fresh verification

| Check | Result |
|---|---|
| Repository fetch and commit comparison | **PASS** — fetched `origin`; `HEAD` and `origin/main` remain `6bc9fbba880389c08d8fc011383fc2274e632665`; working branch was based on the supplied SHA. |
| Backend suite | **PASS** — `1,185 passed, 18 skipped, 0 failed`; 2 upstream deprecation warnings; 51.91s. Persistent repository SQLite database hash and journal/WAL sidecars were unchanged. |
| Playwright | **PASS** — `334 passed, 38 project-specific skips, 0 failed` across Chromium and Pixel 7 emulation; 6.2 minutes. All 9 Chromium responsive viewports passed. The control inventory covered 42 admin destinations, 5 guest views, and 2,125 visible controls, with 0 enabled non-focusable controls and 0 missing accessible names. |
| Python compilation | **PASS** — `.venv/bin/python -m compileall -q app`. |
| Bandit | **PASS** — configured Medium/High scan: 0 findings. Reviewed all 46 `nosec` directives; they are B608-only and limited to fixed/allowlisted identifiers, fixed predicates, or generated placeholders with separately bound values. The new property insert suppression now has a rationale at the query site. |
| Python dependency audit | **PASS** — `pip-audit -r requirements-dev.txt`: no known vulnerabilities. |
| Node dependency audit | **PASS** — online `npm audit --audit-level=high`: 0 vulnerabilities across 3 packages. |
| Gitleaks current worktree | **FAIL / unresolved local configuration** — one redacted `generic-api-key` match at `.env:5`, which is ignored and untracked; the variable name is `CREDENTIAL_ENCRYPTION_SECRET`. Its value was not printed or classified as production configuration. No other current-tree findings were returned. |
| Gitleaks reachable history with forced text diffs | **FAIL / known high finding** — 3 detections in the historical recovery-harness artifact at the commit and lines listed above. No value was printed. |
| Compose configuration | **PASS** — synthetic production Compose config parses; omitting `ADMIN_BOOTSTRAP_PASSWORD` fails interpolation as intended. |
| Docker/PostgreSQL/Redis runtime | **BLOCKED** — Docker daemon unavailable; integration tests skipped because no `DATABASE_URL`/`REDIS_TEST_URL` services were configured. |
| GitHub branch protection | **BLOCKED** — read-only GitHub API returned HTTP 401 without authentication. No repository setting was changed. |

### Final repository state for this review

- The latest commit remains `6bc9fbba880389c08d8fc011383fc2274e632665`; the audit and remediation changes are uncommitted local worktree changes.
- Playwright-generated edits to the historical `audit/evidence/browser-2026-10-12/` files and the old control-inventory JSON were restored to their pre-test contents. Fresh screenshots and the current control inventory are kept under `docs/audit/evidence/guest-ui-acceptance-2026-10-14/`.
- Dated errata were appended to `docs/audit/RELEASE_REMEDIATION_VERIFICATION_2026-10-14.md` and `docs/audit/SECURITY_FINDINGS.md` to correct their earlier clean-history scan claim.
- No external credential was rotated, no history was rewritten, no production data or services were changed, and no remote repository settings were modified.
- The historical credential remains a release blocker pending issuer-owner invalidation evidence and authorized history cleanup. See `SECURITY_REMEDIATION.md` and `RELEASE_READINESS.md`.
