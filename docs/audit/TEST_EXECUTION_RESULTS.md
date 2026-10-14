# Test execution results

**Audit target:** `d5d006e89c38c0d901256d545679fee753175ef8`  
**Environment:** Darwin arm64, Python 3.11.16, Node v26.7.0; date 2026-10-14 Asia/Manila.  
**Database safety:** Python tests use isolated fixtures; the persistent SQLite safety check reported unchanged before/after hashes and no journal/WAL sidecars.

| Command | Result | Notes |
|---|---|---|
| `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/test_local_demo_isolation.py tests/test_security_remediation.py tests/test_source_install.py` | **92 passed, 1 skipped** in 4.65s | Two deprecation warnings from Starlette/httpx/AnyIO. The skipped test is platform-specific. |
| `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -rs` | **1,180 passed, 18 skipped, 0 failed** in 46.14s | Two deprecation warnings. Skip reasons below. |
| `npm run test:e2e` | **323 passed, 38 skipped, 9 failed** in 6.3m | Every failure was the same browser console 404 for `/explore` while the SPA changed paths. Responsive/layout assertions passed. The fix was an explicit SVG favicon; see post-fix run. The whole suite was not rerun after the fix. |
| `npm run test:e2e -- --project=chromium tests/e2e/manual-qa-responsive.spec.js` | **9 passed, 0 failed** in 51.7s | Reran all nine unchanged viewport tests (1920, 1440, 1280, 1024, 768, 430, 390, 375, 320 px) after adding the favicon. |
| `npm audit --offline --json` | **0 advisories** | Lockfile audit from local cache; 3 dependency entries. No online registry check is claimed. |
| `.venv/bin/bandit -q -r app -ll` | **0 High, 2 Medium B608 alerts** | Both are SQL construction alerts at `app/properties.py:595,771`; source review confirms fixed `COLUMNS` identifiers and bound values. Other Bandit comment/parser warnings remain. |
| `.venv/bin/pip-audit -r requirements.txt` | **BLOCKED** | The audit tool could not upgrade its temporary pip/wheel/setuptools tooling because package-network access was unavailable. No Python dependency-clean claim is made. |
| `git ls-remote origin refs/heads/main` | **BLOCKED** | DNS lookup for `github.com` failed. Local cached refs point to the audited SHA, but remote freshness was not confirmed. |

## Skipped backend tests

- `tests/test_ai_provider_distributed_bulkhead.py` — `REDIS_TEST_URL` required.
- `tests/test_knowledge_management.py` — Linux `RLIMIT_AS` acceptance is platform-specific.
- `tests/test_postgres_backup_integration.py` — requires `DATABASE_URL` and `PG_DUMP_AVAILABLE`.
- `tests/test_postgres_integration.py` — 12 cases require `DATABASE_URL`.
- `tests/test_postgres_sqlite_migration.py` — requires `DATABASE_URL`.
- `tests/test_redis_rate_limiter.py` — requires `REDIS_TEST_URL`.
- `tests/test_source_install.py` — `systemd-analyze` is not installed on this host.

## Browser skips and limits

Playwright uses one worker and two projects (Chromium and Pixel 7 emulation). The 38 skips are project-specific responsive/control matrix cases intentionally run once in Chromium, desktop-only flows in the mobile project, and tests explicitly marked for one project. The Chromium responsive matrix was rerun and passed after remediation. No physical device, screen reader, live provider, hotel gateway, PostgreSQL/Redis service, production proxy, or 30,000-user load environment was exercised.
