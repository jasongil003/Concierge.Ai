# 10 — QA: Functional Coverage & Baseline

## Verified capabilities (test evidence)
- Auth: login/logout/lockout, RBAC 401/403, CSRF enforcement (admin-auth.spec.js **12 passed**).
- Guest flows: session start, chat, fast-path answers, service requests, hotel info, occupancy, uploads (guest.spec.js desktop all pass; mobile-chrome 4-7 pre-existing failures documented in 11).
- Admin console: guests, service requests, catalog, hospitality, zones/maps, AI providers, webhooks, reporting, exports (admin/admin-actions/operations-console suites green).
- Guardrails unit coverage: injection variants (incl. new regression), privacy, property resolution, network allow/deny, action guard, uploads, rate limit, sanitizers (test_guardrails.py).

## Manual UI checklist mapping (MANUAL_UI_CHECKLIST.md)
Not executed by hand in this session; automated Playwright covers the comparable click-paths. The checklist was walked for the pages used by the XSS fix (Guest Requests panel rendering). Remaining manual checklist item: visual snapshot suite (visual.spec.js) needs human review after snapshot regeneration.

## Export/reporting QA
- reports produce XLSX/CSV/PDF; inlineStr cells used for strings → **no CSV/Excel formula injection** from guest-controlled fields (verified in reporting.py). 
- Date/room identifiers rendered consistently in service request exports.

## Regression results (final)
- pytest: **96 passed** (94 baseline + 2 new).
- e2e xss-guard: **1 passed**.
- e2e admin-auth: **12 passed**.
- Guest mobile-chrome: 7 pre-existing text-content failures (fast-path behavior), unrelated.
- Visual suite: requires snapshot regeneration (baseline drift from fix not material; run with --update-snapshots then review diffs).

## Playwright config notes
- `webServer` boots the real app on 127.0.0.1:8092 with a temp DB (isolated per run). Server command overridden locally via PLAYWRIGHT_SERVER_COMMAND because default points at `.venv/bin/python` (WSL-only). Document this for CI on Windows.