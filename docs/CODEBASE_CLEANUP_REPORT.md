# Concierge.Ai remediation and cleanup report — 2026-10-17

**Readiness: source patch ready for owner review; historical incident and production release remain BLOCKED.** No commits, branch/ref changes, history filtering, ref deletion, publication, production restore or system service changes were executed by this agent. Browser-generated tracked evidence was restored to its baseline bytes after testing.

Baseline branch: `codex/guest-lifecycle-notifications-20261016`. Baseline/current HEAD: `17038c2758f3bf9483f5a9480ef63b812433d7f7`. Initial working tree was clean. The verified historical incident was accepted as supplied; its secret value and original transcript were not opened or reproduced. The explicit CI `--all --text` scan, `.gitleaksignore` and `.gitattributes` remain unchanged.

## Required status matrix

PASS below means the stated local evidence passed; it does not certify external infrastructure or production.

| Area | Current Status | Fix Applied | Verification | Remaining Blocker |
|---|---|---|---|---|
| Credential Revocation | PASS owner report / NOT VERIFIED independently | Owner confirmed revoked and private evidence available | Chat confirmation only; no credential requested | Independent issuer/auth-rejection evidence, account scope, timestamp and private ticket reference remain private owner actions |
| Historical Secret Exposure | BLOCKED | Hardened preparation and ordered runbook | Known incident accepted; no repeat discovery | Explicit rewrite approval and independently confirmed revocation |
| Gitleaks | PASS clean current-source snapshot / BLOCKED sanitized history | Scanner settings preserved | Gitleaks 8.24.3: clean source snapshot zero findings; local raw worktree has one ignored `.env` finding | Both real post-rewrite modes/default Action event must pass after approved maintenance |
| Git Reference Preservation | PASS synthetic gates / BLOCKED actual rewrite | Collision, maps, tips/types, exact reachable sets, counts and parent topology gates | Known five-commit-loss fixture rejected; read-only preflight rejects 11 current collisions | Fresh canonical source, owner approval, actual generated maps |
| Environment Isolation | PASS | Source installer/service allow-lists; QA dotenv disabled; test-state layout corrected | Synthetic sentinel/failure-output tests and actual HTTP sample | New runtime settings require explicit allow-list review |
| Backup Security | PASS local drill | Scoped auth/TLS environment; safe exceptions; common pg_dump runner | Backup tests; 17 real isolated PostgreSQL tests | Production authentication, credentials and scheduled delivery are deployment-specific |
| WSL Installer | PASS bounded local/synthetic checks / NOT VERIFIED native WSL | Shared connect timeout plus bind check; indeterminate state blocks install | IPv4/IPv6/refused/timeout/bind/closure tests; real port-check 0.047s | Native WSL mirrored-networking confirmation |
| PostgreSQL/SQLite Tests | PASS | Explicit diagnostic config wins over caller environment | Baseline mismatch reproduced; original PostgreSQL assertion retained and passes; SQLite behavior preserved | None for local covered paths |
| Backend | PASS local suite | Focused backup duplication removal, scoped environment construction, Alembic path parsing | Supported Python matrix; compile; Bandit | Skipped infrastructure cases and production runtime |
| Frontend | PASS functional suite | No speculative UI rewrite | 376 browser tests pass; three static JS files syntax-check | 42 browser skips; dedicated visual snapshot/platform checks not run |
| Guest Concierge | PASS tested flows / NOT VERIFIED live service | Existing behavior preserved | Conversation/context/error/scroll/session/tool tests | Real provider responses and deployed hotel content |
| AI Providers | PASS unit behavior / NOT VERIFIED live | Supported provider settings remain in explicit runtime allow-list | Existing provider/fallback/timeout tests | No real provider credentials used; external availability not certified |
| Facility Maps | PASS tested behavior | Existing property-specific map behavior preserved | Map revisions/uploads/routing and browser workflows | Live deployed hotel map/content review |
| Notifications | PASS tested behavior / NOT VERIFIED delivery | Existing consent/targeting/property scoping preserved | Delivery/campaign/quiet-hours/privacy unit/browser tests | Real configured downstream delivery |
| RBAC / Guest Privacy | PASS covered regressions | Existing policy/scoping checks retained | Department, high-RBAC, policy inventory and guest privacy suites | Production role/config review remains deployment-specific |
| Deployment / Recovery | PASS local install/upgrade/PostgreSQL drill / BLOCKED container recovery | Bounded probes, correct diagnostics, isolated app children, one lock re-execution | Real disposable bootstrap/reinstall; lock-flow test; database backup/restore | Docker daemon unavailable; native Linux/WSL service verification |
| CI/CD | PASS locally executed gates / NOT VERIFIED hosted CI | No weakened checks or workflow edits | Python/browser/static/dependency checks below | Authorized commit/publication; historical leak; Docker image/Trivy/SBOM/platform jobs |

## Exact changes and patch delivery

Actual unified diffs for all security-critical code/tests are in [SECURITY_REMEDIATION_2026-10-17.patch](audit/SECURITY_REMEDIATION_2026-10-17.patch). The patch contains only selected source/test/config files, with no private `.env`, audit transcript or historical credential.

Changed source/config files:

- `alembic.ini`: explicitly selects OS path separation, removing the existing migration-config warning.
- `app/backup.py`: preserves explicit password-file/TLS/Kerberos authentication while excluding unrelated host settings; URL values take precedence. Removes duplicate pg_dump subprocess handling. Suppresses timeout/missing-tool exception chains and raw failure output.
- `deploy/common/diagnostics.py`: explicitly selected config values take precedence over shell values; explicit blank SQLite configuration remains authoritative.
- `deploy/common/preflight.py`: uses the shared bounded probe and fails closed on indeterminate state. `_foreign_uvicorn_active()` remains a bounded, two-second `ps` operation.
- `deploy/common/port_probe.py` (new): timeout is one second per IPv4/IPv6 candidate; failed connects require a successful local bind to establish availability. Bound sockets, unsupported IPv6 and socket errors are handled explicitly; sockets always close.
- `deploy/common/runtime_environment.py` (new): explicit application settings and required PATH/home/temp/locale/proxy/certificate/libpq runtime keys. Excludes arbitrary host credentials and Python injection settings. Application provider credentials are forwarded only under supported explicit setting names.
- `deploy/source_install.py`: both initialization and validation app subprocesses use the allow-list plus selected private configuration.
- `deploy/source_service.py`: shared probe and scoped fallback-service child environment; removes a redundant local subprocess import.
- `scripts/master_audit_http_sample.py`: retains the baseline allow-list, additionally disables checkout dotenv loading, nests isolated state correctly, and withholds failed bootstrap output. The baseline already had the requested host-environment fix; this patch completes safe operational behavior.
- `scripts/failure_recovery_smoke.py`: retains the verified allow-list; adds only explicit dotenv disablement so checkout credentials cannot re-enter through `app.config`. The original fix was not rewritten.
- `scripts/prepare_secret_history_cleanup.sh`: supports bare/full source repositories; rejects shallow sources; invokes collision preflight before cloning; inventories all ref types/relationships; records local-tree exceptions with expected-OID deletion safeguards in the disposable mirror; retains empty commits/merges; invokes the stronger gate and path-removal verification; never pushes.
- `scripts/history_preservation.py` (new): independently testable read-only preflight/snapshot/verification helper. Rejects duplicate maps, missing/extra destinations, changed types/tips, removed/collapsed commits, substituted reachable sets and changed ordered parents. Documents origin-tracking namespace migration.

Changed/new tests: `tests/test_failure_recovery_harness.py`, `tests/test_master_audit_http_sample.py`, `tests/test_source_install.py`, `tests/test_remediation_stabilization.py`, `tests/test_source_installer_lock_flow.py`. The new lock-flow test uses synthetic executable stubs and the real lock wrapper/shell re-execution, stopping intentionally before venv/dependency/service mutation. All pre-existing tests are retained.

Documentation: this report, [history runbook](SECURITY_HISTORY_CLEANUP_RUNBOOK.md), [deployment/WSL/upgrade/recovery troubleshooting](DEPLOYMENT_RECOVERY_TROUBLESHOOTING.md), [ECC closeout](audit/ECC_REMEDIATION_CLOSEOUT_2026-10-17.md), and the unified patch.

## Before/after and executed checks

| Check | Before / root cause | After / evidence |
|---|---|---|
| Initial targeted baseline | 87 passed, 1 skipped, 1 failed; HTTP mock attempted a sandbox-prohibited real bind, and lacked a process PID | Hermetic socket/process mocks and stronger sentinel/output/required-key checks pass |
| Doctor PostgreSQL assertion | Reproduced one failure using baseline `read_config` with `DATABASE_URL=` in caller environment: expected PostgreSQL, reported SQLite | Implementation precedence fixed; original assertion unchanged and deployment suites pass |
| HTTP sample real startup | Baseline state equalled child system-temp root; existing test-state guard refused startup | Nested state + dotenv disabled; 300/300 successful requests across 1/5/10 workers and healthy restart |
| WSL-style port check | No timeout patch existed at initial inspection; prior WSL stall accepted from supplied evidence | Local Linux-mode check exit 0 in 0.047s; synthetic timeout/bind/IPv6 coverage; native WSL not verified |
| Reference collision/loss | Baseline gate could accept null/collapsed map entries based only on surviving-count comparison | Five-commit-loss/null-map fixture hard-fails; equal-count substituted histories and changed parents hard-fail |
| PostgreSQL drill fixture | Initial SQL_ASCII disposable cluster made psycopg return bytes to SQLAlchemy version detection | Test-only UTF-8 cluster initialization; 17 passed, encrypted backup + separate clean restore database verified |

Final test matrix and exact commands:

- Python 3.11.16, `.venv/bin/python -m pytest -q`: **1415 passed, 22 skipped** (closeout run).
- Python 3.12.14, `/tmp/concierge-venv312/bin/python -m pytest -q`: **1414 passed, 22 skipped**, followed by **4 passed** for the subsequently added lock regression and final recovery-harness change.
- Python 3.13.15, `/tmp/concierge-venv313/bin/python -m pytest -q`: **1414 passed, 22 skipped**, followed by the same **4 passed** final targeted check.
- Python 3.14.7, `/tmp/concierge-venv314/bin/python -m pytest -q`: **1415 passed, 22 skipped** (closeout run).
- The 3.14 security/deployment/backup targeted suite also passed **114 tests, 1 skipped** before the additional lock regression. Final isolation/preservation tests on 3.11 passed **33**, and the added shell lock-flow test passed separately.
- `node node_modules/@playwright/test/cli.js test --grep-invert @visual`: **376 passed, 42 skipped**, desktop/mobile Chromium, isolated temporary app state; no failing browser tests. Skips are retained as limitations, not converted to PASS.
- Real disposable PostgreSQL 16.15 cluster: migrations plus `tests/test_postgres_backup_integration.py tests/test_postgres_integration.py`: **17 passed**. The cluster was stopped/removed. No production database was connected or restored.
- Real source-install stages in a temporary source copy: port check, prepare, initialization, repeat prepare/initialization **PASS**; `.env` and existing admin preserved; no service commands.
- `.venv/bin/python -m compileall -q app deploy scripts`: **PASS**. `node --check` over the three `app/static` JavaScript files: **PASS**. No separate frontend build/typecheck/lint script is configured in root `package.json`.
- `bash -n scripts/prepare_secret_history_cleanup.sh` and `shellcheck --severity=warning scripts/prepare_secret_history_cleanup.sh`: **PASS**. `git diff --check`: **PASS**.
- `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium`: **PASS**, no findings at the configured gate; existing nosec-comment parser warnings remain.
- `npm audit --audit-level=high`: **PASS**, zero vulnerabilities. `.venv/bin/pip-audit -r requirements-dev.txt`: **PASS**, no known vulnerabilities. No dependency version or lock-file changes were needed. Runtime direct pins and the npm lock were retained; a fully hashed Python transitive lock remains a pre-existing reproducibility limitation.
- Persistent/default SQLite safety checks report the existing database unchanged, with no journal/WAL/SHM changes attributable to tests. No customer data reset occurred.

Versions: pytest 9.1.1; FastAPI 0.141.1; Starlette 1.3.1; httpx 0.28.1; SQLAlchemy 2.0.54; psycopg 3.3.6; Alembic 1.18.5; Bandit 1.9.4; pip-audit 2.10.1; Gitleaks 8.24.3. Existing httpx/AnyIO compatibility deprecations remain (two warnings in default runs). No speculative major upgrades or dependency removals were made.

## Gitleaks and reference evidence

The local raw worktree scan found **one** credential-like value in ignored `.env`. Its contents were neither displayed nor copied into evidence. This is private local configuration outside a clean CI checkout; do not upload it. A clean snapshot of versioned files and current nonignored additions returned **zero findings** with Gitleaks 8.24.3 `detect --no-git`. This separately named scope is not represented as a successful raw-worktree or history scan.

The real post-rewrite default-diff scan, actual Action event range and explicit `--all --text` scan are **BLOCKED**, because no rewrite was authorized or executed. Historical findings remain confirmed, with no new ignore entries or exclusions. Earlier offline cleanup success is not reused as evidence for the changed preservation tool.

Read-only inspection: **11** local/origin branch-name collisions, including the known closeout branch. Preflight correctly refuses this source. There are **21** local `refs/codex/turn-diffs/*` tree refs, one reaching the known compromised blob; the earlier supplied count was 19. No tree content was read and no ref was deleted. Private OID/type inventory: `/tmp/concierge-local-tree-refs.json`. Remote read-only inventory: 27 branch refs, 0 tags and 36 PR refs; no advertised Codex turn-diff refs. Absence from today's advertisement does not prove they were never published. Remote snapshot is `/tmp/concierge-remote-refs-readonly.tsv`, for inspection only; maintenance must take a fresh baseline.

Actual ref-map/commit-map preservation, fingerprint remapping, sanitized reachability, GitHub PR reachability/cache purge and collaborator recovery are each **BLOCKED/NOT VERIFIED**. The runbook includes verified CLI interfaces, private before/after inventories, exact preparation/remap/scanner commands, per-ref expected-old-OID leases, stop conditions, rollback precautions and postpublication PR/local-ref checks. `.gitattributes` removal is explicitly deferred until published sanitized refs are verified, per owner policy.

## Scope decisions and owner actions

Focused cleanup removed duplicated pg_dump execution and redundant import logic, fixed diagnostics and migration configuration, and hardened the directly related subprocess/installer paths. Existing backend/frontend feature coverage passed. No unsupported conclusion about unused features/endpoints/dependencies justified deletion; no wholesale UI/backend rewrite was made. The generic operation-lock wrapper intentionally inherits environment for re-executing the same operator command; app subprocess boundaries now isolate their own environment. Docker CLI/tool invocations use their intended provider/registry authentication context, not a dumped environment.

Docker is unavailable: its configured server socket does not exist. Consequently container recovery/Redis interruption, production image build/Trivy/SBOM/Compose runtime and container CI smoke are **BLOCKED** here. Native Linux systemd, native WSL and dedicated visual/platform CI checks are **NOT VERIFIED**. Actual external AI, places and notification delivery were not exercised with real credentials. No 30,000-user load test was run.

Required owner actions, in order:

1. Privately provide/review the non-secret incident reference and independent revocation/rejected-authentication evidence; confirm replacement deployments and access-log review.
2. Review the patch/runbooks and explicitly authorize any desired source commit. This report does not authorize one.
3. Separately approve the maintenance window, fresh clone/ref operations and offline rewrite after the credential gate. Reconcile current collisions by using a fresh canonical source; do not overwrite either competing tip.
4. Require actual preservation maps, exactly ten approved remaps and zero findings in both history modes and the applicable default Action event before any publication approval.
5. Separately approve explicit lease-protected publication, postpublication attribute cleanup and any local-tree-ref deletions. Coordinate collaborators, GitHub Support/cached/PR refs and CI/deployment refresh.
6. Complete environment-dependent/native/provider checks before declaring production release or incident closure.
