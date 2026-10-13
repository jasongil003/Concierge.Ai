# Master test results

Date: 2026-10-12–13 (Asia/Manila). Baseline `41c0ea1a7937035db6078cbb944f1e94f2fbad63`; final tested implementation commit is in `MASTER_RELEASE_READINESS.md`. Environment: Darwin arm64, Python 3.11.16, Node 26.7.0, isolated synthetic SQLite, desktop Chromium/Pixel 7 emulation. Persistent SQLite safety guard reported unchanged state. No customer records or production deployment were used.

## Execution ledger

| Check / command | PASS | FAIL | SKIP | Result / evidence |
| --- | ---: | ---: | ---: | --- |
| Baseline `.venv/bin/python -m pytest -q --junitxml=.../backend.xml` | 1100 | 0 | 18 | `evidence/master-2026-10-12/backend.log` / XML |
| Final `.venv/bin/python -m pytest -q --junitxml=.../backend-final.xml` | 1132 | 0 | 18 | `evidence/master-2026-10-12/backend-final.log` / XML; 59.77 s |
| Dashboard reproduction before fix | 2 | 3 | 0 | `evidence/security-2026-10-12/legacy-dashboard-before-fix.txt`; fixture setup errors retained in security notes |
| Final broader security subset | 660 | 0 | 2 | Overlaps full backend suite; do not add as unique tests |
| Quiet-hours reproduction before fix | 6 | 3 | 0 | `quiet-hours-before.log` |
| Quiet-hours plus roadmap regressions after fix | 13 | 0 | 0 | `quiet-hours-after.log`; overlaps final suite |
| Initial functional browser run with old privacy assertion loaded | 277 | 2 | 35 | `browser-2026-10-12/playwright-full.log`; stale assertion failed after corrected product copy |
| Focused classic-scrollbar/privacy/responsive checks after layout correction | 8 | 0 | 0 | `layout-fixed.log`; later static disclosures also covered in the complete final run |
| Functional candidate before fixing fixture teardown race | 278 | 1 | 35 | `playwright-final.log`; route response disposed during early absence assertion; failure retained |
| Complete candidate before empty renderer correction | 281 | 2 | 35 | `playwright-accepted.log`; startup-ready assertions exposed the empty Quick actions heading in both projects |
| Complete functional + visual browser suite | 283 | 0 | 35 | `playwright-release.log`; 5.8 min |
| Final candidate functional + visual browser suite | 283 | 0 | 35 | `playwright-final-candidate.log`; 5.6 min; final application source |
| PDF report layout reproduction → correction | 0 → 10 | 2 → 0 | 0 | `pdf-layout-before.log` / `pdf-layout-after.log`; two coordinate regressions, ten related checks after |
| Legacy knowledge publication reproduction → correction | 0 → 49 | 3 → 0 | 0 → 1 | Security `legacy-knowledge-before.txt` / `legacy-knowledge-after.txt`; five new permission/race regressions, broader related checks |
| PostgreSQL integration with matching PostgreSQL 16 tools | 14 | 0 | 0 | `container-postgres-final.log`; 3.70 s, fresh synthetic migrated database |
| Real PostgreSQL publication guard | 1 | 0 | 0 | `container-postgres-approval.log`; verifies actual SQL write predicate and unchanged guest fact after rejection |
| Real Redis integration | 4 | 0 | 0 | `container-redis.log`; shared limits/bulkheads against isolated service |
| Container runtime smoke | 4 phases | 0 | 0 | Security `docker-runtime-smoke.log`; packaging, production validation, non-root writes, recreation persistence |
| Failure/recovery smoke | 7 phases; 16 tests | 0 | 0 | Security `failure-recovery-remediated-smoke.log`; PostgreSQL/Redis interruptions and intact recovered configuration |
| Phase6 restart/ingress focused regressions | 6 | 0 | 0 | `phase6-ingress-final-regressions.txt`; three new regressions, reserved address checks overlap full suite |
| Repeated staging startup and proxy boundaries | 6 HTTP checks + start/health | 0 | 0 | `phase6-final-repeat-start.log`, `phase6-final-health.log`, `phase6-proxy-boundary-checks.json`: health/login200, anonymous401, supplied forwarding426, unknownHost400 |
| Linux PDF kernel memory enforcement | 1 probe | 0 | 0 | Security `linux-pdf-kernel-enforcement.json`; 384 MiB RLIMIT_AS blocks 768 MiB allocation as UID 10001 |

All failed reproduction, fixture and earlier suite results are historical evidence; none is relabeled a pass. Final counts refer to unique cases in their respective final suites. Browser skips are explicit desktop/mobile/project exclusions; backend skips: 14 PostgreSQL cases, two Redis integration cases, Linux RLIMIT_AS, and systemd validation. Skips are not passes.

Additional completed checks: compileall, JS syntax, `git diff --check`, Bandit medium/confidence threshold (exit 0), isolated Compose config (exit 0), npm audit (zero advisories), clean requirements-dev pip-audit (78 resolved packages, zero advisories). Installed virtual environment initially had 15 advisory entries across pip/setuptools/Werkzeug; after scoped upgrades its 97-package audit found zero, and pip check passed. Original JSON is retained.

## Twenty requested journey checks

These are mapped contracts across separate isolated tests, not a single live hotel installation/AI/gateway journey. PASS applies only to the scope stated.

| # | Journey | Result | Executed local evidence / boundary |
| --- | --- | --- | --- |
| 1 | Create property | PASS | Admin onboarding plus `test_super_admin_can_create_the_first_property` |
| 2 | Configure branding | PASS | Published property branding/home prompts and logo-upload workflows |
| 3 | Configure landing page | PASS | Builder sections/theme/device/inspector/reordering tests |
| 4 | Publish design | PASS | Full draft/preview/publish/persist/discard workflow; store history/restore regressions |
| 5 | Configure knowledge | PASS | Browser reviewable upload; backend review/approval/publish/expiry/property isolation |
| 6 | Configure AI | PASS | Encrypted connection/settings and authorized configuration; live provider acceptance BLOCKED |
| 7 | Create restaurant | PASS | Restaurant ownership/assignment CRUD in hospitality/RBAC suites |
| 8 | Add menu | PASS | Restaurant menu approval/publish/item-property boundary tests |
| 9 | Configure facilities | PASS | Facilities empty/search/CRUD browser workflow and store validation |
| 10 | Create guest session | PASS | Credential-bound synthetic guest start; SG5 admission BLOCKED |
| 11 | Ask concierge questions | PASS | Verified hotel data, inert AI text, explicit unavailable fallback; real model quality BLOCKED |
| 12 | Submit request | PASS | Explicit confirmation returns persisted backend request ID; My Requests renders record |
| 13 | Process as staff | PASS | Request transition/authorization and restaurant-staff conversation/reply contracts |
| 14 | Review dashboard | PASS | Truthful host/record telemetry, timeframe handling; scoped legacy dashboard regressions |
| 15 | Export report | PASS | Record-derived XLSX/PDF export contract, formula neutralization and export permissions |
| 16 | Reconnect session | PASS | Resume credential rotation and pseudonymous stay continuity tests |
| 17 | Expire/revoke session | PASS | Already-expired rejection, validated-expiry race, later revocation refusal |
| 18 | Validate complete cleanup | BLOCKED | Local stay anonymization/preference cleanup passes; location observation/visit/transition lifecycle remains missing software work |
| 19 | Restricted-role access | PASS | Direct API positive/negative RBAC, UI restrictions and custom role delegation |
| 20 | Cross-property isolation | PASS | Host/property guest/admin/restaurant/knowledge/map/request boundaries |

Journey ledger: **19 PASS, 0 FAIL, 0 SKIP, 1 BLOCKED**, with limited local scope as above. This is a separate checklist and must not be added to test-case totals.

## External/platform acceptance ledger

Five deployment acceptance groups remain BLOCKED: (1) actual hotel TLS/Nginx SSE/network policy and clean install/upgrade/reboot/rollback/off-host encrypted restore; (2) live authorized AI quality/cost/throughput; (3) SG5/PMS/controller/WLAN facts; (4) physical captive/iOS/Android/assistive-device acceptance; (5) representative staged capacity/soak. Local Docker/Linux/PG/Redis migration, backup restore, non-root persistence and interruption recovery now have fresh candidate evidence. Missing local software is tracked separately in the matrix/backlog.

Remote historical PR #52 evidence was recovered: CI run `38247953936` tested synthetic merge `976184725c2212fc330e0b3ea3f7e11c6e556052`, head `d328484`. Nine jobs passed, including PostgreSQL/Redis (1 migration + 17 integration tests), Docker persistence/Trivy/secret scan and dependency audits. Browser job failed: **273 PASS, 2 FAIL, 35 SKIP**. Retained receipts/excerpts are in `evidence/master-2026-10-12/github-*`. These are baseline evidence, not final audit-branch CI or deployment certification.

Failure screenshots and focused traces are retained beside the logs. Large all-test traces remain local and are indexed in the artifact manifest; current responsive screenshots cover all nine widths. Historical documentation screenshots were restored from baseline. Only uniquely named audit-owned resources are eligible for cleanup; existing unrelated services and databases were preserved.

## Infrastructure failure history and source identity

Earlier attempts are retained, not folded into passing totals: Docker was initially stopped; native loopback service attempts refused connections; the safety guard rejected non-loopback aliases; a fresh database was queried before its migration completed; a reused staging database run had three failures (bootstrap credential fixture and backup restore); a fresh migrated database with PostgreSQL 17 client had 13 PASS/1 FAIL because pg_restore emitted unsupported `transaction_timeout` to server 16. Matching PostgreSQL 16 tools fixed the real restore and the complete suite passed. The initial runner build tried resolving a local digest remotely; the legitimate existing local-image template fixed that tooling issue. A full backend run then caught the runner Dockerfile naming contract (1121 PASS/1 FAIL/18 SKIP); the corrected build follows the existing contract, without weakening the scanner. Recovery smoke twice returned 401 before separate synthetic credentials/database fixtures were corrected. The final restart attempt also reproduced a Compose one-off static-address collision; its correction and host-proxy acceptance are recorded in the security receipt.

Production image source hashes match all eight changed application/backend/frontend files (`packaged-source-comparison.json`, all true); image SHA and runner receipts are retained. Container labels originally identify d2d09ba9 plus the tested uncommitted source; final committed source identity is recorded in the release receipt. These service checks overlap local skipped/in-process cases and are reported separately, not added to unique suite totals. Final audit-branch hosted CI/Trivy/Gitleaks were not executed; historical CI remains historical.

Final infrastructure fixture history: the newly added fake Docker script first had an interpreter path containing spaces, then reported fake volumes present without a runtime env. Both fixture failures are retained (`phase6-ingress-restart-after.txt`, `phase6-ingress-mock-volume-fixture-failure.txt`); the corrected mock follows the Unix-socket and missing-volume safety contracts. A command initially named a nonexistent test file and exited4 without running cases; the corrected focused command passed6. Docker Desktop had stopped before the continued session; it was restarted for final owned-stack verification. These are not product passes. Final full-suite execution after all source/test changes:1132 PASS,18 SKIP,0 FAIL,59.77s.

The native-host Phase6 `test` path expects published PostgreSQL/Redis loopback ports. On this Docker Desktop version, internal bridges did not publish those service listeners; that command path remains unaccepted here. Actual integration was accepted via separately scoped non-root container runners sharing each service network namespace, preserving the application's loopback-only test-URL guard. This is a known harness portability follow-up, not missing PostgreSQL/Redis product implementation. No final-candidate hosted CI or hardware acceptance was substituted.

Final tested implementation commit: `ecfe3f42963896cd86a291450fa574a4c26b197f`. Reports/evidence are committed separately; their receipt is discoverable with `git log -1 -- audit/MASTER_TEST_RESULTS.md`. All test results refer to these unchanged committed implementation bytes, including explicitly scoped container receipts and local skips.
