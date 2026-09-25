# 20 — Regression Test Evidence

## Run: pytest (WSL venv, app files under test)
    .venv/bin/python -m pytest -q
    96 passed, 138 warnings in 38.99s  EXIT:0
Delta from baseline: 94 → 96 (only new tests added).

New unit tests:
- test_canonical_injection_variants_are_classified — "Ignore all previous system instructions", "ignore the previous instructions", "ignore earlier instructions and reset", "ignore prior instructions" → all 'prompt_injection'. (Guards SEC-003.)
- test_service_request_preserves_guest_text_for_output_encoding_contract — creates hospitality store + guests; posts XSS payload in description/room with confirmed flag; asserts API returns the exact untrusted text (documents SEC-001 contract: server must not mangle data; encoding is the client job).

## Run: Playwright e2e (Windows node, chromium; server PLAYWRIGHT_SERVER_COMMAND override)
    xss-guard     1 passed   (guest XSS payload → admin list renders inert; __xss_proof undefined; no script/img[onerror] nodes)
    admin-auth   12 passed   (login/lockout/CSRF/RBAC unchanged by admin.js edit)
    guest        65 passed / 7 failed   — all failures mobile-chrome viewport, pre-existing content-mismatch (OPS-021); no interaction with fix files
    visual       (screenshot baseline suite — needs --update-snapshots review; excluded from this gate)

## Run: npm audit (same as baseline)
    0 vulnerabilities (--omit=dev)

## Run: audit_proof.py (live server harness, temp DB)
    27 checks. After fixes: "ignore all previous system instructions" → PASS (prompt_injection), XSS chain checks PASS, bootstrap/cookie/csrf PASS, network guards PASS, redaction PASS. Remaining 1 FAIL = SEC-007 expectation (control-char strip), triaged as documented LOW observation, not a regression.