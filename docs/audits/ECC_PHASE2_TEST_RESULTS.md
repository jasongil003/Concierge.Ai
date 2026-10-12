# ECC Phase 2 test and scan evidence

## Environment

- Branch: `fix/intelligent-ui-v2-phase2-completion`; starting and final local commit remain `6bf63f642a5fa6bd77db371860ed8d9989e29b2a` because no commit was created.
- Python used: repository `.venv` Python 3.11.16. Python 3.12 is unavailable locally.
- Playwright uses an isolated temporary SQLite database and uploads directory; persistent `state/concierge.db` remained unchanged at SHA-256 `a682599b6e28da3051909d14d0018bf8825e80d663607ae579af35347f980e78`.
- Localhost Playwright initially could not bind inside the sandbox. The isolated run was retried with approved loopback permission.

## Commands and results

Final local results:

| Command | Result |
| --- | --- |
| `.venv/bin/pytest -q tests/test_security_remediation.py::test_active_guest_activity_slides_expiry_and_refreshes_cookie_age` | **1 passed**, 2 deprecation warnings, 0.44s. Persistent SQLite hash unchanged. |
| `.venv/bin/pytest -q` | **1087 passed, 17 skipped**, 2 deprecation warnings, 41.04s. Persistent SQLite hash unchanged. |
| `npm run test:e2e -- --reporter=list` | **273 passed, 35 skipped**, no failures, 5.2 minutes; full 308-test matrix across desktop Chromium and emulated mobile Chrome. |
| `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium` | **Passed (exit 0)** at the exact CI threshold. Bandit emitted `# nosec` validation and comment-parser warnings; no finding met the configured severity and confidence threshold. |
| `.venv/bin/python -m compileall -q app tests/test_ai_providers.py tests/test_intelligent_ui.py tests/test_ai_quality_benchmark.py` | **Passed.** |
| `node --check app/guest_v2/app.js && node --check tests/e2e/guest.spec.js` | **Passed.** |
| `git diff --check` | **Passed** after restoring the generated control inventory artifact. |

Focused verification: 204 backend tests passed across Intelligent UI, AI provider, security-remediation, and 100-case benchmark files; the 100-case benchmark alone reports 101 passed; facility/map schema and property-map tests pass. The targeted breakfast browser regression passed in both projects. Targeted floor-map browser regression passed in both projects. A prior full browser run had one legacy Details-button assertion mismatch; the selector was corrected to follow the button's updated accessible name, and the targeted test passed in both projects. The final full browser rerun passed with 273 passed and 35 skipped.

## Unavailable checks and warnings

Python 3.12, PostgreSQL/Redis test services, Docker/Trivy, Gitleaks, desktop Safari, physical iOS/Android devices, a captive-portal gateway, external provider credentials, and target appliance/TLS/proxy/backup infrastructure are unavailable in this environment. `npm audit` could not reach `registry.npmjs.org` because network DNS is blocked; `pip-audit`, Trivy, and Gitleaks are not installed. These checks remain blocked/unverified. The full pytest suite emits two upstream deprecation warnings from Starlette/httpx/AnyIO. The configured CI Bandit command passes; its threshold filters out lower-confidence findings.
