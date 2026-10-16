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
| `.venv/bin/python scripts/m