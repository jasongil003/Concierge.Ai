# ECC Phase 6 Test Results

## Candidate and host

- Branch: `test/phase6-infrastructure-acceptance`.
- HEAD: `49b9575b705987fc961bb6380be502b5b549d809`; Phase 6 documentation/harness changes are uncommitted.
- Host: macOS Apple Silicon; CPython 3.12.14 at `/tmp/phase5-venv/bin/python`, CPython 3.11.16 at `.venv/bin/python`, Node v26.7.0, npm 11.19.0.
- Tests use isolated temporary state. The persistent SQLite safety fixture reported database SHA-256 `a682599b6e28da3051909d14d0018bf8825e80d663607ae579af35347f980e78` unchanged after both full runs.
- The supplied Phase 6 baseline SHA is absent locally. `origin/main` is only the local tracking ref at `6fd9d230`; remote refresh and GitHub Actions inspection are blocked by `github.com` DNS failure.

## Backend tests

| Command | Result | Notes |
| --- | --- | --- |
| `/tmp/phase5-venv/bin/python -m pytest -q` | **1,100 passed, 18 skipped, 0 failed** (39.93 s) | CPython 3.12.14. Two existing Starlette/httpx and AnyIO deprecation warnings. Persistent DB unchanged. |
| `.venv/bin/python -m pytest -q` | **1,100 passed, 18 skipped, 0 failed** (39.42 s) | CPython 3.11.16. Same two deprecation warnings. Persistent DB unchanged. |
| `/tmp/phase5-venv/bin/python -m pytest -q -rs` | **1,100 passed, 18 skipped, 0 failed** (38.49 s) | Skip reasons below; the repeat was to capture them explicitly. |
| Python compile + JavaScript syntax | **Passed** | `python -m compileall -q app` on both interpreters; `node --check app/static/app.js`; `node --check tests/e2e/guest.spec.js`. |
| Phase 6 harness/config | **Passed** | `bash -n scripts/phase6/acceptance.sh`; `shellcheck --severity=warning -x scripts/phase6/acceptance.sh`; Compose JSON assertions confirmed staging mode, loopback-only published ports, internal DB/cache networks, disabled local AI, and the global guest UI flag off. Synthetic staging settings validated without a service connection. A dummy external `DOCKER_HOST` was refused without a query; dummy unsafe environment overrides did not change the loopback assertion. `start` stopped before resource creation because the local daemon is unavailable. |
| `git diff --check` and new-file whitespace scan | **Passed** | `git diff --check` exit 0; separately checked all 11 untracked Phase 6 files for trailing whitespace/NUL bytes because Git's diff check omits untracked files. |
| PostgreSQL/Redis service tests | **Not run / skipped in full suites** | No service URLs, PostgreSQL/Redis servers, or Docker daemon. See integration harness in `scripts/phase6`. |

The 18 Python skips are explicit and expected for this host: 14 PostgreSQL cases (including migration and backup/restore) lack `DATABASE_URL`/PostgreSQL 16 `pg_dump`; two Redis integration cases lack `REDIS_TEST_URL`; the Linux `RLIMIT_AS` acceptance test is platform-specific; and the systemd installer check skips because `systemd-analyze` is absent. These remain service/platform gates, not passing tests.

## Browser tests

`npm run test:e2e -- --grep-invert @visual --retries=1 --reporter=list` passed **275 tests and skipped 35** in 5.6 minutes. The visual suite `npm run test:visual -- --grep @visual --retries=1 --reporter=list` passed **4/4** snapshots (2 visual scenarios in desktop Chromium and Pixel 7 emulation). Combined: **279 passed, 35 skipped, 0 failed**. Both runs used a fresh temporary SQLite state directory and loopback-only app server on port 8092; the sandbox initially denied the loopback bind, then the run succeeded with narrowly scoped permission. Expected skipped cases are platform/project-specific exclusions (desktop-only flows are not repeated on mobile, mobile-only cases are omitted on desktop, and visual tests are selected separately); no failure was converted to a skip. This is not physical-device, Safari, captive-browser, WCAG certification, or proxy acceptance.

The automated control inventory reported 2,113 visible control instances, 2,078 focusable controls, no enabled-but-unfocusable controls, no missing accessible names, and no invalid composite widgets. That inventory and responsive browser checks are useful evidence, not a WCAG 2.2 AA or screen-reader certification.

## Security and supply chain

| Check | Result | Notes |
| --- | --- | --- |
| Bandit | **Passed, exit 0** | Ran the CI threshold: `bandit -q -r app -x app/static --severity-level medium --confidence-level medium`. It emits existing `nosec`/comment parsing warnings; no threshold finding failed. |
| `npm audit --audit-level=high` | **Blocked** | npm registry request failed with `getaddrinfo ENOTFOUND registry.npmjs.org`; no current advisory result is claimed. |
| `pip-audit -r requirements-dev.txt` | **Blocked** | Installed auditor's temporary pip bootstrap failed because package index DNS/network was unavailable. No clean audit result is claimed. |
| Gitleaks | **Unavailable** | Executable is not installed; GitHub secret-scan Action status could not be fetched. |
| Trivy | **Unavailable** | Executable not installed and no container image was built. |
| GitHub Actions | **Blocked from this host** | Remote access/DNS fails; no workflow status is inferred from local tests. |

## Infrastructure and service-dependent acceptance

- Docker Compose CLI exists, but `docker info` cannot connect to `/Users/jasongil/.docker/run/docker.sock`. No Docker container was started or modified.
- No Colima, Lima, Podman, Multipass, QEMU, PostgreSQL server/client, Redis server/client, Nginx, or Caddy binary was available.
- The repository already contains its appliance Compose, deterministic load-test override, pinned Dockerfile, Nginx config, and CI PostgreSQL 16/Redis 7 integration services. A narrowly scoped overlay and command harness are added under `scripts/phase6/`; only `docker compose config` can be validated on this host.
- PostgreSQL migrations/backup/restore, Redis distribution/TTL/restart/outage, proxy SSE and HTTPS, Linux PDF resource limits, installation/recovery, and target-device acceptance remain **BLOCKED**.
- Live AI benchmark is **NOT RUN** because no provider, credential, cost limit, or dataset authorization was configured. This was not treated as a test failure or synthetic success.
- Full Playwright skip count is 35 expected project/device exclusions. The four visually tagged checks were run separately and passed; the combined browser result is 279 passed, 35 skipped.

## Persistent-state and cleanup evidence

Both full pytest sessions' explicit safeguard reported the same database size, modification time, and SHA-256 before and after; journal/WAL sidecars remained absent. Playwright used a newly created temporary state path. It regenerated one tracked control-inventory report and four screenshots; all five were restored byte-for-byte from the starting `HEAD`. Final status contains only the nine requested Phase 6 documents and two isolated harness files.
