# Test execution results

**Starting HEAD:** `e4bbd7493fe9d90a513d8224749b54c9e25ddc90`
**Implementation and tested commit:** `a30f95eb8db2ff05151c3473e453f9f38d0dec2d`
**Earlier audit code baseline:** `d5d006e89c38c0d901256d545679fee753175ef8`
**Environment:** Darwin arm64, Python 3.11.16, Node v26.7.0; 2026-10-14 Asia/Manila.
**Database safety:** Backend tests used isolated fixtures; the persistent SQLite safety check reported unchanged before/after hashes and no journal/WAL sidecars. Playwright used an isolated temporary database.

| Command | Result | Notes |
|---|---|---|
| `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -rs` | **1,182 passed, 18 skipped, 0 failed** in 45.72s | Two deprecation warnings. Includes concurrency and duplicate-confirmation idempotency regressions plus the deterministic four-turn restaurant follow-up. |
| `npm run test:e2e` | **334 passed, 38 skipped, 0 failed** in 6.2m | Full Playwright run: 372 tests across Chromium and Pixel 7 emulation. The nine declared viewport sizes pass in Chromium; their mobile-project copies are intentionally skipped. |
| `npm audit --offline --json` | **0 advisories** | Lockfile audit from local cache; 3 dependency entries. No online registry check is claimed. |
| `.venv/bin/bandit -q -r app -ll` | **0 High, 2 Medium B608 alerts** | Both are SQL construction alerts in `app/properties.py`; review confirms fixed column identifiers and bound values. Additional Bandit comment/parser warnings remain. |
| `.venv/bin/pip-audit -r requirements.txt` | **BLOCKED** | The audit tool could not upgrade its temporary pip/wheel/setuptools tooling because package-network access was unavailable. No Python dependency-clean claim is made. |
| `git ls-remote origin refs/heads/main` | **BLOCKED** | DNS lookup for `github.com` failed. Cached local refs were not refreshed; current remote state is unconfirmed. |

## Skipped backend tests

- `tests/test_ai_provider_distributed_bulkhead.py` — `REDIS_TEST_URL` required.
- `tests/test_knowledge_management.py` — Linux `RLIMIT_AS` acceptance is platform-specific.
- `tests/test_postgres_backup_integration.py` — requires `DATABASE_URL` and `PG_DUMP_AVAILABLE`.
- `tests/test_postgres_integration.py` — 12 cases require `DATABASE_URL`.
- `tests/test_postgres_sqlite_migration.py` — requires `DATABASE_URL`.
- `tests/test_redis_rate_limiter.py` — requires `REDIS_TEST_URL`.
- `tests/test_source_install.py` — `systemd-analyze` is not installed on this host.

## Browser skips and limits

The 38 Playwright skips are project-specific responsive/control-matrix cases intentionally run once in Chromium, desktop-only flows in the mobile project, and tests explicitly marked for one project. The complete run passed with zero failures after the test fixture cleanup. No physical device, screen reader, live provider, hotel gateway, PostgreSQL/Redis service, production proxy, or 30,000-user load environment was exercised.

## Responsive-matrix failure investigation

The earlier full run had nine failures whose console text was prefixed with the current SPA URL `/explore`. That URL was initially misread as the failed resource. A response-level diagnostic showed the actual 404 was a synthetic `/api/guest/hotel-assets/…` image left in the shared E2E database by the indoor-map test after its test-local image mock ended. The test now deletes its three demo facility profiles in teardown, and the responsive matrix explicitly checks for HTTP 404 responses as well as console errors. The follow-up full run passed all 334 executed browser tests.
