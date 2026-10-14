# Release remediation and verification — 2026-10-14

## Scope and revision

- Repository: `jasongil003/Concierge.Ai`.
- Freshly fetched `origin/main`, local `main`, and `HEAD`: `4b36b5ecd39d8cda2e1c240dc1450d971244d77f` (`4b36b5e`, docs-only audit update).
- Previous implementation commit: `a30f95eb8db2ff05151c3473e453f9f38d0dec2d` (`a30f95e`). Its parent is `e4bbd7493fe9d90a513d8224749b54c9e25ddc90`.
- `4b36b5e` changes eight `docs/audit/*.md` files and no application, test, deployment, or configuration code. The `a30f95e` implementation changes were also reviewed: deterministic restaurant follow-up context, request idempotency, guest-shell favicon, media path/symlink boundaries, regression tests, and E2E fixture cleanup.
- This report and the fixes below are uncommitted local worktree changes on top of the fetched commit. No push, deployment, external credential rotation, Git history rewrite, production-data access, or remote setting change was performed.

Acceptance statuses describe only the evidence named here. Synthetic fixtures and mock integrations are never treated as live hotel acceptance.

## Confirmed findings and local fixes

| Severity | Finding and reproduction | Disposition |
|---|---|---|
| Medium — deployment reliability | Production Compose previously supplied a weak bootstrap-password fallback. The application rejects that fallback in production, so a fresh configuration without an explicit password could not start successfully. Compose itself could not be run because this host has no Docker daemon; the unsafe interpolation and fail-closed validation were confirmed by source review and the Compose regression test. | Removed the fallback; production Compose now requires `ADMIN_BOOTSTRAP_PASSWORD` explicitly at [docker-compose.yml](../../docker-compose.yml#L24). Added a regression in `tests/test_deployment_config.py`. |
| Medium — documentation/security hygiene | The quickstart documented a fixed administrator login inconsistent with the source installer, which generates a unique initial password and stores it in protected local configuration. | Removed the fixed login example and documented local retrieval/change at first sign-in in [README.md](../../README.md#L139). No credential value is reproduced here. |
| CI gate — scanner false positive | Gitleaks interpreted a single-line group of empty provider environment assignments in the local-demo script as a generic API key. Review showed the values were empty; it was not a credential. | Replaced the assignments with `unset` in [scripts/local-demo.sh](../../scripts/local-demo.sh#L75), added a regression test, and recorded a commit/path/rule-specific historical fingerprint exception in `.gitleaksignore`. Full-history Gitleaks then completed with no findings. |
| CI gate — scanner false positives | Bandit raised two B608 findings for SQL strings whose interpolated identifiers are drawn only from the fixed `PropertyStore.COLUMNS` tuple; record values remain bound parameters. | Added narrow, reasoned suppressions at [app/properties.py](../../app/properties.py#L595) and [app/properties.py](../../app/properties.py#L773). The configured Medium/High Bandit scan now reports zero findings. |
| Documentation accuracy | `docs/RELEASE_CONTROLS.md` counted seven CI jobs and omitted three defined jobs. | Corrected the inventory to ten jobs and clarified that repository rules must require them individually. |

The changes above were covered by **27 targeted tests passing** (2 warnings). The full backend suite below includes the new regression tests.

## Feature acceptance matrix

| Requirement | Status | Evidence and boundary |
|---|---|---|
| Admin authentication, session expiry/revocation, CSRF/origin checks | **VERIFIED** | Backend auth/session/guardrail tests passed; browser auth and session-resume flows passed. This verifies the tested application boundary, not a deployed identity provider or hotel network. |
| RBAC, role ceilings, restaurant/department scope | **VERIFIED** | Backend role-matrix, cross-property, department, and restaurant scope tests passed. Selected admin permission workflows also passed in Playwright. |
| Property isolation for guest sessions, content, requests, provider settings, maps, uploads | **VERIFIED** | Backend isolation regressions and browser cross-property/session cases passed using isolated synthetic properties. No hotel tenancy deployment was exercised. |
| Guest session continuity and old-message history | **VERIFIED** | Playwright reload/resume, transcript, and expiry-recovery journeys passed. Browser tests use isolated temporary data. |
| Guest privacy and location-data lifecycle | **PARTIAL** | Session protections and retention hooks have local tests. Approved consent, opt-out, retention, checkout, export, and deletion policy for location observations remains incomplete; this is a hotel-pilot blocker. |
| SQL injection protections | **VERIFIED** | Parameterized data values, fixed internal SQL identifiers, injection/security regressions, and the full backend suite passed. This is not a proof against all query paths or future identifier changes. |
| XSS protections | **VERIFIED** | Stored-XSS browser regression and backend output-encoding cases passed. |
| SSRF/outbound URL controls | **VERIFIED** | Outbound-host validation and IPv4/IPv6 cases passed in the backend suite. No request was sent to an external hotel/provider endpoint. |
| Upload validation and property media containment | **VERIFIED** | MIME/signature, active/external SVG, size/dimension, PDF/map, hash-name, and symlink-escape regressions passed. No hotel content or image rights were evaluated. |
| Current tracked-source secret scan | **VERIFIED** | Gitleaks 8.24.3 scanned full reachable history and tracked current source with zero findings after the exact false-positive exception. The ignored local `.env` was not inspected; a separate broad scan reported one pattern match there, so its contents and validity remain unknown. |
| Previously reported historical execution credential | **BLOCKED** | The October 13 report records a high-severity credential exposure in reachable history. This run did not display or validate the value; a targeted scan of the cited commit did not reproduce the report. Issuer, audience, validity, and completeness of refs/forks/caches remain unknown. Do not treat the scan result as proof of revocation or history cleanup. |
| Hotel information retrieval | **PARTIAL** | Property-scoped published-content retrieval and grounding paths passed local tests. No hotel-approved source content was supplied, so factual accuracy for a hotel is unverified. |
| Multi-turn restaurant context | **PARTIAL** | The deterministic four-turn sequence (“I'm hungry” → Japanese food → menu → location) passed against two synthetic restaurants. This proves the deterministic local path; live-provider response quality and hotel content accuracy remain unverified. |
| Restaurant/menu cards, prices, hours and images | **PARTIAL** | Playwright verified rendering/retrieval for published synthetic records. Real prices, availability, hours, imagery, and usage rights require property approval. |
| Facility maps, floors, landmarks, routes and text alternatives | **PARTIAL** | Synthetic map search, floor data, markers, and route rendering passed. Approved building plans, geometry, accessibility, and on-site route correctness were unavailable. |
| Property-specific content and publication workflow | **PARTIAL** | Property scoping, content review/publish, and guest retrieval workflows passed locally. No property owner approved or validated production content. |
| Service-request proposal and explicit guest confirmation | **PARTIAL** | Local browser/API flow created a request only after confirmation, showed its reference/status, and supported cancellation. Replay and eight concurrent same-key submissions produced one ticket. Staff delivery, fulfilment, escalation, and real SLA behavior were not exercised. |
| Guest reply rendering, composer layout and scroll behavior | **VERIFIED** | Full Playwright suite passed desktop Chromium and Pixel 7 emulation for replies, chronological history, persistent composer, long-conversation scroll anchor, responsive layouts, and no-overlap assertions. Physical devices and assistive technology were not tested. |
| Admin routes, forms, publication, dashboard and buttons | **PARTIAL** | Named admin CRUD/publish/request/user/role/dashboard flows passed. Inventory covered 42 destinations and 2,125 visible control instances; keyboard/accessibility checks found no enabled non-focusable controls or missing accessible names. The inventory does not behaviorally exercise every control or every error/permission path. |
| AI provider routing, streaming, fallback, spend and model quality | **IMPLEMENTED_NOT_VERIFIED** | Provider adapters and fixture-backed routing, masking, fallback, scope, and streaming tests passed. No live provider credential/call, cost, quota, latency, guest-data policy, or model-quality acceptance was performed. |
| ANTlabs mock flow | **VERIFIED** as simulation only | Mock contract tests passed. Mock success is not guest Wi-Fi authentication or Internet admission. |
| Live ANTlabs SG5, PMS, RADIUS/ACS, WLAN and captive-browser behavior | **BLOCKED** | No authorized staging gateway/PMS/network/device was available. Live redirect, admission, room validation, checkout, roaming, logout, and recovery remain unverified. |
| Dedicated QR/NFC product flow | **MISSING** | No dedicated product flow was found; sharing a canonical URL is not QR/NFC acceptance. |
| PostgreSQL/Redis deployment, migrations, restart and integration | **BLOCKED** | No Docker daemon, PostgreSQL/Redis binaries, or configured disposable service was available. Integration cases skipped. Do not count historical CI/container receipts as a fresh run. |
| SQLite backup/restore | **VERIFIED** for isolated local test data | `tests/test_backup_restore.py` passed backup, verification, and restore against disposable SQLite data. No hotel or production data was used. |
| PostgreSQL backup/restore, off-host encryption/key recovery | **BLOCKED** | PostgreSQL backup integration skipped; no independent off-host recovery target or key recovery rehearsal was available. |
| Install, upgrade, rollback and reboot recovery on target hosts | **PARTIAL** | Configuration/installer tests and a local service restart smoke passed. Clean Ubuntu/macOS host installation, production upgrade/rollback, reboot, and native recovery were not run. `systemd-analyze` was unavailable. |
| Production capacity and availability | **BLOCKED** | Only a bounded local loopback smoke ran: 1/5/10 workers, 100 requests each, all HTTP 200, then a local Uvicorn restart and health check. This is not a capacity, soak, or hotel-network SLO test. |

## Security and repository controls

- Backend static security and dependency checks: Bandit at the CI Medium/High threshold reported 0 findings after the narrow reviewed suppressions; `pip-audit -r requirements-dev.txt` reported no known vulnerabilities; online `npm audit --audit-level=high` reported 0 vulnerabilities.
- Secret detection: full reachable-history and tracked-tree Gitleaks scans passed after the exact empty-assignment false-positive exception. The older reported historical credential remains unresolved as described above. The ignored local `.env` match was not read or printed and needs owner-side validation.
- CI definitions: `.github/workflows/ci.yml`, `macos-native-validation.yml`, and `release.yml` were reviewed. CI defines ten jobs: backend tests, JavaScript dependency audit, Python dependency audit, Bandit, secret scan, browser tests, PostgreSQL/Redis integration, Docker runtime, Linux deployment validation, and macOS artifact validation. Workflow actions are pinned to commit SHAs; secret scanning covers history and current source; dependency/image/SBOM checks are configured.
- Hosted CI results for the fetched SHA were not independently retrieved. No tracked `CODEOWNERS` or Dependabot configuration was found. GitHub rulesets/branch protection cannot be inspected from this workspace. The previous October 13 report said main had no required checks; current state is therefore **unverified and a release blocker**, not assumed fixed.
- Production Compose now requires an explicit bootstrap password, encryption secret, metrics token, canonical host/base URL, and admin CIDRs. Production cookie/host/proxy boundaries and loopback-only development bindings have local regression coverage. No target TLS, DNS, proxy chain, management VLAN, or appliance secret permissions were tested.

## Verification run

| Check | Result |
|---|---|
| Full backend: `PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -rs` | **1,184 passed, 18 skipped, 0 failed** in 45.79s; 2 deprecation warnings. |
| Full browser: `npm run test:e2e` | **334 passed, 38 project-specific skips, 0 failed** (372 total) in 6.2 minutes; Chromium and Pixel 7 emulation. |
| Targeted deployment/demo regressions | **27 passed**, 2 warnings in 2.23s. |
| Gitleaks 8.24.3 | Full reachable history and tracked worktree: **0 findings** after the exact, reviewed local-demo false-positive exception. |
| Bandit application scan | **0 findings** at Medium/High configured threshold after reviewed suppressions; fixed-column SQL construction remains parameterized. |
| Python dependencies | `pip-audit -r requirements-dev.txt`: **no known vulnerabilities found**. |
| JavaScript dependencies | `npm audit --audit-level=high`: **0 vulnerabilities**. |
| Bounded local HTTP/restart smoke | **300/300 HTTP 200**, no failures at 1/5/10 workers; app stopped, restarted, and health returned healthy. |
| Persistent workspace database | Hash unchanged by tests. Tests used temporary SQLite data; no customer data was accessed. |
| `git diff --check` | Passed on the final worktree. |

Backend skips: Redis bulkhead and rate-limiter checks; Linux `RLIMIT_AS`; PostgreSQL backup plus 13 PostgreSQL integration/migration cases; and `systemd-analyze`. Browser skips are project-specific duplication/platform exclusions. The Docker daemon was unavailable, and no `psql`, PostgreSQL server utilities, Redis server/CLI, Podman, or `systemd-analyze` executable was present.

## Release decisions

- **Internal demo: READY for isolated local synthetic-data use only.** The local demo unsets external provider keys and uses mocked ANTlabs behavior. Keep the demo on loopback, use no real guest/property data, and do not distribute this checkout or claim a live hotel integration while the historical credential and local ignored `.env` findings remain unvalidated.
- **Hotel pilot: NOT READY.** Blocked by location-privacy policy/lifecycle, the unresolved historical credential review, approved property content/maps, live gateway/PMS/network acceptance, provider data-sharing and quality acceptance, staff fulfilment, and target-host recovery.
- **Production: NOT READY.** In addition to the pilot blockers: current branch protection/required checks are not independently verified, hosted CI results are unavailable, production PostgreSQL/Redis/Docker and off-host backup/key recovery were not exercised, and no target capacity/SLO test ran.

## Erratum — follow-up review of `6bc9fbba880389c08d8fc011383fc2274e632665`

A fresh Gitleaks 8.24.3 run found that the earlier “full reachable history” clean result did not account for the non-diffable attribute on the retained recovery-harness evidence file. The default history scan returns zero findings, but a scan of all reachable refs with `--log-opts="--all --text"` returns three `generic-api-key` detections in `audit/evidence/security-2026-10-12/recovery-harness-before.txt`, commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`, lines 10, 17, and 24. This supersedes the earlier claim that reachable history was clean. The value is not reproduced here; issuer-side invalidation and authorized history cleanup remain outstanding.

The current-worktree Gitleaks scan also returned one match in the ignored, untracked local `.env` at line 5 (`CREDENTIAL_ENCRYPTION_SECRET`); its value was not printed or classified as production configuration. A forced-text, redacted history scan is now part of `.github/workflows/ci.yml`, and is expected to fail until the historical credential is addressed. See `LATEST_COMMIT_REVIEW.md` and `SECURITY_REMEDIATION.md` for the complete fresh evidence. No credential rotation, history rewrite, or remote setting change was performed.
