# 21 — QA Walk-Through Record

## Who/what
Session performed by automated agent (task-verified); manual UI checklist (MANUAL_UI_CHECKLIST.md) parameters mapped to Playwright specs.

## Walked paths
1. Guest boot → session start → chat (fast-path + freeform) → service request → upload → hotel info → occupancy:
   covered by tests/e2e/guest.spec.js (desktop green; mobile failures OPS-021).
2. Admin bootstrap login → cookie/CSRF → RBAC 401/403 on role-scarce user → property scope:
   covered by admin-auth.spec.js (12 green).
3. Admin console panels: Guests, Guest Requests (hotspot for SEC-001), Service Catalog, Hospitality, Zones & Maps, AI Providers, Webhooks, Reporting/Exports:
   covered by admin/admin-actions/operations-console specs (green on chromium).
4. Security walkthrough matrices (guardrails unit tests + proof script): network allow/deny blocklist, property resolution, action guard confirm/refuse, sanitizer, rate limiter.
5. Dockerfile → HEALTHCHECK + non-root (config review; no container run in this env).
6. Diagnostics endpoints by super-admin (check_dns/check_ssl) — functional; see SEC-011.

## Unexpected observations
- OPS-021: fast-path breakfast/pool answers flaky on mobile viewport (returns dining overview). Pre-existing; not fix-related.
- Report/formula injection: safe (inlineStr).
- Playwright on Windows needed PLAYWRIGHT_SERVER_COMMAND override (default is WSL venv path). Documented for CI (10).

## Manual-only remainder
- Visual snapshots (visual.spec.js) require human diff review after --update-snapshots.
- Lint/typecheck: none configured; add (suggested idle work).