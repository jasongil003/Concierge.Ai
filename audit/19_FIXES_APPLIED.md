# 19 — Fixes Applied (audit session)

## SEC-001 — Stored XSS in admin Guest Requests (CRITICAL)
File: `app/static/admin.js`
Change: service-request row template now escapes all guest-controlled fields via existing `escapeHTML()`: request_type, room, status, sla_state, department, priority, description (lines ~2417-2421). Defense-in-depth escaping also added for provider name/auth_method (966-967), status label (972), zone name/category (1831), busiest_zone_id (2069), area-metrics zone keys + movement source/destination (2095-2096). `escapeHTML(` call count 61 → 68.
Verification: new e2e `tests/e2e/xss-guard.spec.js` PASS; unit contract test added; admin-auth suite 12/12 green.

## SEC-003 — Prompt-injection classifier bypass (MEDIUM)
File: `app/guardrails.py` (INJECTION_PATTERNS[0])
Old: `ignore (?:all |the )?(?:previous|prior|system) instructions`
New: `ignore (?:all |any |the )?(?:previous|prior|system|earlier)[^\n]{0,24}instructions`
Verification: `audit_proof.py` now returns prompt_injection for "ignore all previous system instructions"; `test_canonical_injection_variants_are_classified` (4 variants) added; full pytest 96/96.

## SEC-009 — Docker root + no healthcheck (MEDIUM)
File: `Dockerfile` (rewritten)
- non-root `concierge` service account; `USER concierge`; owned /state & /app.
- HEALTHCHECK via urllib on /health (30s/5s/15s/3).
- PYTHONDONTWRITEBYTECODE/PYTHONUNBUFFERED env kept.
Note: image not rebuilt in this environment (Docker daemon access not assumed); config-only change, unit/Dockerfile reviewed. CI build step recommended before release.

## Regression test additions
- `tests/test_guardrails.py::test_canonical_injection_variants_are_classified`
- `tests/test_guardrails.py::test_service_request_preserves_guest_text_for_output_encoding_contract`
- `tests/e2e/xss-guard.spec.js` (browser-level stored-XSS guard)