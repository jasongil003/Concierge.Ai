# ECC Phase 6 Findings

## Scope and evidence boundary

- Candidate checkout: branch `test/phase6-infrastructure-acceptance`, HEAD `49b9575b705987fc961bb6380be502b5b549d809` (`admin`). This Phase 6 work is uncommitted; no final commit SHA exists.
- The prompt-supplied baseline `4fcbc38361e3e45864ae8a4501536526fb0c9af6` is not present in the local object database. The checked-out commit is the local tip of `fix/intelligent-ui-v2-phase5-stabilization` and its local tracking ref.
- The local `origin/main` ref is `6fd9d2309f28137a2ab3823ca99794656998b5d8`; remote refs and Actions could not be refreshed because DNS lookup for `github.com` fails. This is not proof of current GitHub state.
- Host: macOS Apple Silicon, Python 3.12.14 and 3.11.16, Node 26.7.0. Docker CLI/Compose are installed; the Docker daemon socket is absent. No local Linux VM runtime, PostgreSQL, Redis, Nginx, Gitleaks, or Trivy executable was found.
- No production environment, guest data, real provider credential, or external AI endpoint was accessed. The test suites use isolated temporary databases; persistent `state/concierge.db` was unchanged.

## Register

| ID | Severity | Root cause / current implementation | Fresh Phase 6 verification | Remaining risk | Status |
| --- | --- | --- | --- | --- | --- |
| `ECC-HIST-001` | Medium | Transcript ciphertext is versioned and supports a multi-key ring and resumable, batched rotation. | Full local suites pass; prior focused local rotation/backup tests are not a substitute for this phase's off-host restore. | Separate key escrow, interrupted PostgreSQL rotation, and recovery on a new host have not run. | **FIXED-UNVERIFIED** operationally |
| `FILE-DOS-01` | Medium | PDF extraction is isolated, bounded, supervised, and configures Linux `RLIMIT_AS`/`RLIMIT_CPU`; the macOS path is sampled parent supervision. | Full backend suites pass. No Linux worker/container was available for a Phase 6 resource run. | Linux hard limits, RSS, kill/reap, and cleanup remain unverified for this candidate. | **FIXED-UNVERIFIED** |
| `ECC-OPS-001` | Medium | Install, upgrade, service, proxy, rollback, and recovery runbooks exist; Compose/systemd definitions are present. | Fresh local backend/browser checks do not exercise installation or service lifecycle. Phase 6 scoped Compose harness added but not started. | Linux target, persistent-volume behavior, clean/upgrade install, and recovery are unverified. | **BLOCKED** |
| `ECC-PERF-001` | Medium | Existing SQLite/ASGI microbenchmarks do not establish deployment or provider capacity. | A fresh local sample is recorded in `PHASE6_PERFORMANCE.md`; it uses synthetic SQLite and in-process requests only. | No representative hardware, sustained concurrency, proxy, Redis/PostgreSQL contention, or capacity proof. | **BLOCKED** |
| `DB-INT-001` | Medium | PostgreSQL and Redis adapters exist; CI defines PostgreSQL 16/Redis 7 service integration. SQLite is the appliance default. | Both full local Python suites pass; service-gated cases skip without service URLs. No Docker daemon/server binaries were available. | Migrations, transaction contention, real Redis TTL/worker sharing/restart, DB backup/restore, and outage recovery remain unverified here. | **BLOCKED** |
| `AI-LIVE-001` | Medium | Provider routing and a 100-case synthetic benchmark exist. | No provider request was made. No authorized test credential, provider budget, or dataset-use authorization was supplied. | Model correctness, hallucination, injection, multilingual quality, tool safety, and live stream timing are unknown. | **BLOCKED** |
| `ECC-UI-001` | Low | SSE route/client cancellation are covered in app tests; proxy buffering and transport behavior require a real proxy path. | Fresh Playwright evidence is in `ECC_PHASE6_TEST_RESULTS.md`; no container proxy was started. | Proxy/TCP first-event timing, buffering, idle timeout, cancellation, and TLS are not accepted. | **BLOCKED** at proxy |
| `ECC-UI-002` | Low | Intelligent UI has a global kill switch and per-property settings; global default is disabled. | Full local backend and nonvisual browser suites exercise UI/rollback behavior. | Multi-replica propagation and rollback under deployment are unverified. | **FIXED-VERIFIED** locally |
| `ECC-UI-003` | Low | Restaurant choices are presentation/selection and do not create an unapproved reservation. | Full backend/browser suites pass. | Any future reservation integration requires its own authorization and acceptance. | **FIXED-VERIFIED** for current scope |
| `ECC-UI-004` | Low | Facility content is property scoped and depends on configured property data. | Full backend/browser suites pass. | Real property content/integrations were not supplied or tested. | **FIXED-VERIFIED** for current scope |
| `ECC-UI-005` | Low | Facility location is derived from configured location/map data rather than inferred from service status. | Full backend/browser suites pass. | No target property dataset was used. | **FIXED-VERIFIED** locally |
| `ECC-UI-006` | Low | Delayed chat rerender previously discarded expanded restaurant detail state. Phase 5 persists expansion and restores focus. | Current nonvisual Playwright run includes the delayed-response regression; the complete browser result is 279 passed, 35 expected skips, 0 failed. | Physical mobile and assistive-technology behavior remains unverified. | **FIXED-VERIFIED** locally |
| `ECC-SES-001` | Historical High | Guest activity renewal must persist expiry and keep cookie/server expiry aligned while refusing expired/revoked tokens. | Full local suites pass; PostgreSQL concurrency is unavailable here. | Cross-worker renewal behavior against PostgreSQL remains unverified. | **FIXED-UNVERIFIED** for multi-worker DB |
| `OPS-021` | Low | Guest breakfast content must come from the configured property's data. | Full backend/browser suites pass. | No live provider grounding acceptance. | **FIXED-VERIFIED** locally |

## Severity summary

No new confirmed Critical or High issue was found in the checks completed. The historical High guest-session issue has local regression coverage, but no PostgreSQL multi-worker verification was possible. Medium operational, database/cache, live AI, PDF/Linux, and capacity gates remain open or blocked; they are not closed by SQLite tests.

## Security review observations

The acceptance overlay reuses the existing application image and proxy. Its synthetic staging configuration passed the app's production-safety validator; it places PostgreSQL and Redis on an internal backend network, publishes only their disposable test ports to `127.0.0.1`, binds the proxy to loopback, generates fresh local credentials under a mode-`0700` temporary directory, disables background workers/local AI, and keeps the Intelligent UI global kill switch off. Cleanup names one source-SHA-scoped Compose project and removes only its project resources and labeled volumes. The overlay was not executed because the Docker daemon is unavailable.
