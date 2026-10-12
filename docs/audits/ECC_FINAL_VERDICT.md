# Concierge.AI ECC Audit — Final Verdict

**Assessment date:** 2026-10-12

**Deployment classification: INTERNAL DEMO ONLY**

## Repository state

- Branch: `feature/intelligent-guest-ui-v2`
- HEAD: `fbf9d50635c427f5340098cac48e7bb8eb7ef7a2`
- The worktree already contained six modified tracked files and untracked Intelligent UI source, tests, demo script, and documentation. Those user changes were preserved. The audit added only the eight files under `docs/audits/`.
- No commit, push, merge, deploy, database reset, or production configuration change was made.
- Cached local `origin/main`, local `main`, and `origin/HEAD` point to HEAD. Live remote status is **unverified** because GitHub lookup failed at DNS/network resolution.

## Security findings

- **Critical open:** 0
- **High open:** 0
- **Medium:** `FILE-DOS-01` is **FIXED-UNVERIFIED** pending high-expansion PDF resource acceptance on supported OSes; `ECC-OPS-001` is **BLOCKED** pending target deployment and recovery checks.
- **Low:** `ECC-UI-001` (SSE not implemented) and `ECC-UI-002` (global rollback requires process restart) are **OPEN**.
- **Historical High fixed:** `ECC-SES-001` guest expiry race is **FIXED-VERIFIED** in the current checkout.
- **Functional acceptance:** `OPS-021` breakfast answer appears corrected in source but remains **FIXED-UNVERIFIED** until an exact desktop/mobile end-to-end assertion runs.

No current Critical or High application security issue was confirmed by this local code review and test evidence. This conclusion is bounded by the skipped integrations and unavailable hosted/production checks.

## Test and scanner results

- Target guest expiry regression: **1 passed, 2 warnings**.
- Full backend pytest: **961 passed, 17 skipped, 2 warnings**. Skips are 12 PostgreSQL tests, one PostgreSQL/SQLite migration, one PostgreSQL backup test, one Redis limiter, one Redis provider bulkhead, and one unavailable `systemd-analyze` check.
- Playwright non-visual browser suite: **265 passed, 35 skipped, 0 failed** across Chromium and mobile Chrome (300 cases). One initial harness attempt lacked a temp `audit/` output directory; it was rerun with that directory created outside the repository. The inventory case passed on rerun and output remained outside the repository.
- Bandit: passed at the CI medium severity/confidence thresholds.
- `npm audit --audit-level=high`: 0 vulnerabilities.
- `pip-audit -r requirements-dev.txt`: no known vulnerabilities.
- Python compile (45 files), JavaScript syntax, shell syntax, and workflow YAML parsing: passed.
- `git diff --check`: re-run after reports; see final verification below.
- Local environment did not provide Python 3.12, Gitleaks, a Docker daemon/Trivy scan, or live GitHub access. These are unverified, not passing results.

## Session expiry review

The response-time check in the original per-session-cookie implementation could fail after a request authenticated just before expiry and finished just after it. Current renewal uses the authentication timestamp, rejects already-expired requests, limits renewal authority to one TTL, rechecks both credential hashes and revocation in a transaction, and sets the cookie only after a successful persisted update. Deterministic tests verify the original timing boundary, repeated slide, cookie Max-Age, expired rejection, and revoked-session non-revival. This fully addresses the reported local SQLite race. A concurrent interleaving stress test and Python 3.12 execution remain outstanding.

## Backend stability

The backend is stable for the tested local SQLite and application flows. The full pytest suite, browser suite, static checks, and dependency scans provide positive evidence. It is not yet certified for production stability: PostgreSQL and Redis integration, external gateways/providers, target hardware, TLS/proxy, appliance reboot/update rollback, and disaster recovery were not executed here.

## Intelligent UI readiness

The current implementation supports a gated, structured, non-streaming prototype with bounded schemas, current-session/property authorization, existing chat policy, text-only rendering, property-scoped cards, and explicit confirmation for service actions. It can be used for an internal synthetic-data demo in an isolated environment. SSE is absent, global disable needs restart, shared-device transcript policy needs clarity, answer-quality acceptance needs direct tests, and the UI changes remain uncommitted.

## Deployment decision

**INTERNAL DEMO ONLY.** Restrict use to an isolated internal environment with synthetic property/guest data. Do not treat this audit as clearance for hotel guest pilot or production. The exact blockers are: unverified hosted CI/current remote SHA, locally skipped PostgreSQL/Redis jobs, incomplete appliance and off-host recovery acceptance, unverified PDF RSS guard on target OS, and outstanding Intelligent UI rollback/product acceptance. Existing repository acceptance docs independently state these checks are required.

## Exact next work

1. Run hosted CI for the exact clean commit, including PostgreSQL, Redis, migration, backup, secret-scan, and container checks.
2. Add deterministic concurrent guest renewal/revocation coverage and run the backend suite on Python 3.12.
3. Run PDF expansion controls on every supported OS and add exact breakfast-answer desktop/mobile tests.
4. Complete disposable appliance install, TLS/proxy, gateway, reboot, update rollback, backup, and off-host restore acceptance.
5. Decide whether SSE is required; rehearse and document global rollback; review and release the Intelligent UI source only after those gates pass.

Detailed findings and acceptance steps: [security](ECC_SECURITY_FINDINGS.md), [functional](ECC_FUNCTIONAL_FINDINGS.md), [session review](ECC_SESSION_EXPIRY_REVIEW.md), [UI readiness](ECC_INTELLIGENT_UI_READINESS.md), [test evidence](ECC_TEST_EVIDENCE.md), and [remediation backlog](ECC_REMEDIATION_PLAN.md).
