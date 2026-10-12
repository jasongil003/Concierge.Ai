# ECC Phase 3 test results

## Candidate and test environment

- Branch: `fix/intelligent-ui-v2-phase3-release`
- Base commit: `2915974fceae9bf3ea46195254f52392968a0667`
- Candidate source remains an uncommitted local worktree; no new commit, push, merge, or deployment was made.
- Python used for backend tests: CPython 3.11.16. Python 3.12 was not installed on this host.
- Browser coverage uses desktop Chromium and mobile Chrome emulation. No physical iOS/Android device or Safari run is claimed.
- Tests use isolated temporary SQLite databases and upload directories. The persistent application database SHA-256 before and after the full pytest run was unchanged: `a682599b6e28da3051909d14d0018bf8825e80d663607ae579af35347f980e78`.

## Automated results

| Check | Result | Evidence / limit |
| --- | --- | --- |
| Full backend suite: `.venv/bin/pytest -q` | **1091 passed, 17 skipped, 0 failed, 2 warnings** | Final run completed in 38.14 seconds. Skips require unavailable optional integration services. |
| Full browser suite: `npm run test:e2e -- --reporter=list` | **277 passed, 35 skipped, 0 failed** | 312 tests across desktop Chromium and mobile Chrome emulation; 5.4 minutes. Runs against loopback with isolated test storage. |
| Focused Phase 3 backend regressions | **6 passed, 2 warnings; final location regression 1 passed, 2 warnings** | Covers additive facility migration/legacy insert shape, typed selection validation, property-scoped facility output, concurrent property streams, provider cancellation/slot release, isolated PDF page-count boundary, and status-note/location separation. |
| Focused browser regressions | **Passed in desktop Chromium and mobile Chrome emulation** | Typed selection required/review/edit/cancel/share flow and facility metadata editing/rendering are also included in the full suite. |
| Python compilation | **Passed** | `.venv/bin/python -m compileall -q app tests/test_ai_providers.py tests/test_intelligent_ui.py tests/test_knowledge_management.py tests/test_operational_admin.py` |
| JavaScript syntax | **Passed** | `node --check` on changed application JavaScript and Playwright specs. |
| Bandit CI policy | **Passed, exit code 0** | `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium`; scanner emitted parser warnings for existing `# nosec` and comment annotations. |
| `git diff --check` | **Passed** | Re-run after final report changes. |
| Persistent DB integrity | **Passed** | Hash remained unchanged; all test DBs were isolated. |

The new PDF worker diagnostic used synthetic input with a configured 96 MiB supervision threshold. The parent terminated and reaped the worker in about 0.046 seconds. Sampled peak RSS reached 115.8 MiB before termination, so this does not establish a hard 96 MiB OS-enforced ceiling; `FILE-DOS-01` remains `FIXED-UNVERIFIED` across supported operating systems.

## Bounded local performance sample

Twenty synthetic guest sessions were exercised with an in-process FastAPI `TestClient` and disposable SQLite database. The following are server-handler timings in milliseconds (not browser navigation, network, TLS, reverse-proxy, or production workload timings):

| Operation | Samples | Median | p95 |
| --- | ---: | ---: | ---: |
| Guest shell `GET /` | 21, including warm-up | 6.00 ms | 12.90 ms |
| Guest session creation | 21, including warm-up | 9.85 ms | 11.88 ms |
| Guest home retrieval | 20 | 14.93 ms | 16.05 ms |
| Guest personalization retrieval | 20 | 10.66 ms | 11.55 ms |
| Empty encrypted-history retrieval | 20 | 9.86 ms | 10.36 ms |

No configured AI provider was available, so time-to-first-token and full provider response latency were not measured. Cold browser load, client memory, query plans at production scale, and sustained concurrent throughput remain unmeasured; the provider concurrency tests are correctness tests, not load tests.

## Unavailable or blocked checks

- Python 3.12 was unavailable; Python 3.11.16 was used.
- GitHub Actions could not be queried because the `gh` CLI is unavailable. No remote workflow status is inferred from local tests.
- `npm audit --audit-level=high` could not reach `registry.npmjs.org` (`getaddrinfo ENOTFOUND`). No dependency result is claimed.
- `gitleaks`, `trivy`, and `pip-audit` are unavailable on the host. No secret, container-image, or Python dependency scan result is claimed.
- PostgreSQL and Redis services were unavailable. The 17 skipped tests include optional service-dependent coverage; no distributed-store or PostgreSQL result is claimed.
- Docker CLI is present, but its daemon is unavailable. No container build or target deployment test is claimed.
- No authorized OpenAI, Gemini, Groq, Anthropic, or local Ollama provider was configured. The 100-case live-provider benchmark remains **NOT RUN**; deterministic tests are not represented as model-quality results.
- The local route sample above does not establish browser page-load performance, provider latency, client memory limits, or production throughput.
- No target reverse proxy, TLS appliance, physical devices, Safari, or deployment hardware was available. Proxy buffering, idle timeout, TLS, platform-specific memory enforcement, clean-install/restart, and target rollback acceptance remain unverified or blocked.
- Transcript encryption key rotation has no tested reversible procedure. No key rotation or bulk transcript rewrite was attempted.

## Security and compatibility evidence

- Existing guest expiry, revocation, replay, signed-confirmation, property-isolation, RBAC, feature-flag rollback, and encrypted-history tests remain in the full suite.
- New form tests verify that cancel sends nothing and the explicit share action uses the ordinary idempotent chat path; no booking or service mutation route is invoked.
- The full browser run passed typed forms, guest rollback, property-configured breakfast, interactive maps, admin facility editing, legacy guest rendering, XSS guard, and the requested guest widths (320, 375, 390, 430, 768, 1024, 1440, 1920 px). A post-run backend regression also verifies status notes do not appear as a facility location when no location/map data exists.
- The Playwright suite also rewrote unrelated visual-baseline and control-inventory artifacts; those generated changes were restored from the current base, retaining only the new selection-form screenshots.
- Playwright's manual control inventory reports 2,113 visible control instances, 2,078 focusable controls, zero enabled-but-unfocusable controls, zero controls missing accessible names, and no invalid composite widgets in its covered views. This is an automated inventory, not a complete screen-reader or WCAG conformance audit.
- Facility migration tests preserve existing rows and legacy positional inserts by storing new fields in a separate additive table. Queries bind both property and facility identifiers.
- Concurrent provider streams are tested for property isolation; cancellation closes the provider iterator and releases its concurrency slot.
- PDF boundary and worker-recovery tests use disposable files and isolated processes.

## Reproduction commands

Run from the repository root:

```sh
.venv/bin/pytest -q
npm run test:e2e -- --reporter=list
.venv/bin/python -m compileall -q app tests/test_ai_providers.py tests/test_intelligent_ui.py tests/test_knowledge_management.py tests/test_operational_admin.py
node --check app/guest_v2/app.js
node --check app/static/app.js
node --check app/static/admin.js
.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium
git diff --check
```

This is local release-candidate evidence only; the final verdict remains **WORKING LOCAL PROTOTYPE**.
