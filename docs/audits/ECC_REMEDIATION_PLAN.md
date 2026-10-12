# Concierge.AI ECC Audit — Prioritized Remediation Plan

> Historical pre-Phase 2 plan. Use [ECC_PHASE2_REMEDIATION_BACKLOG.md](ECC_PHASE2_REMEDIATION_BACKLOG.md) for remaining work and [ECC_PHASE2_FINDINGS.md](ECC_PHASE2_FINDINGS.md) for current statuses.

This is an audit backlog only. No remediation was implemented during this read-only audit.

## P0 — Critical security and data integrity

No open P0 item was confirmed. Maintain existing security regression gates.

| Reference | Work and code area | Regression and dependencies | Acceptance |
| --- | --- | --- | --- |
| `ECC-SES-001` (fixed) | Preserve authentication-time-bound renewal and conditional hash/revocation update in `app/session_store.py` and `app/main.py`. | Keep deterministic expiry boundary, error, cookie, revoke-before/after-auth, repeat-slide tests. Add a controlled concurrent renew/revoke test. | Targeted and full test suite pass on Python 3.12 and supported SQLite/PostgreSQL paths; revoke wins or renewal is safely followed by revoke with no credential revival. |

## P1 — High-severity security

No open P1 finding was confirmed. Before future release, run the production CI security gates (including secret/history scanning) on the exact clean commit. No external penetration test is authorized by this audit.

| Reference | Work and code area | Regression and dependencies | Acceptance |
| --- | --- | --- | --- |
| `ECC-SES-001` | Above concurrency test and supported-Python matrix. | Disposable test DB; CI Python version and configured DB services. | No race produces a refreshed cookie without persisted valid credentials; expired/revoked credentials never resume. |

## P2 — Major functional and reliability issues

| Reference | Work and code area | Regression and dependencies | Acceptance |
| --- | --- | --- | --- |
| `ECC-OPS-001` | Complete `docs/CONTROLLED_POC_ACCEPTANCE.md`, `docs/PRODUCTION_ACCEPTANCE.md`, deployment scripts and recovery runbooks on disposable Ubuntu/macOS target(s). | Requires approved appliance, synthetic data, test gateway/provider, TLS/proxy, DB/cache services, backup target. | Clean install; TLS/trusted proxy; guest/admin flows; reboot; valid update; failed update rollback; independent restore; health; sanitized evidence all pass. |
| `FILE-DOS-01` | Exercise `app/knowledge_management.py` and `app/pdf_extraction_worker.py` on each supported OS using the approved synthetic memory-expansion fixture. | Requires isolated host/fixture and RSS monitoring; no sensitive documents. | Worker is killed/reaped at configured ceiling, request fails in a controlled way, app remains healthy, valid bounded PDF still extracts. |
| `OPS-021` | Add direct guest answer regression around `app/main.py:6408-6490` plus `tests/e2e/guest.spec.js` and deterministic property data. | Synthetic restaurant meal periods/opening hours; desktop and mobile Playwright. | Breakfast answer uses only eligible property data, includes the correct time or explicit unknown-hours fallback, and has no generic misleading answer. |
| CI integration evidence | Run exact clean commit through `.github/workflows/ci.yml` with PostgreSQL 16/Redis 7, migration, backup, rate-limit, and load-smoke jobs. | GitHub Actions services; exact source SHA. | All required jobs pass; skipped locally are green in CI; release artifact is traceable to tested SHA. |

## P3 — Intelligent UI compatibility improvements

| Reference | Work and code area | Regression and dependencies | Acceptance |
| --- | --- | --- | --- |
| `ECC-UI-001` | If required, design and implement bounded SSE support across `app/main.py`, `app/intelligent_ui.py`, and `app/guest_v2/app.js`. | Protocol decisions: auth per stream, cancellation, reconnect, event ordering/limits, rate accounting, provider timeout. | Tests prove event schema validation, session/property checks, disconnect cleanup, no duplicate action, bounded resource use, safe fallback. If streaming is not in product scope, document that decision. |
| `ECC-UI-002` | Document/rehearse global restart-based rollback and per-property disable; consider a dynamic audited kill switch only after design review. | Requires deployment operator access and tested process supervision. | Global disable reaches all instances within measured objective, assets/API fail closed, rollback route to legacy works for open and fresh pages. |
| UI release review | Review current uncommitted UI files, preserve legacy compatibility, and promote through clean CI. | Must start from a clean branch and exact tested state. | Security and functional browser suites pass; no unrelated audit/worktree files included; release gate records SHA. |
| Shared-device handling | Define transcript retention and clearing for `sessionStorage` in `app/guest_v2/app.js`. | Product policy for public/shared guest devices. | Clear-on-session-end/replacement and reload behavior are tested; no expectation that tab storage is an authorization boundary. |

## P4 — Cosmetic, maintainability, and optimization

| Reference | Work | Acceptance |
| --- | --- | --- |
| `ECC-UI-001` | Decide whether to expose loading/progress states without streaming or keep one-shot response behavior. | Documented UX decision and browser test. |
| `ECC-OPS-001` | Add CI artifact retention for sanitized test, migration, dependency, and acceptance summaries. | Evidence has exact source SHA and contains no credentials or guest data. |
| General | Add explicit Python lint/format and frontend lint/build scripts only if adopted as project standards. | CI and contributor docs use the same pinned tools and commands. |

## Dependency order

1. Keep `ECC-SES-001` tests in CI and add the revocation/renewal interleaving test.
2. Run exact-commit hosted CI to cover PostgreSQL/Redis and required scanners.
3. Close PDF OS acceptance and direct guest-answer assertions.
4. Complete disposable appliance and recovery acceptance before any guest pilot.
5. Decide streaming and rollback requirements, then review/release the Intelligent UI behind its existing gates.
