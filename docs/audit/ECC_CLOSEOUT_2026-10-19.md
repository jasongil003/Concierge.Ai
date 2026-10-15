# Concierge.Ai ECC closeout

**Prepared:** 2026-10-15 (Asia/Manila)  
**Requested milestone:** 2026-10-19  
**Code baseline:** `ba56274262053fe03b2db71b9c57ee25c8445377` (merged PR #57)  
**Working branch:** `codex/ecc-closeout-20261019`  
**Implementation commit:** pending publication  
**Pull request:** pending publication

This closeout records work and verification completed on the stated synthetic/local environments. It does not assert production readiness, legal approval, or live-provider acceptance.

## Verification matrix

| Workstream | Status | Evidence and remaining work |
|---|---|---|
| Facility maps and directions | **GREEN (synthetic)** | Existing map editor, revisions, publish/restore, guest-visible nodes, floor switching, route transitions, accessible routing, and missing-route behavior passed backend and browser coverage. Synthetic facility data is verified; real building accuracy remains **BLOCKED** on hotel-approved plans and a property walkthrough. |
| AI providers | **GREEN (deterministic); BLOCKED (live)** | Adapter, routing, fallback, interrupted-stream, timeout, quota, credential encryption, and consent regression tests are in the full backend suite. No approved live provider credential was configured here, so no live connection is claimed. |
| Nearby recommendations | **GREEN (synthetic); BLOCKED (live)** | Synthetic coordinate scoping, bounded radius/results, provider response validation, safe map links, consent gating, error handling, and structured guest cards are covered by backend and browser tests. No approved Google Places credential was configured; live discovery and provider licensing/quota acceptance remain unverified. |
| Notification engine | **YELLOW** | The PostgreSQL claim-release defect is fixed; property-local quiet hours, retries, dedupe, consent/preferences, service-request updates, and scheduled hotel-event reminders are tested. Actual PostgreSQL execution is pending hosted CI. Facility-closure and current-weather-source triggers are not complete; no approved weather source is configured. |
| Guest privacy | **YELLOW** | Periodic retention, checkout cleanup, immediate optional-consent withdrawal, notification preference deletion, export/deletion protections already in the baseline, aggregate metrics, and cross-property tests pass locally. Property-owner/privacy approval of policy, retention exceptions, and legal text remains outstanding. |
| Deployment and recovery | **YELLOW; target recovery BLOCKED** | Installer, startup/configuration, migration, backup/restore, proxy, recovery-ledger, and outage behavior have synthetic tests. Docker is unavailable on this host; PostgreSQL/Redis service checks, clean target installs, reboot/upgrade recovery, encrypted off-host backup, separate key escrow, and a disposable-host restore were not performed. |
| Security and CI | **RED** | The current tracked tree scan is clean, but Gitleaks still finds three reachable-history findings in retained audit evidence. Repository rules do not require CI status checks. No finding was suppressed and no history rewrite or credential-revocation claim was made. |

**Excluded:** the 30,000-user load target remains **DEFERRED**. No 30,000-user test was run or represented as passed.

## Confirmed fixes

### PostgreSQL notification claim release

`_release_guest_delivery_claim` no longer sends the SQLite-oriented predicate `claim_token IS ?` to PostgreSQL. It now uses two fixed query forms: `claim_token IS NULL` for a null token and `claim_token = ?` for a non-null stale token. This preserves compare-and-release semantics without interpolating caller-controlled SQL.

Regression coverage checks SQLite quiet-hours release, stale claim rejection, retry/reclaim, frequency limits, and concurrent workers. The added PostgreSQL integration test exercises the same paths against a live PostgreSQL service when `DATABASE_URL` is configured. That test was collected but skipped locally because no PostgreSQL URL/service was available; the repository's hosted `postgres-redis-integration` job is the remaining execution gate.

### Retention, consent, and checkout

- Added bounded `RETENTION_MAINTENANCE_INTERVAL_SECONDS` and `GUEST_NOTIFICATION_RETENTION_DAYS` configuration.
- Added a periodic, restart-resumable maintenance task when background workers are enabled. Failures are counted and logged by exception class; the next interval retries.
- Cleanup covers eligible consent, location, personalization, stay/session/device, and notification records. It is idempotent and records aggregate category counts only.
- Checkout removes read and pending inbox content, preference records, and frequency locks for that stay. The store operations remain property scoped.
- Withdrawing optional processing consent or disabling an optional notification category purges its inbox content. Delivery also rechecks current consent and preferences before acknowledging an item as sent.

### Property-local notification time

Property updates now validate timezone names as IANA zones. Notification scheduling and event reminder display use the property's zone, including overnight and daylight-saving cases covered by tests. A corrupt legacy timezone causes event reminder scheduling for that property to be skipped and logged without stopping inbox dispatch.

### Verified event reminders

Staff-entered, all-guest hotel events can produce one in-app reminder inside the configured lead window when the property enables reminders and the active stay has experience notifications and proactive consent enabled. Dedupe keys include the source event ID and start time. Reminder facts come from the stored event; an AI response does not create or augment them. Scheduling and dispatch now have separate worker error handling so an event scheduling error does not suppress the inbox dispatch pass.

## Changed files

- `.env.example`
- `app/config.py`
- `app/guest_identity.py`
- `app/hospitality.py`
- `app/main.py`
- `app/metrics.py`
- `app/properties.py`
- `tests/test_guest_privacy_consent.py`
- `tests/test_notification_delivery.py`
- `tests/test_notification_quiet_hours.py`
- `tests/test_postgres_integration.py`
- `tests/test_properties.py`
- `docs/audit/ECC_CLOSEOUT_2026-10-19.md`

No database migration was added. Browser-generated files under `audit/evidence/` were restored to their baseline contents and are not part of this change.

## Verification results

### Backend and static checks

- `.venv/bin/pytest -q -rs`: **1,308 passed, 19 skipped**, 2 deprecation warnings, 56.44 seconds.
- `.venv/bin/python -m compileall -q app`: passed.
- `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium`: passed. Bandit emitted existing parser and `nosec` warnings; it reported no gate failure.
- `git diff --check`: passed.
- The suite's persistent SQLite safety check reported the workspace database unchanged.

Skip breakdown: 15 PostgreSQL-related cases (including PostgreSQL backup/restore and SQLite-to-PostgreSQL migration), 2 Redis service cases, 1 Linux-only memory-limit acceptance, and 1 `systemd-analyze` case because that utility is absent. The PostgreSQL/Redis integration workflow is configured in `.github/workflows/ci.yml`, but its result for this branch is pending the pull request.

### Browser and visual checks

- Full local `npx playwright test --reporter=line`: **339 passed, 39 skipped, 4 failed**. The failures were a mobile admin-navigation timeout, two responsive manual-QA timeouts (1280×720 and 375×812), and one mobile operations-console mock fallback.
- Each failing case passed in an isolated rerun: admin navigation passed, both responsive cases passed, and the operations-console mock case passed. The full run is therefore recorded as flaky, not green.
- Focused `npx playwright test tests/e2e/visual.spec.js --grep @visual`: **4 passed** across desktop Chromium and mobile Chromium.
- Focused synthetic journey `npx playwright test tests/e2e/admin-actions.spec.js:224 tests/e2e/admin-actions.spec.js:336 tests/e2e/guest.spec.js:934 tests/e2e/guest.spec.js:1386 --project=chromium`: **4 passed** (admin map editing, cross-floor transitions, nearby cards, and guest indoor directions).
- Existing guest-interface evidence: [verified pool answer](evidence/guest-ui-acceptance-2026-10-14/verified-pool-answer-desktop.png), [restaurant desktop](evidence/guest-ui-acceptance-2026-10-14/restaurant-desktop-1440x900.png), [restaurant tablet](evidence/guest-ui-acceptance-2026-10-14/restaurant-tablet-768x1024.png), and [restaurant mobile](evidence/guest-ui-acceptance-2026-10-14/restaurant-mobile-390x844.png). These screenshots are dated 2026-10-14, not newly captured by this closeout.

### Security, dependencies, and live integrations

- Gitleaks 8.24.3 reachable-history scan: **failed with 3 findings across 231 commits**, all in `audit/evidence/security-2026-10-12/recovery-harness-before.txt`. The finding values are intentionally omitted. The file is retained as audit evidence; no suppression or history rewrite was performed.
- Gitleaks current tracked working tree plus this report: **0 findings**. A scan of the whole local working directory also flagged one generic-key pattern in ignored `.env` at line 5; it is not tracked or included in the proposed change, and its value was not printed. The local owner should determine whether that ignored value is live and rotate it with its issuer if needed.
- `npm audit --audit-level=high` could not reach `registry.npmjs.org` from this host (`ENOTFOUND`); no local dependency-audit result is claimed.
- `pip-audit -r requirements-dev.txt` did not complete in the local environment while attempting to bootstrap its pip dependency. The hosted dependency-audit job remains authoritative for this branch.
- Docker runtime check: unavailable (no Docker daemon/socket).
- `DATABASE_URL`, `REDIS_TEST_URL`, global cloud-provider keys, and Google Places key were not configured in this environment. Consequently, no actual PostgreSQL, Redis, AI-provider, Places, weather, hotel network, or external gateway connection was tested.

## Hosted CI and repository controls

- Baseline PR: [PR #57](https://github.com/jasongil003/Concierge.Ai/pull/57) was merged at the stated baseline. Its recorded CI was 9/10 jobs successful; the historical secret scan remained failing.
- This closeout PR: pending publication. After opening, the run list will be available at `https://github.com/jasongil003/Concierge.Ai/actions` and the PR checks at its `/checks` page. Results are not claimed until fetched.
- The repository ruleset inspected for `main` protects branch deletion and non-fast-forward updates but does not require CI status checks. The integration could not access the branch-protection administration endpoint. A repository administrator must make the required CI checks mandatory before merging.

## External blocker owners and actions

1. **Credential issuer / repository owner:** verify revocation or rotate the historical credential, then approve coordinated history cleanup and secret re-scan. The current three-history-finding failure cannot be waived by this change.
2. **Repository administrator:** configure required status checks for `main` and confirm merge protection rejects failing checks.
3. **CI owner:** verify this PR's hosted secret, dependency, backend, browser, PostgreSQL/Redis, and security jobs. The local PostgreSQL and Redis tests are skipped until hosted execution.
4. **Property/privacy owner:** approve the applicable policy text, retention schedule, and retention exceptions. Do not collect real guest location or optional-processing data before approval.
5. **Hotel operations owner:** validate synthetic map positions against approved building plans and verify facility closure/event facts before enabling guest notifications.
6. **Infrastructure/recovery owner:** provide authorized Ubuntu/macOS/Docker targets, production-like PostgreSQL/Redis, encrypted off-host backup destination, separately escrowed recovery key, and a disposable restore target. No destructive restore was attempted.
7. **Provider account owner:** supply approved AI and Places API credentials with account/API access and terms confirmed before any live connection test.

## Release decision

**NO-GO for an internal release candidate at this time.** The local synthetic implementation and most automated suites pass, but the historical credential finding and missing required-check enforcement are security gates, the full browser run had four flaky failures, and live PostgreSQL/Redis and deployment recovery evidence is pending. An isolated internal synthetic demo remains suitable only with synthetic data and no live provider or guest-data claims. This repository must not be described as production-ready.
