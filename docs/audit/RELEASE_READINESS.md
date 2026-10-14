# Release readiness

Date: 2026-10-14 (Asia/Manila)  
Reviewed commit: `6bc9fbba880389c08d8fc011383fc2274e632665`  
Working changes: local and uncommitted; no push or deployment occurred.

## Release decisions

| Release target | Decision | Basis |
|---|---|---|
| Internal demo | **Conditional — isolated local synthetic demo only** | Backend and Playwright workflows pass locally, and Compose configuration fails closed without a unique bootstrap password. Do not distribute the current clone/build or expose it to real guest data until the historical credential owner confirms invalidation and an authorized history-cleanup plan is complete. |
| Hotel pilot | **Not ready** | Historical credential remains in reachable history; location/AP consent and retention lifecycle is incomplete; hotel-approved content/maps/imagery are absent; live AI, SG5/PMS/WLAN, staff delivery, physical devices, and target-host recovery have not been accepted. |
| Production | **Not ready** | Pilot blockers remain, plus Docker runtime, PostgreSQL/Redis, target-host install/upgrade/rollback/reboot, off-host backup/key recovery, trusted proxy/TLS, operational recovery, branch protection, and representative capacity evidence are missing or blocked. |

## Deployment and recovery evidence

| Area | Current status | Evidence and boundary |
|---|---|---|
| SQLite development | **Verified locally** | Full backend suite passed. Persistent repository DB hash and WAL/journal sidecars were unchanged. |
| PostgreSQL production and migration | **Blocked** | PostgreSQL integration and SQLite-to-PostgreSQL cases skipped because no `DATABASE_URL` service was configured. |
| Redis | **Blocked** | Two Redis-dependent cases skipped because no test Redis service was configured. |
| Docker Compose | **Configuration verified** | `docker compose config --quiet` succeeded with synthetic required settings; missing `ADMIN_BOOTSTRAP_PASSWORD` failed interpolation. |
| Docker runtime | **Blocked** | Docker CLI is present, but no daemon/socket is running. No image build, runtime health, non-root write, or volume persistence check ran. |
| Ubuntu/macOS install and services | **Partially verified** | Installer/configuration unit tests ran. `systemd-analyze` was unavailable; no clean Ubuntu host or native macOS appliance install/reboot was tested. |
| SQLite backup/restore | **Verified in isolated tests** | Backend backup/restore tests passed against disposable data. |
| PostgreSQL/off-host backup, encryption, and key recovery | **Blocked** | No PostgreSQL service or independent recovery target/key rehearsal was available. |
| Upgrade, rollback, and restart recovery | **Partially verified** | Local code/configuration and rollback regressions passed; no clean target-host upgrade, reboot, or production restore rehearsal ran. |
| 30,000 concurrent guests | **Blocked** | No representative load/soak environment or 30,000-user result exists. Do not infer capacity from unit, E2E, or small local smoke tests. |

## Security and integration gates

1. Credential owner confirms invalidation/rotation of the historical browser identity credential; repository owner authorizes history cleanup and verifies hosted refs, forks, clones, and caches. The value is not included in this report.
2. The new forced-text full-history Gitleaks CI step passes after cleanup. It currently detects the three historical copies and therefore is expected to fail.
3. Approve and implement location/AP privacy consent, opt-out, retention, checkout, export, and deletion behavior with tests.
4. Use owner-approved property content, imagery rights, map geometry, accessible routes, and on-site route verification.
5. Complete live AI provider privacy, quality, streaming/fallback, cost/quota, and rate-limit acceptance without exposing sensitive guest data.
6. Complete authorized ANTlabs SG5/PMS/WLAN/captive-device acceptance and staff request delivery/fulfilment workflow validation.
7. Run clean target-host install, upgrade, rollback, restart, backup/restore, and key recovery rehearsals for supported deployment profiles.
8. Run representative staged load and soak tests with latency, error, resource, queue, database, Redis, and provider quota measurements.
9. Repository branch protection and required checks remain unverified: the read-only GitHub API returned 401. An authorized repository admin must inspect and configure them; no settings were changed here.

## Verification ledger

- Backend: **1,185 passed, 18 skipped, 0 failed**. Skips are PostgreSQL/Redis and platform-specific memory/system-service checks.
- Playwright: **334 passed, 38 project-specific skips, 0 failed** across Chromium and Pixel 7 emulation.
- Bandit configured Medium/High scan: **0 findings**; 46 B608 suppressions reviewed.
- Python dependency audit: **no known vulnerabilities**.
- Node dependency audit: **0 vulnerabilities across 3 packages**.
- Current-tree Gitleaks: one unclassified, ignored `.env:5` match for the local encryption-secret variable; no value printed. The `.env` file is not tracked.
- Full reachable-history Gitleaks with forced text diffs: **3 historical findings** in the recovery-harness artifact; release blocker.
- Compose syntax: verified using synthetic settings; Docker execution blocked by missing daemon.
- GitHub branch settings: blocked by unavailable authentication (HTTP 401).

### GitHub Actions follow-up

Run [38560724104](https://github.com/jasongil003/Concierge.Ai/actions/runs/38560724104) had a failed `browser-tests` job; its other jobs passed. The browser failures exposed an incorrect Playwright server override in CI, which skipped the test-only session-clock routes, plus one desktop scroll-anchor timing failure. CI now uses `tests/e2e/run_server.py`, and the scroll test establishes its starting position without smooth-scroll animation. All 12 affected local browser cases passed across Chromium and Pixel 7 emulation when repeated twice. A new GitHub run is still needed to verify the workflow correction remotely.
