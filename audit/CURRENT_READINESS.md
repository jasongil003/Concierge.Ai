# Current product readiness

**Review date:** 2026-09-28  
**Reviewed checkout:** `audit/production-readiness-final`  
**Scope:** Current working tree, including the guest-session, SQL/Bandit, CI, browser, and load-test changes in this review. This is not evidence that the remote `main` branch or its GitHub Actions runs have passed.

## Result

**Development ready: Yes. Pilot ready: No. Production ready: No.**

The application suite, Bandit, and desktop/mobile browser suite pass locally. Eight backend tests that require PostgreSQL and Redis are skipped without those services. Dependency advisories, Docker runtime, and Trivy are not verified in this environment. No real hotel network, TLS proxy, or ANTlabs SG5 was available.

See [controlled load-test stages](../docs/LOAD_TESTING.md) for the runner and [release controls](../docs/RELEASE_CONTROLS.md) for the required merge checks.

## Issues fixed

| Issue and cause | Fix |
| --- | --- |
| Guest session IDs acted as bearer credentials; guest routes checked the session record but not a browser-held secret. | Every guest API now requires a random server-issued token and separate browser-context cookie. The store keeps only SHA-256 hashes; cookies are HttpOnly, SameSite strict, Secure in production/staging, and expire with the session. Resume rotates credentials. Legacy sessions without credentials fail closed in all environments. Revocation and verified gateway-session storage hooks are present. |
| Guest session IDs were included in several GET URLs. | Guest home, requests, and personalization APIs resolve the session from cookies; the frontend no longer puts session IDs in those query strings. Other guest routes also validate the cookies. |
| Bandit B608 detections covered generated placeholders, fixed fragments, and schema identifiers. | Reviewed each detected query, retained bound runtime values, and used narrow suppressions with adjacent rationale only where Bandit cannot recognize the fixed SQL structure. The CI-equivalent scan exits successfully. |
| Integration CI did not supply the required bootstrap/encryption values to Alembic. | The PostgreSQL/Redis job creates random per-run values through `GITHUB_ENV`; production startup policy remains unchanged. |
| The Trivy action reference was not resolvable. | CI uses the supported `aquasecurity/trivy-action@v0.36.0` release against the built image, failing on fixable High/Critical findings. |
| Docker runtime checks did not assert application-user file permissions or exercise production configuration loading. | CI validates production settings in the image, runs the container as non-root, checks `/state` access and application-source write denial as the app UID, and writes/restarts/verifies persisted state. These remote checks have not run from this checkout. |
| Guest-home screenshots mixed in property-scoped records left behind after a profile was deleted, and the committed screenshots described the earlier chat-first home. | Each visual test now uses a fresh property ID and waits for `/api/guest/home`. The current stay dashboard was inspected, and only the desktop/mobile guest-home baselines were updated. |
| Staged capacity profiles did not match the requested 10–1,000-user range or collect all requested metrics. | Added six controlled stages and a confirmation-gated runner that records Locust latency/throughput/success, API-process CPU/RSS, HTTP/database errors, AI queue wait, and rate-limit events. No staged capacity run was performed. |

## Local verification

| Check | Result |
| --- | --- |
| Backend | 667 passed, 8 skipped, 2 dependency deprecation warnings. PostgreSQL/Redis-dependent tests are among the skipped cases. |
| Browser | 216 passed, 18 skipped, 0 failed across desktop and mobile Chromium. The browser workflow uses macOS to match the committed Darwin visual baselines. |
| Bandit | CI-equivalent command exits 0; B608 suppressions are scoped and explained. |
| SQL regression | Included in the passing backend suite. |
| Python compile, JSON profile validation, `git diff --check` | Passed. Workflow YAML parses with Ruby's YAML parser. |
| Python/npm dependency audit | Not verified: package/advisory network access is unavailable. |
| Docker build/runtime and Trivy | Not verified: Docker cannot connect to the local daemon socket. |
| PostgreSQL and Redis integration | CI steps are defined, but services are not available locally and no remote CI result was obtained. |
| Staged load test | Prepared, not run. No throughput or capacity claim is made. |

## Remaining risks and external evidence

- Validate actual SG5 gateway assertions, endpoint behavior, and any trustworthy session identifier on a hotel gateway. Concierge does not grant Internet access and does not infer ANTlabs network authentication from the browser handoff.
- Verify real TLS termination, canonical hostnames, guest/admin CIDRs, trusted proxy header replacement, walled-garden access, backup restore, and retention/checkout integrations at the hotel.
- Run PostgreSQL migration/idempotency, SQLite-to-PostgreSQL, Redis limiter, backup/restore, and distributed bulkhead tests against the CI services and retain the passing logs.
- Run current Python/npm advisory scans, Gitleaks, Docker build/runtime, and Trivy on a connected runner. Confirm all required Actions checks pass before merge.
- Validate PDF decompression/resource limits in an isolated worker.
- Run the staged Locust profile against representative hardware and database/Redis setup; report collected results without extrapolating beyond the tested configuration.
- Configure GitHub branch protection for `main` outside this repository. The workflow does not configure repository settings.
- Gradual route/frontend extraction remains open: `app/main.py` is 6,432 lines and `app/static/admin.js` is 7,077 lines. Several async routes call synchronous store methods; event-loop blocking and multi-worker behavior need targeted measurement and incremental refactoring. SQLite Compose remains single-process; use PostgreSQL and Redis only after the integration gates pass.

## Readiness table

| Area | Before | After | Status |
| --- | --- | --- | --- |
| Guest session security | Session ID alone could replay on the property network. | Hashed expiring token plus browser-context cookie; rotation, revocation, no legacy bypass. | Fixed and locally tested |
| Admin authentication | Existing authenticated, CSRF-protected admin sessions. | Existing controls preserved; full backend and browser suites pass. | Verified in local suites |
| RBAC | Existing role and property checks. | Preserved; full API/browser suites pass. | Verified in local suites |
| Admin AI | Existing server-side allowlist and confirmation workflow. | Preserved; backend/browser coverage passes. | Verified in local suites |
| Restaurant RBAC | Existing restaurant-scoped access rules. | Preserved and exercised with guest browser credentials. | Verified in local suites |
| SQL security | B608 scan findings required review. | Bound values retained; narrow explained suppressions. | Bandit passes |
| PostgreSQL | Required CI values were missing; local services unavailable. | CI creates test-only secrets and runs migration/integration steps. | CI configured, remote run unverified |
| Redis | Integration requires a service. | CI configures Redis and runs limiter/bulkhead tests. | CI configured, remote run unverified |
| Docker | Trivy ref and smoke coverage incomplete. | Production validation, runtime checks, persistence, and scan steps defined. | CI configured, local Docker unavailable |
| CI | Integration migration could fail at startup; Trivy action ref invalid. | Required jobs and corrected configuration are in the workflow. | Configuration fixed; Actions results unknown |
| Browser QA | Guest-home screenshot failures from stale records and outdated baseline. | Fresh per-test property, readiness wait, inspected dashboard baselines; full suite green. | Passed locally |
| ANTlabs | Browser handoff scaffold; no live gateway proof. | Signed assertion checks preserved; verified-session storage hook added. | Deployment validation required |
| Load testing | Profiles did not match requested stages and omitted several metrics. | Stages and collectors prepared for 10/50/100/250/500/1,000 users. | Prepared; not run |
| Production readiness | Infrastructure and security gates lacked evidence. | Local development gates pass; release/documentation controls improved. | Not production ready |
