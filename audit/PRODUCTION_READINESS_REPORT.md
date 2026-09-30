# Concierge.AI v1.0-RC1 — Production Readiness Report

**Review date:** 2026-09-30  
**Reviewed revision:** `5e1f654` plus the uncommitted changes listed below  
**Review type:** repository audit and local automated verification; not a hotel deployment certification

## Executive Summary

The repository has a substantial production-hardening baseline: property-aware routing and storage, backend-enforced role permissions, admin and guest session controls, provider abstraction, validated configuration, operational reporting, health checks, backup/restore code, deployment guidance, and broad backend and browser coverage. The guest home presents stay, explore, requests, and concierge capabilities rather than opening directly into chat.

This review found no new Critical or High application-code issue in the areas exercised by the local test suites and static scan. That is not equivalent to production certification: PostgreSQL and Redis integration tests were skipped, the current npm advisory request could not reach the registry, Docker was unavailable, and no real property network, TLS terminator, ANTlabs gateway, PMS, or physical phone was available.

This pass isolated PDF parsing in a resource-limited worker, added the missing 320-pixel responsive check, and created this evidence-based report. The system is **NOT READY FOR PILOT** until the external production gates and Linux/Docker validation listed below pass.

## Changes Made

- Moved PDF extraction to `app/pdf_extraction_worker.py`. On Linux it is limited to 768 MiB of address space and 20 CPU seconds; the parent enforces a 30-second wall-clock timeout. The worker also enforces upload, page, extracted-text, and output-section limits and receives a minimal environment.
- Added regression coverage proving PDF extraction stops at the configured text budget and exercised the worker with a valid PDF.
- Added a 320×720 viewport to the Playwright responsive matrix; all admin destinations and guest views passed at that size in Chromium.
- Updated the knowledge-management guide, vulnerability record, and README report link.

## Critical Findings

**Resolved:** No new Critical finding was confirmed in the local code and automated checks reviewed.

**Unresolved:** None confirmed. External systems and production network boundaries were not exercised, so this result is limited to tested repository code.

## High Findings

**Resolved:** No new High application-code finding was confirmed in the executed tests and Bandit scan. Existing controls for authentication, authorization, cross-tenant access, host validation, outbound requests, and file handling remain covered by regression tests.

**Unresolved:** The production deployment itself is not verified. Treat production exposure as blocked until its network, gateway, database, container, and credential settings have passed the release gates below.

## Medium Findings

- **Production network and gateway validation remains outstanding.** Validate HTTPS termination, canonical guest hosts, trusted proxy behavior, management CIDRs, guest VLAN separation, and the real ANTlabs SG5 assertion/authentication contract at the target property.
- **Database and distributed-service validation is incomplete.** Sixteen tests were skipped because PostgreSQL/Redis service URLs and `pg_dump` integration were not available. Do not scale the SQLite Compose profile beyond one app process.
- **The PDF memory ceiling was not exercised on Linux in this checkout.** The worker sets `RLIMIT_AS` on Linux; this macOS run verified valid parsing, error handling, and early text-budget termination, but not the Linux limit itself.
- **Current dependency advisory status is unknown.** `npm audit` failed because `registry.npmjs.org` could not be resolved. `pip-audit -r requirements-dev.txt` could not bootstrap its temporary pip environment, and `pip-audit --local` could not resolve `pypi.org` for advisory lookup. Run both from a connected CI runner.
- **Capacity and outage behavior are not certified.** Load stages are defined, but no representative hotel-hardware run was performed. Live AI-provider, PMS, and gateway failures were not exercised.

## Low Findings

- `app/main.py` (6,662 lines) and `app/static/admin.js` (7,122 lines) remain large files. Continue incremental route/UI module extraction when a focused change makes ownership clear.
- Dense semantic retrieval, guest-visible citations, a native Microsoft/Azure Foundry provider, and scanned-PDF OCR are not implemented. Copilot is explicitly unavailable in the provider catalog. These are product limitations, not hidden working features.
- Several async routes call synchronous stores. Measure event-loop latency and move expensive operations to bounded workers as part of measured capacity work.

## Security

- Admin passwords use a password hash; admin sessions are server-side, expiring, revocable, and protected by CSRF checks on writes. Login throttling and lockout have concurrent-attempt regression coverage.
- Production configuration fails closed for missing/weak bootstrap and encryption secrets, insecure cookies, unsafe debug/demo settings, broad management CIDRs, invalid canonical hosts, and invalid public origins.
- Production disables public OpenAPI/Swagger pages. Forwarded client addresses are accepted only through configured trusted proxies, and malformed proxy chains fail closed.
- Guest API calls require expiring server-issued browser credentials; session IDs alone do not authenticate. Tokens are hashed at rest, cookies are HttpOnly, and resume rotates the credentials.
- Uploaded floor maps reject active SVG and mismatched content. Office archive, image dimensions, file size, upload quota, filename, and extracted content checks are covered by existing tests. PDF resource limits were strengthened in this pass.
- Parameterized SQL, output escaping, CSRF, SSRF, path traversal, reset-link host injection, and stored-XSS paths have regression coverage. Bandit passed at the configured Medium severity/confidence thresholds.
- No current online dependency advisory result is available from this run.

## RBAC

Authorization is enforced in backend middleware and route policies, with additional checks inside sensitive tools and operations. Admin AI configuration proposals use permission checks and explicit confirmation; generated text cannot directly run system commands or grant itself permissions. Existing tests cover authentication, role ceilings, custom roles, admin route inventory, and direct API calls.

## Property Isolation

Property identifiers are resolved and checked server-side. Property-scoped store queries and ownership checks cover guest data, analytics, restaurants, configuration, knowledge, sessions, and exports. Regression suites exercise direct identifier manipulation and cross-property access. Actual production domain/DNS mappings remain an operator validation task.

## Restaurant Isolation

Restaurant managers and staff are assigned restaurant IDs and backend routes apply role, property, and assignment checks. Menu and promotion approval flows clear stale approval on edits. Existing restaurant workflow tests cover single and multiple assignments, unauthorized IDs, cross-property access, and direct API calls.

## Network Separation

The production Compose profile binds the host-facing HTTP proxy to loopback and keeps the application service on the internal Compose network. Production requires exact canonical hosts, a non-global administrator CIDR list, an HTTPS public origin, secure cookies, and explicit trusted-proxy addresses. This repository configuration does not prove the hotel VLAN, firewall, external TLS proxy, DNS, or captive-portal path is correct.

## Guest Experience

The guest home is a personal stay dashboard with separate Explore, Requests, My Stay, and Concierge views. Property content, dining, requests, privacy, accessibility, loading/error handling, and AI-unavailable fallback paths have browser coverage. The full Playwright run covered the existing desktop/mobile workflows; the responsive matrix covered 1920, 1440, 1280, 1024, 768, 430, 390, and 375 pixels, and the added 320×720 case passed separately.

Real-device behavior, captive portal handling, keyboard appearance, safe areas, actual hotel Wi-Fi, and device-specific TLS trust remain untested. See `audit/REAL_DEVICE_ACCEPTANCE.md`.

## Admin Experience

The UI has operational dashboards, role-aware navigation, restaurant workflows, configuration previews, reports, health checks, and explicit save/publish/destructive-confirmation paths. The Playwright control inventory reported 42 admin destinations, 5 guest views, 2,119 visible controls, zero enabled controls that were not focusable, and zero controls missing accessible names. The inventory is a discovery/focus check; interactive behavior is validated by named workflows rather than blind clicking every control.

Responsive destination checks found no horizontal overflow at each tested viewport. Physical tablet/laptop browser differences and full keyboard/screen-reader acceptance still need human deployment QA.

## AI Architecture

Provider-specific code is behind a provider interface. Implemented options include Gemini, Groq, OpenAI, Claude, OpenRouter, and local OpenAI-compatible services. The catalog marks GitHub Copilot unavailable; there is no native Microsoft/Azure Foundry adapter. Health checks, retries, circuit/bulkhead controls, timeouts, usage telemetry, encrypted credentials, local endpoint allowlisting, and fallback paths have deterministic tests. No live provider was called during this review.

Retrieved property content is treated as untrusted input; tool actions still pass through server authorization. Current keyword retrieval and pattern-based prompt-injection checks do not constitute semantic search, antivirus, or comprehensive DLP.

## Performance

The repository includes staged load profiles and telemetry collection for request latency, throughput, errors, CPU/RSS, database errors, AI queue wait, and rate limits. No representative hardware, full load profile, soak run, or capacity target was measured in this review. SQLite is configured for one application process; PostgreSQL/Redis scaling remains gated on their service integration jobs and target connection/load budgets.

## Resilience

Health liveness/readiness, provider circuit/bulkhead controls, rate limiting, persisted background work, error-safe UI states, and backup/restore flows have local test coverage. No live provider outage, database failover, network partition, PMS partial sync, or recovery drill was run against deployment infrastructure.

## Database

SQLite remains the documented single-node on-prem default. Additive migrations and SQLite ordering/upgrade tests passed in the backend suite. PostgreSQL adapter, Alembic migration, Redis limiter, distributed provider bulkhead, and PostgreSQL backup tests were skipped without those services. Do not enable multiple replicas until the integration workflow and deployment migration/rollback are verified.

## Monitoring

The app exposes restricted health/metrics endpoints and records request/error/latency, database, provider, and operational-alert telemetry. The admin health and operations pages have functional browser coverage. External alert delivery, hotel-specific thresholds, on-call ownership, and tested SLOs are not configured by this repository alone.

## Backup / Restore

The SQLite backup/restore suite passed locally, including database and upload restoration paths. PostgreSQL backup/restore integration was skipped because `DATABASE_URL` and `PG_DUMP_AVAILABLE` were not provided. Off-host encrypted retention and a clean-environment recovery drill must be verified by the operator.

## Tests

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q -rs` | **765 passed, 16 skipped, 0 failed**; 2 upstream deprecation warnings. Skips require PostgreSQL/Redis URLs and `pg_dump`. |
| `npm run test:e2e` | **230 passed, 32 skipped, 0 failed** on desktop Chromium and mobile Chrome. Skips are project-specific browser applicability skips. |
| `npm run test:e2e -- --grep '320x720'` | **1 passed, 1 expected skip** (320px Chromium case; mobile project is skipped by the matrix). |
| `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium` | Exit 0. Bandit printed reviewed `nosec B608` annotations for generated SQL placeholders. |
| `.venv/bin/python -m compileall -q app` | Passed. |
| `.venv/bin/python -m json.tool app/admin_route_policies.json` | Passed. |
| `git diff --check` | Passed. |
| `npm audit --audit-level=high` | **Not verified:** registry DNS lookup failed (`ENOTFOUND registry.npmjs.org`). |
| `.venv/bin/pip-audit -r requirements-dev.txt` and `.venv/bin/pip-audit --local` | **Not verified:** temporary pip bootstrap failed; local advisory lookup failed to resolve `pypi.org`. |
| Docker runtime / image scan | **Not verified:** Docker API socket denied access in this environment. CI job definitions exist but no remote CI result was obtained. |

The 16 skipped backend cases cover PostgreSQL migration/query/backup integration and Redis rate-limit/distributed-bulkhead integration. They are environment skips, not passes.

## Remaining Risks

- No green CI evidence for this checkout was obtained. CI definitions do not substitute for executed jobs.
- Real SG5 gateway behavior, signed assertion fields, device/session binding, PMS sync, property DNS, TLS, management CIDRs, and walled-garden rules need a hotel lab.
- Linux address-space enforcement in the new PDF worker must be exercised in the Linux CI/container runtime; the local host was macOS.
- Current Python and npm advisory scans, Gitleaks, Docker runtime smoke, Trivy, and SBOM generation need a connected CI runner.
- No physical iOS or Android acceptance, measured hotel hardware capacity, live AI/provider health check, or off-host restore drill was performed.
- Semantic retrieval and some broad AI provider requests remain future product work; use verified hotel data and human approval for guest-visible facts/actions.

## Production Blockers

1. Obtain green backend, PostgreSQL/Redis integration, browser, Docker runtime, secret-scan, dependency-audit, and image-scan CI results for the release revision.
2. Verify Linux PDF memory/CPU enforcement in the production image and validate container memory limits.
3. Complete a real hotel network test for TLS, DNS/hosts, admin CIDR/proxy trust, guest VLAN isolation, captive portal, and the SG5 authentication contract.
4. Run a successful restore drill from the intended encrypted off-host backup location.
5. Complete physical iPhone/Android guest-flow QA and at least one representative staged capacity run.

## Pilot Recommendations

- Keep any pilot private to a controlled hotel lab until the blockers above pass. Use disposable guest accounts and test property data.
- Start with one app instance, SQLite, and an explicitly configured local or approved provider; keep management access on a dedicated trusted network.
- Do not enable a real gateway handoff until the hotel's exact SG5 fields and successful network admission have been observed and recorded.
- Require a pre-upgrade backup, verified rollback steps, health/readiness check, and an operator contact before every pilot deployment.
- Retain redacted test evidence for every gate; do not move to guest-facing production traffic based only on local test results.

## Recommended Next Steps

1. Run all defined CI jobs on a connected Linux runner and retain artifacts.
2. Verify the release image and migrations with PostgreSQL, Redis, Docker, Trivy, and SBOM checks.
3. Exercise backup/restore and the PDF resource ceilings against production-like Linux limits.
4. Conduct the ANTlabs/PMS, TLS, proxy, and VLAN acceptance plan at the target property.
5. Run the staged load profile and physical-device checklist; set the supported concurrency envelope from those results.
6. After a controlled pilot, incrementally extract route and admin UI modules and address measured synchronous-call bottlenecks.

## Readiness State

**NOT READY FOR PILOT**

The local application tests are strong and no new Critical or High code finding was confirmed, but integration, deployment, network, recovery, and physical-device evidence is still missing. Reassess after the production blockers above have passing evidence.
