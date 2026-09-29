# Security Test Results

Run date: 2026-09-29. Scope: checked-out revision `0c4c98e` plus the uncommitted audit fixes in this worktree. Tests used local disposable databases/services and one-run credentials only. No production credentials, external targets, or paid AI calls were used.

## Automated checks

| Check | Result |
|---|---|
| Python/backend suite (SQLite default) | **709 passed, 15 skipped, 0 failed.** Skips are the PostgreSQL/Redis service cases and PostgreSQL backup drill when its `pg_dump` prerequisite is absent. Two Starlette/httpx and AnyIO deprecation warnings remain. |
| PostgreSQL + Redis integration matrix | **16 passed, 0 failed.** Covered PostgreSQL adapter and migration behavior, SQLite-to-PostgreSQL migration, Redis rate limiting and shared provider bulkhead, plus concurrent password-reset token consumption on PostgreSQL. Alembic `upgrade head` succeeded twice. |
| Browser/E2E | **220 passed, 22 skipped, 0 failed** across desktop Chromium and mobile Chrome. Included 1440×900 desktop and 375px mobile admin navigation, guest/admin JavaScript-console checks, RBAC buttons and endpoints, XSS guard, and viewport overflow checks. Skips are existing project/test annotations. |
| Load smoke | **10 virtual guests for 25 seconds; 0 failures.** CSV gate passed and verified the no-staff-conversation 404, guest escalation, and successful active staff-message response. The Locust console listed 426 requests; the CSV assertion counted 422. |
| Bandit | **Passed** with the CI command and no unsuppressed Medium-or-higher findings. Existing B608 notices correspond to reviewed static query fragments/placeholders. |
| Gitleaks | **Earlier scan passed:** 85 commits / about 4.40 MB scanned; no leaks found. A final repeat was blocked because the Docker socket denied access and no local Gitleaks binary is installed; the latest uncommitted diff was not rescanned by Gitleaks. |
| Docker build/runtime | **Passed before the final small input-validation tightenings:** image build, production configuration, non-root/read-only application files, writable state, and persistence across container recreation were checked. The final image was not rebuilt because Docker socket access was denied on the last run. |
| Python compilation / JS syntax / whitespace | **Passed:** `compileall`, `node --check app/static/admin.js`, and `git diff --check`. |
| `pip-audit` | **Not verified.** The tool could not upgrade pip/create its temporary environment because package network access is blocked. |
| `npm audit` | **Not verified.** The advisory endpoint `registry.npmjs.org` failed DNS resolution. |
| Trivy image scan | **Not run.** The CI workflow has the scan; a local Trivy executable/image was unavailable. |
| PostgreSQL backup/restore drill | **Not run.** The host lacks `pg_dump`; its integration test remains skipped unless `PG_DUMP_AVAILABLE` and the PostgreSQL client are installed. |

## Supported database test matrix

The normal full suite runs with the default SQLite database. The repository’s CI job runs the dedicated PostgreSQL/Redis integration modules against those services, rather than setting one shared `DATABASE_URL` for every SQLite-oriented test. The supported PostgreSQL/Redis command used here was:

```text
DATABASE_URL=postgresql+psycopg://concierge@127.0.0.1:55432/concierge \
REDIS_URL=redis://127.0.0.1:56379/0 \
REDIS_TEST_URL=redis://127.0.0.1:56379/2 \
.venv/bin/pytest -q -rs tests/test_postgres_integration.py tests/test_postgres_sqlite_migration.py tests/test_redis_rate_limiter.py tests/test_ai_provider_distributed_bulkhead.py
```

An exploratory attempt to point the entire suite at one PostgreSQL database produced **61 failures and 218 setup errors** because SQLite-oriented tests share/ignore their per-test database paths when a global `DATABASE_URL` is set. This is outside the repository’s CI database matrix; the full SQLite suite and the supported focused PostgreSQL/Redis matrix above both passed. The dedicated integration command is the PostgreSQL compatibility evidence.

The final SQLite/backend and browser commands were:

```text
.venv/bin/pytest -q -rs
npm run test:e2e -- --reporter=line
.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium
.venv/bin/python -m compileall -q app tests
node --check app/static/admin.js
git diff --check
```

The load smoke used the CI-equivalent 10-user, 25-second flow and its CSV assertion:

```text
LOADTEST_STAFF_CONVERSATION_FLOW=true locust --headless -f loadtest/locustfile.py -u 10 -r 2 -t 25s --host http://127.0.0.1:8092 --csv /tmp/concierge-load-smoke --only-summary
python loadtest/assert_smoke.py /tmp/concierge-load-smoke_stats.csv --require-staff-conversation
```

## Authorization, tenancy, and session probes

- Admin route-policy inventory and built-in role tests exercise direct APIs, missing permissions, anonymous access, and cross-property paths.
- `tests/e2e/admin.spec.js` verifies that users without `concierge.edit` cannot see Save Draft, Discard, or Publish controls and receive 403 responses if they call the corresponding endpoints directly.
- Guest-session regressions verify that session ID alone and legacy uncredentialed rows are rejected; client-chosen session IDs are ignored; credentials cannot replay across properties; expiry and revocation fail closed; resume rotates tokens; expired/revoked sessions cannot resume; legacy cookies are rotated/removed; and invalid-session cleanup preserves cookies for a different active session.
- Cookie tests verify production `Secure`, `HttpOnly`, `SameSite=Strict`, and `__Host-` scope. A many-session test keeps the resulting Cookie header below 8 KiB. Token tests verify credentials are hashed, opaque, absent from responses/logs, and session fixation input is ignored.
- Guest mutation tests cover hostile matching Host+Origin, hostile Referer, invalid explicit ports, cross-origin and cross-site Fetch Metadata rejection, and acceptance of configured property origins. Origin-less native/server clients remain supported; authenticated guest cookies and signed gateway checks are enforced in the route handlers.

## Attack cases exercised

- **SQL injection:** Regression tests submit hostile quote/boolean/union-style values; reviewed query values remain bound parameters.
- **Database dialect compatibility:** Modified SQL contains no `rowid` or `IS ?` usage. Conditional `UPDATE ... RETURNING` reset claims pass the SQLite concurrency regression and PostgreSQL concurrency integration; SQLite-to-PostgreSQL migration tests pass.
- **XSS:** Browser tests verify stored guest text is inert. Upload tests reject fake MIME/signatures, active/external SVG, image bombs, CSV formulas, malformed Office archives, macros, and embedded active content.
- **SSRF:** Outbound tests cover private and special-use ranges (including CGNAT, benchmark, and IPv6 ULA), DNS answers, same-origin redirects, blocked cross-origin redirects, and invalid header controls before DNS or connection. Deployment TLS verification rejects loopback, RFC1918, CGNAT, and IPv6 ULA answers before opening a socket.
- **Reset replay/concurrency:** A barrier synchronizes two SQLite callers immediately before the atomic claim; concurrent SQLite and PostgreSQL tests show exactly one accepted reset.
- **AI injection and tool security:** Local tests reject representative direct prompt-injection requests before provider invocation, mark retrieved content untrusted, prevent sensitive/injection-flagged knowledge from guest retrieval, and separately exercise server-side permission checks for tool proposals. No external/paid model red-team was performed.
- **ANTlabs replay:** Tests cover signature, timestamp, source network, property binding, and nonce replay. The real SG5 contract and device/session binding remain unverified.

## Scanner triage and limits

Bandit B608 notices are associated with generated `?` placeholders, fixed SQL clauses, or constant schema names; runtime values remain bound. The successful Gitleaks history scan reported no leaks, but it predates the latest uncommitted changes and could not be repeated because Docker socket access failed. Current Python/npm advisory status remains unknown because the advisory services were unreachable. The built image was not analyzed by Trivy. PDF extraction still checks the total character limit after parsing; high-expansion PDF behavior needs a safe resource-isolated worker test. No external production environment, gateway, or live AI model was available.
