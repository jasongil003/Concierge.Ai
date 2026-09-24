# 02 — Baseline Conformance & Toolchain

Run on the active environment before any source changes (recorded for reproducibility).

## Environment

- Repo works from WSL2; `.venv` is a Linux venv at `.venv/` (Python 3.14.4) with the pinned requirements.
- Windows host: npm/node with `@playwright/test 1.55.0`; Playwright browsers cached under `%LOCALAPPDATA%\ms-playwright`, matching chromium builds.
- `.env` present (APP_ENVIRONMENT not set → resolves to `development`; PROPERTY_ID=lunara-mnl-001; DB_PATH=state/concierge.db; CREDENTIAL_ENCRYPTION_SECRET=replace-with-a-long-random-secret; AI_PROVIDER_MODE=auto; OLLAMA default host.docker.internal:11434).

## Baseline runs (pre-change)

1. `pytest -q` → **94 passed, 138 warnings, 38.9s, exit 0** (WSL venv).
2. `npm audit --omit=dev` → **0 vulnerabilities**.
3. Server smoke test (`uvicorn app.main:app`, fresh temp DB):
   - GET /health → 200 `{"status":"ok","app":"Concierge.Ai","property_id":"lunara-mnl-001","ai_provider_mode":"auto","local_model":"qwen3:8b","antlabs_mode":"mock"}`
   - GET / → 200 text/html
   - GET /admin (anon) → 303 → /admin/login
   - POST /api/admin/auth/login bootstrap admin/ChangeMe123! → 200 (verified default creds work on a fresh instance)
   - GET /api/admin/auth/me (cookie) → 200 (31 permissions, role super-admin, csrf_token)
   - GET /api/admin/permissions → 200
4. Evidence script (`audit_proof.py`, temp DB, 27 checks): 25 PASS, 2 FAIL → FAILs were (a) admin list endpoint guess (correct endpoint `/hospitality` verified later), (b) control-char sanitizer expectation (documented as LOW observation, not a regression).

## Post-change baseline delta

- `pytest -q` → **96 passed** (+2 regression tests), exit 0.
- `npx playwright test tests/e2e/xss-guard.spec.js` → **1 passed** (stored XSS regression proof).
- `tests/e2e/admin-auth.spec.js` → **12 passed**.
- `tests/e2e/guest.spec.js` → 65 passed / **7 failed on mobile-chrome only** — verified pre-existing/fast-path content mismatch on mobile (e.g., breakfast reply returns dining overview instead of "6:30 AM"); independent of audit changes (guest app + fast-path code untouched). See 11 / OPS-021.
- `tests/e2e/visual.spec.js` — screenshot baseline suite; excluded from automated regression (requires snapshot update).

## Tooling conventions used

- Backend tests: `pytest` with `TestClient`; fresh tmp DBs per fixture; `admin_client` fixture bakes bootstrap admin + CSRF.
- E2E: Playwright `webServer` boots the real app (config: baseURL 127.0.0.1:8092, DB_PATH to tmp, `reuseExistingServer`), projects chromium + mobile-chrome.
- Lint/typecheck: no project linter configured (no ruff/flake8/mypy/pyright in dev deps). Recommended to add in follow-up; not a blocker.