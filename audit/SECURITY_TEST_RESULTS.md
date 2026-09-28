# Security Test Results

Run date: 2026-09-28. Tests were run only against the local repository and local app. No production credentials, external targets, or paid AI calls were used.

## Automated checks

| Check | Result |
|---|---|
| Python test suite | **653 passed, 8 skipped**. Two dependency deprecation warnings from Starlette/httpx and AnyIO. |
| Playwright | **214 passed, 18 skipped, 2 failed** in the final 212.8-second full run. Both failures are guest-home screenshot baseline differences: 2% pixel difference in desktop Chromium and 4% in mobile Chrome. No functional test failed in this final run. Three mobile workflow cases that had failed in earlier full runs pass when isolated. The visual baselines were not updated. |
| Bandit | **0 High findings.** Seven Medium B608 SQL-construction warnings remain in generated placeholder counts, constant SQL fragments, and fixed schema-column construction; manual review found bound parameters and no user-controlled SQL fragments. Twenty Low findings are informational. The seven locations are `app/hospitality.py:1069`, `app/hospitality.py:1077`, `app/observability.py:311`, `app/observability.py:316`, `app/properties.py:515`, `app/session_store.py:503`, and `app/zones.py:341`. No SQL injection was confirmed. |
| pip-audit | **No known vulnerabilities found** in `requirements.txt`. |
| npm audit | **0 vulnerabilities found.** |
| Secret scanning | Gitleaks is not installed. A local candidate-pattern scan of 100 source/config files found 0 candidate matches; tests and local environment files were excluded. It does not scan repository history and is not equivalent to Gitleaks. No production `.env` file was present or read. |
| Docker build/runtime | Docker CLI is installed, but the Docker daemon is unavailable. Both Compose files pass `docker compose config -q` with temporary synthetic values. Image build and runtime checks could not run. |
| Trivy / Grype | Neither executable is installed; image scanning could not run. |

## Authorization and tenancy probes

- Direct API test `tests/test_rbac_policy_inventory.py::test_every_system_role_is_enforced_by_direct_api_requests` signs in as every built-in role, checks permission-gated API access, and attempts a cross-property path for each non-global role.
- Route inventory tests assert exact admin API policy coverage, reject anonymous requests on authenticated routes, and reject authenticated users without the route permission.
- Property isolation tests cover cross-property administrator reads, guest session property selection, guest stay context, knowledge search, and operational records.
- A direct guest session replay test is intentionally retained as a proof of the confirmed GUEST-SESSION-01 finding.

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

Bandit’s remaining B608 findings arise where SQL is assembled from internally generated `?` placeholders, fixed query fragments, or a constant column list. Runtime values are passed separately as query parameters. No arbitrary user value was found in SQL syntax during manual review, and the SQL injection regression tests pass. The warnings are recorded rather than suppressed so future query changes remain visible.

Dependency advisories cover installed Python and npm package manifests only. They do not establish the safety of the mutable `python:3.12-slim` and `nginx:1.29-alpine` image tags. A future image scan is required after Docker is available.
