# ECC test results

**Audit date:** 2026-10-14 (Asia/Manila)  
**Starting branch/commit:** `codex/guest-concierge-premium-2026-10-13` / `82f9df2bafb4b3a632912762364fd6c7dff4a532`  
**Local host:** Darwin arm64, Python 3.11.16, Node v26.7.0, Playwright 1.63.0.  
**Status terms:** LOCAL PASS refers only to this workspace and machine; REMOTE CI has not been observed for these edits.

## Executed checks

| Check | Local result | Scope and limits |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q` before audit edits | **LOCAL PASS:** 1,185 passed, 18 skipped, 2 warnings, 52.99 s | Full backend baseline. Persistent workspace SQLite signature unchanged. |
| `.venv/bin/python -m pytest -q tests/test_test_database_isolation.py tests/test_source_install.py` | **LOCAL PASS:** 33 passed, 1 skipped, 2 warnings, 4.47 s | Focused post-fix dotenv/test isolation and installer checks. |
| `.venv/bin/python -m pytest -q -rs` after test-isolation and report fixes | **LOCAL PASS:** 1,186 passed, 18 skipped, 2 warnings, 47.66 s | Intermediate full backend suite. Persistent workspace SQLite signature unchanged. |
| `.venv/bin/python -m pytest -q tests/test_backup_restore.py tests/test_observability_reporting.py` | **LOCAL PASS:** 16 passed, 2 dependency warnings | Focused restore failure-injection and report formatting regressions. |
| `.venv/bin/python -m pytest -q -rs` after all backend fixes | **LOCAL PASS:** 1,187 passed, 18 skipped, 2 warnings, 45.43 s | Final full backend suite. Persistent workspace SQLite signature and absent WAL/journal sidecars unchanged. |
| `npm run test:e2e -- --grep-invert @visual` | **LOCAL PASS:** 330 passed, 38 skipped, 0 failed, 6.2 min | Desktop Chromium and Pixel 7 mobile Chrome emulation. This run began before the new dotenv harness and guest-scroll regression tests were written; their focused reruns are recorded separately. The test server used disposable SQLite. |
| `npm run test:e2e -- --grep-invert @visual` after all local changes | **LOCAL PASS:** 332 passed, 38 skipped, 0 failed, 6.2 min | Final complete functional browser rerun across both configured projects with synthetic disposable state. Includes the new scroll and test-environment regressions. |
| `npx playwright test tests/e2e/guest-scrollbar.spec.js --project=chromium --grep 'newly completed long reply'` and the matching `--project=mobile-chrome` command | **LOCAL PASS:** 1 passed in each project | Post-fix 390×700 long-reply assertion; fresh before/after Chromium screenshots in `docs/audit/evidence/`. |
| `npx playwright test tests/e2e/server-environment.spec.js` | **LOCAL PASS:** 2 passed | Post-fix assertion that both browser projects' test server excludes host credentials and repository dotenv. |
| `bash -n` and `shellcheck --severity=warning -x` over Linux, macOS, shared deployment shell scripts | **LOCAL PASS:** exit 0 | Static shell checks; no actual install or service restart. |
| `plutil -lint deploy/macos/*.plist` | **LOCAL PASS:** six plists accepted | Does not launch the services. |
| `.venv/bin/python -m compileall -q app deploy scripts` | **LOCAL PASS:** exit 0 | Python syntax/bytecode compilation only. |
| `node --check app/static/app.js`, `admin.js`, `admin-login.js` | **LOCAL PASS:** exit 0 | JavaScript syntax only. The frontend is plain static assets; `package.json` does not define a separate lint/typecheck/production-build script. |
| `docker compose --env-file .env.example -f docker-compose.yml config -q` with ephemeral synthetic required values | **LOCAL PASS:** exit 0 | Compose interpolation and topology validation; no image build or runtime. The first attempt without required values failed closed as intended. |
| `npm audit --offline --json` | **LOCAL PASS:** zero locally cached advisories across three dependency entries | Offline cache only; no current registry verification. |
| `.venv/bin/python scripts/phase4_performance_sample.py` | **LOCAL PASS:** 101 iterations per operation | In-process shell/health/transcript microbenchmark in temporary SQLite; see `ECC_PERFORMANCE_REPORT.md`. |
| `.venv/bin/python scripts/master_audit_http_sample.py` | **LOCAL PASS:** 300/300 HTTP 200 across three bounded stages; restart health passed | Temporary loopback server, synthetic SQLite, no AI or guest workflow; see `ECC_PERFORMANCE_REPORT.md`. Initial sandbox attempt was blocked from binding localhost; the run succeeded with local socket permission. |

## Backend skips and warnings

- **14 PostgreSQL cases:** 12 in `tests/test_postgres_integration.py`, one backup/restore case, and one SQLite-to-PostgreSQL migration case. `DATABASE_URL` and, for backup, `PG_DUMP_AVAILABLE` were absent. A PostgreSQL service was not provisioned locally.
- **2 Redis cases:** distributed provider bulkhead and Redis rate limiter need `REDIS_TEST_URL`; no local Redis service was provisioned.
- **1 platform case:** Linux `RLIMIT_AS` acceptance is not applicable on this macOS host.
- **1 platform case:** `systemd-analyze` is not installed on this macOS host.
- The two warnings came from `starlette.testclient` and AnyIO deprecations in installed dependencies. They did not fail tests; compatibility should be reassessed when dependencies change.

## Browser and deployment status

The 38 Playwright skips are deliberate project-specific exclusions: admin mutation and control sweeps are run once on Chromium, while the mobile navigation sweep runs on mobile Chrome. The guest screenshot matrix also skips without its optional output directory. A separate full visual snapshot run was not performed; the targeted long-reply case has fresh before/after screenshots. Physical iPhone/Android hardware, Safari/WebKit, guest Wi-Fi gateway, real AI providers, PostgreSQL/Redis, TLS proxy, clean Ubuntu/WSL installation, reboot, and off-host restore remain **UNVERIFIED** here.

The browser suite rewrote tracked historical `audit/evidence` captures. Those generated modifications were restored to their pre-run Git state after both complete runs; no unrelated application or report edits were reverted.

Docker CLI and Compose configuration parsing were available, but the local Docker daemon socket was absent. No image build, container smoke, PostgreSQL/Redis service integration, Nginx syntax runtime check, or Docker load test was run. The macOS workflow and Linux systemd validation are defined in CI, but this audit did not observe their remote result. The release workflow is triggered by published releases; no release was created or modified.

**REMOTE CI status:** UNVERIFIED for the working-tree edits. A local test pass must not be reported as a GitHub Actions pass.

## 2026-10-14 follow-up from `6de7319`

| Check | Result | Limit |
| --- | --- | --- |
| Baseline `.venv/bin/python -m pytest -q` | **PASS** — 1,187 passed, 18 skipped | Before follow-up edits; synthetic local tests. |
| Final `.venv/bin/python -m pytest -q` | **PASS** — 1,188 passed, 18 skipped, 2 dependency warnings | Persistent workspace SQLite signature unchanged. |
| Focused SSE grounding tests | **PASS** — 2 passed | Includes fabricated claim rejected before any `text.delta` event. |
| Focused Playwright Chromium | **PASS** — 3 passed | New-chat failure, transient history outage, and existing composer regression. |
| Focused Playwright mobile Chrome emulation | **PASS** — 2 passed | New-chat failure and transient history outage. |
| Bandit Medium/High; Python compile; JavaScript syntax; `git diff --check` | **PASS** | Bandit emitted existing `nosec` parser warnings; no configured-threshold findings. |
| Gitleaks 8.24.3 forced-text history scan | **FAIL / RELEASE BLOCKER** — three historical findings | Credential value omitted; no suppression. Current local `--no-git` scan also matches an ignored `.env` value, so it is not a clean-tree receipt. |
| PostgreSQL/Redis, Docker, live AI providers, physical devices, full browser rerun, staged 30,000-session load | **NOT RUN / UNVERIFIED** | These checks require their respective services, hardware, or longer controlled run. |

The [failed GitHub secret-scan job](https://github.com/jasongil003/Concierge.Ai/actions/runs/38566811348/job/115861890755) completed its initial history step, then failed in the step that includes the forced-text scan. Draft [PR #54](https://github.com/jasongil003/Concierge.Ai/pull/54) prepares an offline mirror cleanup but does not close the finding. CI for the follow-up changes is unverified until their new PR runs.

## 2026-10-15 verification on fetched `main` `8ee80d2d688584795b6140582d609f81479b2137`

| Check | Result | Scope / limit |
| --- | --- | --- |
| Baseline long-chat regression repeated 12 times per browser project | **FAIL:** 22 passed, 2 failed | Both Chromium and mobile Chromium reproduced `scrollTop=100` jumping to `3140` before the code correction. |
| Same focused regression repeated after code correction | **PASS:** 24 passed, 0 failed | Original test across both projects. |
| Expanded held-response scroll regression | **PASS:** 2 passed | Desktop/mobile; pending and completed answer preserve reading anchor, near-bottom follows the next answer, composer stays separate. Uses a response gate rather than an arbitrary delay. |
| Rich restaurant menu and late image layout | **PASS:** 2 passed | Desktop/mobile projects; 390×844, 768×1024, 1440×900 screenshots were opened and visually reviewed. No observed menu/composer overlap. Synthetic restaurant and image. |
| Full functional Playwright `--grep-invert @visual` | **PASS:** 336 passed, 38 skipped, 0 failed | Desktop Chromium and Pixel 7 mobile emulation, 6.3 minutes, isolated local server and temporary data. The 38 skips are project-specific. Tracked older screenshot fixtures regenerated by the suite were restored after inspection. |
| Full `.venv/bin/python -m pytest -q` | **PASS:** 1,188 passed, 18 skipped, 2 dependency warnings | 51.69 seconds; persistent workspace SQLite signature and absence of WAL/journal files unchanged. PostgreSQL/Redis/platform-dependent cases are skipped locally; run 38579415155 separately reports PostgreSQL/Redis job success. |
| `npm audit --audit-level=high` | **PASS:** zero vulnerabilities across three dependency entries | Fresh online advisory query. |
| `.venv/bin/pip-audit -r requirements-dev.txt` | **PASS:** no known vulnerabilities | Fresh online advisory query. |
| Bandit Medium/High, Python compile, JavaScript syntax, shellcheck, plist validation, Compose config, `git diff --check` | **PASS** | Bandit reported no threshold findings and emitted existing `nosec` parser warnings. Compose used synthetic configuration values. Docker daemon was unavailable, so no local image/runtime test ran. |
| Gitleaks 8.24.3 current tracked snapshot | **PASS:** 0 findings in 953 baseline files and 955 staged final files | Temporary tracked-file copies were scanned. The full local worktree scan separately found one ignored `.env:5` configuration match; its value was neither printed nor committed. |
| Gitleaks 8.24.3 forced-text all-reachable history | **FAIL:** 3 known historical detections | Same documented credential-bearing commit/path/lines; real unresolved exposure. Gitleaks remains a CI gate. |
| Separate sanitized mirror preparation | **PARTIAL:** known path no longer reachable; forced-text scan still fails with 9 documented synthetic patterns | Rewritten hashes invalidate exact historical `.gitleaksignore` fingerprints. Mirror stays offline; it is not a clean-history certificate. |
| Live AI latency/memory/concurrency, physical SG5/PMS, real mobile keyboard, off-host recovery, 30,000 sessions | **NOT RUN / UNVERIFIED** | No authorized representative provider, hotel network, device, target host, or load environment was available. These cannot be inferred from synthetic suites. |

GitHub Actions run [38579415155](https://github.com/jasongil003/Concierge.Ai/actions/runs/38579415155) had passing backend, PostgreSQL/Redis, dependency-security, static-security, and macOS/Linux deployment jobs; `browser-tests` and `secret-scan` failed. This local pass does not change that historical run. New branch CI must be observed separately.

## 2026-10-15 continuation on merged `main` `d4649ff138c8ee9b6b8a681aae2132874894a7a2`

The checkout contains preexisting uncommitted priority-feature work. Initial full backend verification found six failures from changed map publication, notification claim ordering, and grounded dining paths. After correction, `.venv/bin/python -m pytest -q --tb=short` passed **1,301 / 18 skipped / 2 dependency warnings** in 59.78 seconds. The persistent workspace SQLite signature and absent WAL/journal sidecars were unchanged. Focused `tests/test_intelligent_ui.py tests/test_zone_routing_safety.py` passed **68 / 0 failed** after the direction response schema correction.

Initial full Playwright desktop/mobile run: **336 passed, 39 skipped, 7 failed**. Failures isolated a short desktop map layout, suite-dependent guest fixture, unpublished synthetic maps, and direction response validation. The seven affected cases passed in focused reruns after correction, including the longer map interaction test in both browser projects. The final `npx playwright test --reporter=line` rerun passed **343 / 39 skipped / 0 failed** in 6.4 minutes with a disposable test server. Python compile, JavaScript syntax, and `git diff --check` passed. Playwright-regenerated tracked inventory and screenshot fixtures were restored after the run. Remote CI for the uncommitted branch has not run.

The CI Bandit command (`bandit -q -r app -x app/static --severity-level medium --confidence-level medium`) initially reported seven medium B608 cases in the new SQL paths. After parameterizing optional predicates and documenting fixed table-name allowlists, the same threshold reports **0 issues**. Gitleaks 8.24.3 scanned the current worktree with `--no-git --redact`: **one finding in the ignored local `.env`**, no other current-file findings. No secret value was printed. This does not alter the three real historical findings or clear the `secret-scan` release gate.

Draft [PR #57](https://github.com/jasongil003/Concierge.Ai/pull/57) triggered [CI run 38691430521](https://github.com/jasongil003/Concierge.Ai/actions/runs/38691430521). Backend, static security, dependency audits, Docker runtime, and Linux/macOS deployment validation passed. PostgreSQL/Redis integration failed while importing the app after SQLite-to-PostgreSQL migration because `guest_privacy_consents` was absent from Alembic revision `20261015_0003`; the migration and repeatability test were corrected afterward, with focused local tests **27 passed**. The browser job was still running when last checked. `secret-scan` found no leaks in the new commit or current CI worktree, then failed on **three known reachable historical findings**. Updated-head remote CI remains required for the PostgreSQL correction.

## 2026-10-16 guest lifecycle and notification change on `codex/guest-lifecycle-notifications-20261016`

Base: fetched `main` `7185e18df2ae3b8f100804b7c3618a3909a831b6`. Local tested commit `7031cf0eca6a076d5ab80d650be0d0e05874598d` is published in draft [PR #61](https://github.com/jasongil003/Concierge.Ai/pull/61) at remote commit `03f07aa9cfbe2029943cdec013524a3e85b48889`. The full hosted run is [#246](https://github.com/jasongil003/Concierge.Ai/actions/runs/38835174052).

| Check | Result | Scope / limit |
| --- | --- | --- |
| Focused lifecycle, consent, notification, and personalization tests | **PASS:** 48 passed, 2 warnings | Covers long stays, schema migration, checkout-based retention, reconnect, property isolation, concurrent cleanup, consent cascades, opt-out deletion/recovery, event suppression, DST, invalid timezone, and checkout preference purge. |
| Full `.venv/bin/python -m pytest -q -rs` | **PASS:** 1,319 passed, 21 skipped, 2 warnings, 60.43 s | Local suite. PostgreSQL/Redis/backup and platform-dependent checks were skipped without their service/tooling. The new PostgreSQL cleanup regression passed in hosted PostgreSQL/Redis integration on run #246. Persistent SQLite safety check reported unchanged. |
| `npm run test:e2e -- --grep-invert @visual` | **PASS:** 339 passed, 39 skipped, 0 failed, 6.3 min | Desktop Chromium and mobile Chrome emulation; isolated local Playwright server and disposable test database. Existing project-specific and visual exclusions remain. Test-generated tracked screenshots/inventory were restored. |
| `.venv/bin/python -m compileall -q app`, Bandit medium severity/confidence, `git diff --check` | **PASS** | Bandit exit 0 with existing `nosec` and comment warnings; no configured-threshold findings. |
| `pip-audit -r requirements-dev.txt` | **NOT COMPLETED locally** | pip-audit failed while trying to upgrade temporary pip tooling in this restricted environment. No dependency files changed; hosted Python and Node dependency audits passed on run #246. |
| Local Gitleaks | **NOT AVAILABLE** | The executable is not installed. Do not infer secret-scan success. |
| Hosted CI #246 | **COMPLETED; all jobs passed except secret scan** | Backend passed (1,321 passed, 19 skipped), browser passed (339 passed, 39 skipped), PostgreSQL/Redis integration, Docker runtime, dependency audits, static security, and Linux/macOS deployment passed. Secret scan failed at its redacted current-worktree step; the later forced-text history step did not run. This is PR #61 head `03f07aa9cfbe2029943cdec013524a3e85b48889`. |

The current branch does not contain dependency changes. No production data, gateway, provider account, or deployment configuration was accessed. Continue to treat the historical credential, failed current-worktree secret scan, and missing required CI checks as open release blockers.

## 2026-10-16 signed guest wayfinding QR on `codex/final-remediation-20261016`

The candidate adds signed, property-bound HTTPS QR links for published guest-visible waypoint nodes. The guest endpoint resolves only the currently published map/node, rejects tampered or cross-property signatures, and seeds the route origin while keeping QR signature fields out of gateway context. The acceptance ledger marks K-18 locally verified; real-device scanning, printing, and hotel map/waypoint accuracy remain untested.

| Check | Result | Scope / limit |
| --- | --- | --- |
| `tests/test_guest_entry.py` | **PASS: 6 passed** | Signature property/node binding, published-map QR generation and guest resolution, tampering, cross-property, and hidden-node denial. Ran with the isolated `/private/tmp/phase5-venv` environment and disposable dependency path. |
| Admin wayfinding QR Playwright | **PASS: 1 passed** | Chromium; real local admin API, synthetic published map/node, SVG QR and HTTPS signed URL. |
| Guest wayfinding QR Playwright | **PASS: 2 passed** | Desktop Chromium and mobile Chrome; published map, start origin, destination selection, gateway-context filtering, and new-chat continuity. |
| JavaScript syntax, JSON policy parse, `git diff --check` | **PASS** | `app/static/admin.js`, `app/guest_v2/app.js`, both changed e2e files, and `app/admin_route_policies.json`. |
| Gitleaks 8.24.3 current worktree | **PASS: 0 findings** | No-git redacted scan. Full-history hosted secret scan remains a release gate. |

Prior full local runs remain separate: backend **1,329 passed, 21 skipped, 5 failed** (the five installer tests could not bind because a pre-existing process held port 8080); nonvisual browser **351 passed, 39 skipped**; visual browser **4 passed**. No new full-suite run is claimed for this QR change.

Draft [PR #63](https://github.com/jasongil003/Concierge.Ai/pull/63) is mergeable and remains open. Hosted run [#258](https://github.com/jasongil003/Concierge.Ai/actions/runs/38861282815) completed at corrected code head `79a33c5c4fdd9de55b8182d5ae6d1ce68f4d1693`: **9/10 jobs passed**. Backend passed **1,348 tests, 19 skipped**; browser passed **356 tests, 40 skipped**; PostgreSQL/Redis, Docker, Python/Node dependency, static-security, and Linux/macOS deployment checks passed. Full-history Gitleaks failed on three known historical findings; its PR-diff and current-worktree scans each reported no leaks. No merge or deployment was performed.

## 2026-10-16 PR #63 hosted candidate run #259

| Check | Result | Scope / limit |
| --- | --- | --- |
| Backend workflow suite | **PASS:** 1,348 passed, 19 skipped | Hosted CI run [#259](https://github.com/jasongil003/Concierge.Ai/actions/runs/38862722596), head `4563d0064da1e306a67f173a8b729d99811aec7b`. |
| Browser workflow suite | **PASS:** 356 passed, 40 skipped | Hosted CI run #259. Physical iOS/Android and hotel Wi-Fi acceptance remain open. |
| PostgreSQL/Redis, Docker runtime, Python/Node dependency audits, static security, Linux/macOS deployment validation | **PASS** | Hosted CI run #259. These checks do not certify target-hotel installation or live integrations. |
| PR-diff and current-worktree Gitleaks scans | **PASS:** no findings | Run #259. |
| Forced-text full-history Gitleaks scan | **FAIL / RELEASE BLOCKER:** three known historical findings | Run #259. Values omitted; the credential issuer must confirm revocation before owner-authorized shared-history cleanup. |

The run completed with 9/10 jobs passing. Draft PR #63 remains open and mergeable, but release acceptance is **RED**. Consent/location software is covered by `tests/test_guest_privacy_consent.py`; property/privacy-owner approval of retention and deletion policy, allowed notification audiences, and live hotel/provider acceptance remain outstanding.

## 2026-10-16 local pagination change — commit `97369c6`

| Check | Result | Scope / limit |
| --- | --- | --- |
| Backend/property-scope/privacy/notification regression set | **PASS:** 57 passed, 2 deprecation warnings | `tests/test_conversation_pagination.py`, `tests/test_restaurant_workflows.py`, `tests/test_guest_privacy_consent.py`, `tests/test_notification_delivery.py`, and `tests/test_high_rbac_boundaries.py`. Persistent workspace SQLite remained unchanged. |
| Focused Playwright conversations | **PASS:** 3 passed | Chromium: server page navigation/counts, property-admin takeover/reply/resolve, and restaurant assignment. Temporary dependency links were removed after the run. |
| JavaScript syntax and `git diff --check` | **PASS** | `app/static/admin.js`; candidate diff. |

Commits `97369c6` and `adec402` provide pagination for the Conversations inbox only; C-30 remains **PARTIAL** until the other high-volume admin lists gain bounded pages and controls. Hosted run #259 predates these commits, so hosted validation of the pagination change is pending.

## 2026-10-16 PR #63 hosted run #260 and pagination mock correction

| Check | Result | Scope / limit |
| --- | --- | --- |
| Backend workflow suite | **PASS:** 1,349 passed, 19 skipped | Hosted CI [run #260](https://github.com/jasongil003/Concierge.Ai/actions/runs/38866073706), candidate head `46d6c1d2e3dbd6208c7aac3f80b80d2e4eb17013`. |
| Browser workflow suite | **FAIL:** 342 passed, 41 skipped, 15 failed | Twelve failures were six retention-race tests in desktop/mobile whose route mocks still matched the old URL without pagination query parameters. Three additional onboarding/network-access assertions failed only in the full hosted suite and passed in focused local reruns; full-suite interaction remains to be rechecked. |
| PostgreSQL/Redis, Docker runtime, Python/Node dependency audits, static security, Linux/macOS deployment validation | **PASS** | Hosted CI run #260. |
| PR-diff and current-worktree Gitleaks scans | **PASS:** no findings | Hosted CI run #260. |
| Forced-text full-history Gitleaks scan | **FAIL / RELEASE BLOCKER:** three known historical findings | Hosted CI run #260. Values omitted; issuer revocation and repository-owner-authorized history cleanup remain required. |
| Corrected retention-race route mock | **PASS:** 6 passed | Local Chromium against the candidate implementation after updating the mock to match the paginated inbox URL. |
| Focused onboarding and network-access browser checks | **PASS:** 3 passed, 1 skipped | Local Chromium and mobile Chrome emulation. These checks were run separately, so they do not resolve the three full-suite-only failures. |

The browser mock correction is in the next candidate update. Keep release acceptance **RED** until the refreshed hosted full suite and external release gates are resolved.

## 2026-10-16 PR #63 hosted run #261 — corrected full-suite acceptance

| Check | Result | Scope / limit |
| --- | --- | --- |
| Backend workflow suite | **PASS:** 1,349 passed, 19 skipped | Hosted CI [run #261](https://github.com/jasongil003/Concierge.Ai/actions/runs/38868604334), head `7b31f7201ceaaa235bba74d054ba706f60291554`. |
| Browser workflow suite | **PASS:** 357 passed, 41 skipped, 0 failed | Hosted CI run #261. The six retention-race scenarios now intercept the query-bearing paginated inbox URL. Physical iOS/Android and hotel Wi-Fi acceptance remain open. |
| PostgreSQL/Redis, Docker runtime, Python/Node dependency audits, static security, Linux/macOS deployment validation | **PASS** | Hosted CI run #261. These checks do not certify target-hotel installation or live integrations. |
| PR-diff and current-worktree Gitleaks scans | **PASS:** no findings | Hosted CI run #261. |
| Forced-text full-history Gitleaks scan | **FAIL / RELEASE BLOCKER:** three known historical findings | Hosted CI run #261. Values omitted; issuer revocation and repository-owner-authorized history cleanup remain required. |

Run #261 completed with **9/10 jobs passing**. The candidate was tested without merge or deployment. Release acceptance remains **RED** until the historical-secret, branch-protection, policy, live-integration and hotel-device gates are closed.
