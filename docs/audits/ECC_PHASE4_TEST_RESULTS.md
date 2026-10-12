# ECC Phase 4 test results

## Candidate and environment

- Branch: `fix/intelligent-ui-v2-phase4-hardening`.
- HEAD/baseline SHA: `712316989e7baa8dc6b8946ca7192cfa2b22802c`; no commit was created.
- Host: macOS Apple Silicon; CPython `.venv` 3.11.16, Node.js 26.7.0. Python 3.12 was unavailable.
- Tests use temporary SQLite databases and synthetic fixtures. The persistent `state/concierge.db` remained unchanged; SHA-256 was `a682599b6e28da3051909d14d0018bf8825e80d663607ae579af35347f980e78` before and after both full pytest runs.
- Live GitHub refs/workflows could not be queried because `github.com` DNS was unavailable. The local tracking ref `origin/main` points to the reviewed Phase 3 merge above.

## Backend and static checks

| Check | Result | Notes |
| --- | --- | --- |
| `.venv/bin/pytest -q` | **1,098 passed, 18 skipped, 0 failed, 2 warnings** | Final run 38.17 s. Skips include optional PostgreSQL/Redis integrations, Linux-only `RLIMIT_AS` evidence, and unavailable host tooling. Warnings are Starlette's `httpx` TestClient deprecation and AnyIO's deprecated `BlockingPortal` alias. |
| `tests/test_transcript_rotation.py` | **6 passed** | Covers v1/plain/untagged legacy reads, v2 mixed-key reads, unknown/wrong key failure, synthetic escrow recovery, batched migration, interruption/resume, idempotency, database write rollback, rollback to old-release formats, 240-row migration, concurrent sessions, and property scope. Included in the full pytest count. |
| PDF worker platform tests | **Parent supervision passed; Linux kernel-limit test skipped** | Host is macOS. Defaults: 25 MiB upload, 5 files per upload, 2,000 archive members, uncompressed archive bytes bounded by 12× extracted-text cap (6,000,000 bytes at the 500,000-character default), 100:1 archive ratio, 300 PDF pages, 10,000 blocks, 500,000 extracted characters, 20-second `RLIMIT_CPU`, 30-second parent wall timeout, and 768 MiB configured worker memory. Linux additionally sets `RLIMIT_AS`; that kernel test is platform-skipped here. macOS has no demonstrated hard per-process memory cap; Windows also uses parent supervision when POSIX `resource` is unavailable. |
| Python compile | **Passed** | `.venv/bin/python -m compileall -q app tests/test_transcript_rotation.py tests/test_knowledge_management.py tests/test_security_remediation.py`. |
| JavaScript syntax | **Passed** | `node --check` on guest/admin application JavaScript and every `tests/e2e/*.js` file. |
| Bandit CI threshold | **Passed, exit 0** | `bandit -q -r app -x app/static --severity-level medium --confidence-level medium`; Bandit emitted the repository's `# nosec`/comment parsing warnings. |
| `git diff --check` | **Passed** | Re-run after final edits. New untracked deliverables were also checked for trailing whitespace. |
| `npm audit --audit-level=high` | **BLOCKED** | npm registry request failed DNS resolution for `registry.npmjs.org`. |
| `pip-audit -r requirements-dev.txt` | **BLOCKED** | Audit could not install its isolated pip tooling, then direct/no-deps audit failed DNS resolution for `pypi.org`. No dependency audit pass is claimed. |
| Gitleaks / Trivy | **NOT RUN** | Neither executable is installed. Docker CLI exists, but its daemon/socket is unavailable, so an image scan could not be run. |

## Browser suite

The first complete `npm run test:e2e -- --reporter=list` run completed **276 passed, 35 skipped, 1 failed** in 5.6 minutes. The failure was `guest: restaurant card details button toggles verified details` on mobile Chrome: the details paragraph appeared while the second button still read `Details` instead of `Hide details`.

The same test passed in four subsequent isolated runs: three repeated mobile runs and one desktop-plus-mobile sequential run against the same isolated server. The retry-enabled complete suite then completed **277 passed, 35 skipped, 0 failed** in 5.3 minutes. The test was not disabled or weakened. The single initial failure remains recorded as not reproduced in focused reruns or the final complete suite.

The run's control inventory counted 2,113 visible control instances and 2,078 focusable controls, with zero enabled-but-unfocusable controls, zero controls missing accessible names, and no invalid composite widgets in its covered views. This automated inventory is not a WCAG 2.2 AA conformance or screen-reader audit. Chromium/Pixel 7 emulation covered responsive browser cases, including the requested widths; physical iOS/Android, Safari, captive browsers, and screen readers were not available.

Playwright rewrote one control inventory and three screenshot baselines during its run. Those generated files were restored from HEAD; no unrelated audit baseline changes remain.

## Bounded local performance sample

101 measured samples per operation after one warm-up, using in-process FastAPI `TestClient`, temporary SQLite, and synthetic transcript text. Reproduce with `.venv/bin/python scripts/phase4_performance_sample.py`. Times are milliseconds.

| Operation | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| Guest shell `GET /` | 5.155 | 11.274 | 133.925 |
| Liveness `GET /health/live` | 0.839 | 1.014 | 1.114 |
| Encrypted transcript write | 0.967 | 1.305 | 1.788 |
| Encrypted transcript retrieval | 0.630 | 0.783 | 4.223 |

The test process RSS was 108.9 MiB at sample start and 128.6 MiB at sample end; this was not a peak-RSS or memory-ceiling measurement. Process CPU time for the whole sample was 0.824 seconds. There was no browser network, TLS, proxy, live provider, PostgreSQL/Redis, concurrent capacity test, or representative pilot hardware. `ECC-PERF-001` remains **BLOCKED**.

The bounded synthetic PDF-worker supervisor sample (`.venv/bin/python scripts/phase4_pdf_resource_sample.py`) used a 96 MiB demonstration threshold and sampled worker RSS at 1 ms while the production parent supervisor polled at 25 ms. On macOS it observed **98.7 MiB peak RSS**, then killed and reaped the worker; its temporary directory was removed and the parent process remained alive. That is sampled termination with a 2.7 MiB observed overshoot, not a hard OS memory ceiling. `FILE-DOS-01` remains **FIXED-UNVERIFIED** pending Linux and target-OS enforcement evidence.

## Provider, database, streaming, and operations

- **Live AI benchmark: NOT RUN pending authorization.** Metadata-only inspection found stored Gemini/Groq credential rows, but values were not read. The prompt's approval condition for external synthetic data is not yet established. No provider call or score is claimed.
- **PostgreSQL/Redis: BLOCKED.** No service binaries or disposable services were available; Docker daemon is unavailable. PostgreSQL migrations/concurrency and Redis rate-limit/bulkhead behavior did not run. Service-dependent pytest cases were skipped.
- **SSE proxy: BLOCKED.** Local backend/browser streaming regressions ran, but no proxy, target endpoint, or live provider was available. Buffering, TCP disconnect, proxy timeouts, and first-event latency remain unverified.
- **Backup/recovery: local SQLite tests passed** in the full backend suite. Off-host backup restore, key escrow access, target installation/upgrade, TLS/proxy, and release rollback remain blocked.
- **Deployed version and current GitHub Actions status: unverified** because no deployment evidence or GitHub DNS access was available.

No real guest data or external provider was used. No production rotation, database update, deployment, push, merge, or commit occurred.
