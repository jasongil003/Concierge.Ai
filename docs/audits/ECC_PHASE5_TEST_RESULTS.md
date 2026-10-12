# ECC Phase 5 test results

## Candidate and host

- Baseline / current `HEAD`: `6fd9d2309f28137a2ab3823ca99794656998b5d8` (`admin`). Working branch: `fix/intelligent-ui-v2-phase5-stabilization`.
- Candidate includes uncommitted working-tree changes; no final commit SHA exists.
- macOS Apple Silicon, CPython 3.11.16 in `.venv` and isolated CPython 3.12.14 in `/tmp/phase5-venv`, Node v26.7.0, Playwright 1.63.0.
- The suites use temporary SQLite fixtures. Persistent `state/concierge.db` remained unchanged at SHA-256 `a682599b6e28da3051909d14d0018bf8825e80d663607ae579af35347f980e78`.
- GitHub Actions and current remote refs could not be queried: `git ls-remote origin HEAD` failed because `github.com` did not resolve. CI outcomes below are local, not GitHub-hosted results.

## Backend suites

| Command | Result | Notes |
| --- | --- | --- |
| `.venv/bin/pytest -q` (Python 3.11.16) | **Final sequential run: 1,100 passed, 18 skipped, 0 failed** (43.48 s). | The first concurrent Phase 5 run had 1,099 passed, 18 skipped, 1 failure: the 301-page PDF limit fixture hit its 30-second worker timeout while the Python 3.12 and browser suites competed for CPU. The isolated fixture then passed (1 passed), followed by this clean full rerun. Earlier baseline was 1,098 passed, 18 skipped. |
| `/tmp/phase5-venv/bin/python -m pytest -q` (Python 3.12.14) | **1,100 passed, 18 skipped, 0 failed** (54.30 s). | Isolated interpreter and dependencies; project `.venv` was not modified. |
| `pytest -q tests/test_transcript_rotation.py tests/test_backup_restore.py` | **14 passed** on both interpreters. | Includes corrupt ciphertext and incomplete archive regressions. |
| `npm run test:e2e -- --grep 'guest: restaurant card details button toggles verified details|guest: expanded restaurant details survive a chat response rerender' --repeat-each=8 --reporter=list` | **32 passed**. | Two specs × eight repeats × desktop Chromium and Pixel 7 emulation. |
| Full Phase 5 pytest reruns | **Python 3.11: 1,100 passed, 18 skipped, 0 failed. Python 3.12: 1,100 passed, 18 skipped, 0 failed.** | Python 3.11's one timeout under concurrent heavy workloads passed in isolation and in the sequential full rerun. |
| Full Phase 5 Playwright suite | **279 passed, 35 skipped, 0 failed** (5.6 minutes). | Fresh temporary SQLite DB and loopback test server; did not reuse demo server on port 8188. |

Both Python versions report two existing deprecation warnings from Starlette's `httpx` TestClient integration and AnyIO's `BlockingPortal` alias. No warning is a Phase 5 test failure.

## Focused UI investigation and regression

The original intermittent UI failure was reproduced **4 times in 24 pre-fix repeated runs** (desktop and Pixel 7 emulation). Playwright trace showed a valid Details click expanding the paragraph, followed by `/api/chat` completion calling `renderMessages()`. That function replaced the message DOM; the new card initialized collapsed with the label `Details`. This was a state-loss race, not a weak assertion. The test now verifies expand/collapse, exact accessible names, `aria-expanded`, a single card, and focus restoration across a deliberately delayed response.

The 32 focused post-fix runs passed. The full Phase 5 suite passed with **279 passed, 35 skipped and 0 failures**. A generated desktop control inventory reported 2,130 visible control instances, 2,096 focusable controls, zero enabled-but-unfocusable controls, zero controls missing accessible names, and no invalid composite widgets. Playwright regenerated that audit inventory and a screenshot baseline; both were restored from `HEAD` after the run. This is automated Chromium evidence, not a WCAG 2.2 AA or screen-reader certification.

## Static and security checks

| Check | Result | Notes |
| --- | --- | --- |
| `node --check` on changed guest UI and browser spec | **Passed** | Full JavaScript syntax sweep is included in final validation. |
| `python -m compileall -q app ...` on Python 3.11 and 3.12 | **Passed** | Includes the changed regression files. |
| `bandit -q -r app -x app/static --severity-level medium --confidence-level medium` | **Passed, exit 0** | Emits existing `# nosec` and comment parsing warnings; no threshold finding failed. |
| `shellcheck --severity=warning -x` on Linux/macOS installer scripts | **Passed, exit 0.** | CI-relevant deployment lint. |
| `git diff --check` | **Passed before documentation creation; final pass pending.** | Re-run after all deliverables. |
| `npm audit --audit-level=high` | **Passed: found 0 vulnerabilities.** | Completed with registry access. |
| `.venv/bin/python -m pip_audit -r requirements-dev.txt` | **Passed: no known vulnerabilities found.** | Completed with package advisory service access. |
| Gitleaks / Trivy | **Unavailable locally** | Neither executable is installed; Docker daemon is not running. No pass is claimed. |

## Bounded PDF worker sample

`.venv/bin/python scripts/phase4_pdf_resource_sample.py` ran on macOS with a demonstration threshold of 96 MiB and 25 ms parent polling. Peak sampled worker RSS was **99.8 MiB**. The worker was terminated and reaped, temporary data was removed, and the parent remained alive. This is sampled parent supervision with a 3.8 MiB observed overshoot, not an OS-enforced hard memory ceiling. Production configuration defaults to a 768 MiB worker RSS threshold; Linux additionally configures `RLIMIT_AS`, but Linux was not available for this run.

Configured ingestion bounds confirmed in source: 25 MiB/file, five files/upload, 2,000 archive members, archive uncompressed bytes at most 12× the 500,000-character extraction cap, per-member compression ratio at most 100:1, 300 PDF pages, 10,000 text blocks, 500,000 extracted characters, 20 seconds `RLIMIT_CPU`, and 30 seconds parent wall timeout.

## Fresh local performance sample

`.venv/bin/python scripts/phase4_performance_sample.py` used temporary SQLite, synthetic data and in-process FastAPI `TestClient`, with 101 samples per operation. See [Phase 5 performance results](../intelligent-ui/PHASE5_PERFORMANCE_RESULTS.md) for full statistics and limits. This is not proxy, provider or capacity evidence.

## External acceptance and unavailable services

- PostgreSQL/Redis: **BLOCKED**. No server binaries and no Docker daemon/socket. Service-gated integration cases were skipped; unit/mocked tests do not substitute for service acceptance.
- SSE/reverse proxy: local application tests only. No Nginx, Caddy or target proxy is available.
- Live provider benchmark: **NOT RUN**. No explicitly authorized non-production provider credential was supplied for this run; no provider request or quality score is claimed.
- Physical iPhone/iPad/Android, Safari, tablet hardware, captive browser, QR/NFC and assistive-technology acceptance: **NOT RUN**. Pixel 7 is browser emulation only.
- Off-host backup and key recovery, clean/upgrade install, service restart and rollback: **BLOCKED** pending disposable target infrastructure and separately recovered test keys.
