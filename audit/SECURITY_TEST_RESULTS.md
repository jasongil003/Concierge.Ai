# Security Test Results

Run date: 2026-09-28. Tests were run only against the local repository and local app. No production credentials, external targets, or paid AI calls were used.

## Automated checks

| Check | Result |
|---|---|
| Python test suite | **667 passed, 8 skipped**. The skipped tests require PostgreSQL/Redis services unavailable in this local environment. Two Starlette/httpx and AnyIO deprecation warnings remain. |
| Playwright | **216 passed, 18 skipped, 0 failed** across desktop and mobile Chromium. The skipped cases follow existing Playwright test/project annotations. The guest-home baselines were refreshed only after inspecting the current intentional dashboard and isolating each visual test with a fresh property ID. |
| Bandit | The CI-equivalent command exits **0** with no unsuppressed Medium-or-higher findings. B608 detections are narrowly suppressed beside reviewed fixed fragments, generated placeholders, and fixed schema identifiers, each with an explanation. SQL injection regression tests pass. |
| pip-audit | **Not verified.** `pip-audit -r requirements-dev.txt` could not create its temporary environment because package installation/upgrade network access is unavailable. |
| npm audit | **Not verified.** The npm advisory request failed DNS resolution for `registry.npmjs.org`. |
| Secret scanning | Gitleaks is configured in CI, but no local history scan was available. No production `.env` was read. |
| Docker build/runtime | **Not verified locally.** Docker cannot connect to the daemon socket, so image build, container persistence, and non-root runtime checks were not run. |
| Trivy | **Not verified locally.** The Docker image could not be built/scanned; CI uses `aquasecurity/trivy-action@v0.36.0`. |

## Authorization and tenancy probes

- Direct API test `tests/test_rbac_policy_inventory.py::test_every_system_role_is_enforced_by_direct_api_requests` signs in as every built-in role, checks permission-gated API access, and attempts a cross-property path for each non-global role.
- Route inventory tests assert exact admin API policy coverage, reject anonymous requests on authenticated routes, and reject authenticated users without the route permission.
- Property isolation tests cover cross-property administrator reads, guest session property selection, guest stay context, knowledge search, and operational records.
- Guest session tests now prove that session ID alone and legacy uncredentialed rows are rejected; valid original credentials work; cross-property replay is denied; expiry and revocation are enforced; resume rotates credentials; and raw tokens do not appear in logs.

## Attack cases exercised locally

- **SQL injection:** SQL regression tests submit common quote, boolean, and union-style input strings to property and search flows. Reviewed query parameters are bound.
- **XSS:** Playwright XSS guard tests submit stored and reflected hostile text. Floor-map upload tests reject active SVG content and external resource references.
- **CSRF and origin:** Admin state-changing requests without CSRF are rejected; cross-origin guest mutations are denied.
- **IDOR and tenant switching:** Role tests, property path probes, and guest session property-selection tests reject cross-property access.
- **SSRF:** URL tests cover loopback, RFC1918, link-local metadata, IPv6 loopback, redirects, and private DNS answers. Deployment TLS verification is unit-tested with a private DNS result and an assertion that no socket is opened.
- **Path traversal and filenames:** Knowledge upload tests cover traversal names, file extension/content mismatch, and normalization to safe names.
- **Malicious files:** Tests cover fake MIME/magic, active SVG, SVG external URLs, oversized images, CSV formulas, malformed Office ZIPs, macros/embedded active content, and expanded/compressed Office archive limits. PDF page count and file-size checks are present; high-expansion PDF behavior was not stress-tested.
- **AI direct/indirect injection:** Local tests block representative guest prompt injection before a provider call; knowledge tests flag injected instructions and prevent flagged/sensitive items from guest retrieval. Admin and guest prompt builders mark retrieved files, logs, history, and tool output as untrusted; server-side tool authorization is separately tested. No external or paid model was called, so this is not a live model red-team result.
- **ANTlabs replay:** Tests validate signature, timestamp, source network, property binding, and one-time nonce consumption. No live SG5 gateway was available to verify its exact assertion format or device/session binding.

## Scanner triage

Bandit B608 detections arise where SQL is assembled from internally generated `?` placeholders, fixed query fragments, or constant schema identifiers. Runtime values are passed separately as query parameters. No arbitrary user value was found in SQL syntax during manual review. The scanner command passes with narrow, adjacent suppressions and rationale comments, and the SQL injection regression tests pass.

Current Python and npm dependency advisory status is unknown because both online audits were blocked by network access. Dependency advisories also do not establish the safety of the mutable `python:3.12-slim` and `nginx:1.29-alpine` image tags. The CI workflow contains dependency and image scan jobs; their remote results must be checked before merge.
