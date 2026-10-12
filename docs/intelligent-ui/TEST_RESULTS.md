# Intelligent UI test results

## Summary

All executed Python and browser tests passed. This verifies a local prototype against the repository's isolated test data and browser setup. It does not verify a live AI provider, production infrastructure, captive portal behavior, or load capacity.

| Check | Result |
| --- | --- |
| Full Python suite: `.venv/bin/python -m pytest -q` | 961 passed, 17 skipped, 0 failed; 2 upstream deprecation warnings; 39.50 seconds |
| Full Playwright suite: `npm run test:e2e` | 269 passed, 35 skipped, 0 failed; 5.3 minutes |
| Focused Intelligent UI browser cases: `npm run test:e2e -- tests/e2e/guest.spec.js -g 'Intelligent UI'` | 6 passed across Chromium and mobile Chromium |
| Python syntax: `.venv/bin/python -m py_compile app/config.py app/intelligent_ui.py app/main.py tests/test_intelligent_ui.py` | Passed |
| Client syntax: `node --check app/guest_v2/app.js` | Passed |
| Whitespace validation: `git diff --check` | Passed |

Playwright marked viewport/project-specific cases skipped when they did not apply to the current browser project. The Python suite reported 17 skips under its existing skip conditions. No failures were hidden or disabled. The test database safeguard reported that the persistent `state/concierge.db` was unchanged.

## New coverage

- Strict property experience settings validation and allowlisted presentation block validation.
- The global flag defaults off; the property flag is also opt-in. Query parameters cannot turn the feature on.
- V2 chat requires the existing authorized guest session and delegates to the existing chat handler.
- Dining cards are assembled from guest-visible records for the active property.
- A service request goes through the existing proposal and explicit confirmation endpoints; success is rendered only after backend confirmation.
- Server-side rollback returns the legacy HTML and disables v2 API use.
- Hostile HTML in property prompts and assistant text stays inert.
- Responsive geometry was checked at 320, 375, 390, 430, 768, 1024, 1440, and 1920 pixels.
- Existing admin, authentication, legacy guest, security, and visual regression workflows ran in the full browser suite.

## Browser evidence

Real Playwright screenshots are saved in `docs/intelligent-ui/screenshots/`:

- `welcome-chromium.png`
- `conversation-chromium.png`
- `welcome-mobile-chrome.png`
- `conversation-mobile-chrome.png`

The full Playwright suite also ran the existing visual baselines and no-console-error checks. Test output may regenerate `audit/CONTROL_INVENTORY_2026-09-29.json`; that test artifact was restored to its branch version after the run.

## Not verified

- Live provider response quality, provider outage behavior, and native structured-output compatibility.
- Streaming, cancellation, retry/replay, or ordered incremental events; the adapter currently returns a whole response and does not replay a failed message automatically.
- Captive-browser behavior against real hotel gateways or production host/proxy/TLS configuration.
- A broad adversarial multi-tenant penetration test or representative concurrency/load test.
- End-to-end browser refresh recovery and shared-device behavior across real guest handoffs beyond the automated same-session checks.
- New telemetry or performance instrumentation; no guest conversation analytics were added.

See `SECURITY_ASSESSMENT.md` and `FINAL_IMPLEMENTATION_REPORT.md` for the scope and readiness assessment.
