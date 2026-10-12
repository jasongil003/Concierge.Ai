# Concierge.AI ECC Audit — Test and Tool Evidence

> Historical pre-Phase 2 evidence snapshot. Current commands and outcomes are in [ECC_PHASE2_TEST_RESULTS.md](ECC_PHASE2_TEST_RESULTS.md).

## Execution environment

- Repository: `/Users/jasongil/Desktop/My AI workforce/projects/Concierge.Ai`
- HEAD: `fbf9d50635c427f5340098cac48e7bb8eb7ef7a2`; branch `feature/intelligent-guest-ui-v2`.
- Python used: `.venv/bin/python`, **3.11.16**. Python 3.12 was not available locally. CI workflow specifies Python 3.12.
- Browser tests used a temporary working directory under `/private/tmp/concierge-ecc-audit.msFmfV`, a temporary Playwright SQLite database, and loopback server. Generated report/test artifacts were kept there, not in the repository.
- Backend tests use disposable pytest resources. Persistent `/state` SQLite database was fingerprinted before/after; size remained `8544256` bytes and SHA-256 remained `a682599b6e28da3051909d14d0018bf8825e80d663607ae579af35347f980e78`.

## Executed checks

| Check | Result | Notes |
| --- | --- | --- |
| Target guest expiry test | **1 passed, 2 warnings** | `tests/test_security_remediation.py::test_active_guest_activity_slides_expiry_and_refreshes_cookie_age`; deterministic clock verifies DB expiry and cookie `Max-Age`, then repeats activity. |
| Full backend suite | **961 passed, 17 skipped, 2 warnings** | `.venv/bin/python -m pytest -q tests`; 37.92s. All tests passed. |
| Playwright non-visual suite | **265 passed, 35 skipped, 0 failed** | 300 tests; CI-equivalent `playwright test --grep-invert @visual`; Chromium and mobile-Chrome. Loopback server and output directory isolated under `/private/tmp`. Completed in 5.4 minutes. |
| Bandit | **Passed** | CI command `bandit -q -r app -x app/static --severity-level medium --confidence-level medium`, exit 0. Existing B608 `nosec` parser notices were emitted; no failing medium+ finding. |
| Python syntax | **Passed** | In-memory `compile()` on 45 Python files; no bytecode artifacts. |
| JavaScript syntax | **Passed** | `node --check app/guest_v2/app.js` and `node --check app/static/admin.js`. |
| Shell syntax | **Passed** | `bash -n` on local demo and deployment scripts. |
| Workflow YAML | **Passed** | Ruby YAML parse for `ci.yml`, `release.yml`, `macos-native-validation.yml`. |
| npm dependency audit | **Passed** | `npm audit --audit-level=high`; 0 vulnerabilities. |
| Python dependency audit | **Passed** | `pip_audit -r requirements-dev.txt`; no known vulnerabilities. |
| Git whitespace | **Passed before report creation** | `git diff --check`; rerun after audit reports are created. |

## Playwright harness note

The first attempt placed browser execution in a temporary working directory but did not create the test’s expected `audit/` output folder. `manual-qa-control-inventory.spec.js` writes `audit/CONTROL_INVENTORY_2026-09-29.json` relative to the current directory, so that first run had one harness-output-path failure. The suite was rerun after creating the directory in the temporary location; all 300 test cases completed with 265 passed, 35 project/device-specific skips, and no failures. The inventory test passed and generated JSON stayed outside the repository. This harness issue was not an application failure.

## Skipped and unavailable evidence

The 17 backend skips were environment-dependent: 12 PostgreSQL integration tests; one PostgreSQL/SQLite migration integration; one PostgreSQL backup integration; one Redis rate-limiter test; one Redis distributed-provider bulkhead test; and one `systemd-analyze` check unavailable on this platform. SQLite migrations and property-based/local database paths were exercised.

- **Python 3.12:** unavailable locally; only Python 3.11.16 result is independently observed.
- **Remote CI/commit freshness:** GitHub DNS lookup failed; current hosted run state and live `origin` tip could not be verified. Cached local `origin/main`, local `main`, and `origin/HEAD` point to the checked-out HEAD.
- **Gitleaks:** no local executable was available; CI’s historical action result was not queried.
- **Trivy/container image scan:** Docker CLI existed, but no Docker daemon was available. No local container scan was completed.
- **Production/POC acceptance:** no live gateway, external provider, hotel network, real TLS/proxy, appliance boot/update rollback, off-host restore, or production load test was performed.
- **Formatting/lint:** repository does not define a separate Python formatter/linter or frontend lint/build script in its declared dev scripts. Syntax checks and Bandit ran; no undeclared linter result is claimed.

## Warnings

Pytest emitted two deprecation warnings: Starlette’s `httpx` use in `starlette.testclient`, and AnyIO’s `BlockingPortal` alias. Playwright emitted a Node `NO_COLOR`/`FORCE_COLOR` environment warning. These did not fail the test run.
