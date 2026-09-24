# 07 — Security: XSS (Stored, Reflected, DOM)

## Method
Systematic audit of every client-side sink:
- `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `new Function`, string-timeout/setInterval, dynamic script insertion → **none present**.
- `innerHTML` write points: admin.js ×94, app.js ×7. Diffs read for unescaped data-bound values, list= the real sinks at each line.

## Fixed critical (SEC-001) — STORED XSS via guest service requests into admin console

Chain: guest → `POST /api/guest/service-requests` (description/room stored verbatim) → admin `GET .../hospitality` returns `service_requests` → admin.js printed each row field into `innerHTML` unescaped (lines ~2417-2421).

- Proof: stored `<img onerror>` + `<script>` tags; API returned raw; admin.js built DOM via `innerHTML`.
- Fix: every field that may carry guest text is now HTML-escaped through the existing `escapeHTML()` serializer before insertion into the row template (admin.js edit). `escapeHTML(` count in admin.js went from 61 → 68.
- Regression tests:
  - `tests/test_guardrails.py::test_service_request_preserves_guest_text_for_output_encoding_contract` (documents server keeps raw text; defense is client-side encoding — intentionally no sanitization to avoid data loss).
  - `tests/e2e/xss-guard.spec.js` — full browser: guest posts XSS payload with `confirmed:true`; admin renders Guest Requests; asserts payload text visible, `window.__xss_proof` undefined, no script/img[onerror] nodes executed. **PASS.**

## Sinks reviewed and dispositions

| Location (admin.js) | Field | Disposition |
|---|---|---|
| ~2417-2421 | request_type / room / status / sla_state / department / priority / description | **ESCAPED (SEC-001)** |
| ~966-967 | provider.name, provider.auth_method | ESCAPED (defense-in-depth; name can be admin-edited) |
| ~972 | statusLabel | ESCAPED |
| ~1831 | zone.name/category | ESCAPED |
| ~2069 | busiest_zone_id | ESCAPED |
| ~2095-2096 | area_metrics zone keys, movement source/dest | ESCAPED |
| ~808 | ai stats (numeric only) | left verbatim (numbers) |
| app.js chat answers | AI output rendered via text node / validated by AIOutputValidator | Safe pattern; no innerHTML for untrusted text |

## Not fixed (documented LOW)
- `admin-login.js` reads `reset_token` from URL `searchParams` and uses it in input value (safe: set via property/input value, not innerHTML).
- No guest-side `Origin` enforcement (see 05/SEC-012).
- AI provider display fields are admin-edited; escaping added anyway.

## Verdict
Stored XSS in admin console: **FIXED and verified by both unit contract test and end-to-end browser proof.** No other unescaped untrusted-data sink found. Remaining risk: future edits reintroducing innerHTML with unsanitized values — guard with a linter rule / PairWithEscape helper.