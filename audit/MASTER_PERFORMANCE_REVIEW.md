# Master performance and resilience review

- Date: 2026-10-12–13, Asia/Manila.
- Baseline: `41c0ea1a7937035db6078cbb944f1e94f2fbad63`.
- Final tested code: see the candidate receipt in `MASTER_RELEASE_READINESS.md`; report commit is discoverable with `git log -1 -- audit/MASTER_PERFORMANCE_REVIEW.md`.
- Environment: Darwin arm64, CPython 3.11.16, temporary SQLite, one local Uvicorn worker. Docker Desktop Linux containers supplied isolated PostgreSQL 16, Redis, non-root app packaging and the staging proxy. Native host service binaries were unavailable.

## Fresh measurements

Commands: `.venv/bin/python scripts/phase4_performance_sample.py` and `.venv/bin/python scripts/master_audit_http_sample.py`. JSON is retained in [evidence](evidence/master-2026-10-12/). No provider or production endpoint was used.

Serial in-process sample: 101 observations per operation. Guest shell p50/p95/p99 = 5.596/7.785/10.559 ms; live health = 0.819/1.037/1.189 ms; encrypted transcript write = 0.958/1.113/2.331 ms; read = 0.675/0.830/4.521 ms. Process RSS increased from 108.5 to 128.3 MiB; CPU time 0.847 s. These are operation samples, not concurrent-user capacity.

Bounded real loopback HTTP sample alternates guest shell and live health, 100 requests per stage:

| HTTP worker threads | Requests | Failures | RPS | p50/p95/p99 ms | Server RSS MiB | Server CPU seconds |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 100 | 0 | 262.60 | 5.063/7.787/11.902 | 118.80 | 0.332 |
| 5 | 100 | 0 | 281.74 | 15.450/27.670/69.559 | 119.69 | 0.346 |
| 10 | 100 | 0 | 352.09 | 26.737/40.963/44.861 | 104.72 | 0.287 |

Health returned HTTP 200 after terminating and relaunching the owned app against its synthetic database. This verifies process restart readiness only; it does not verify lost requests, customer data recovery, database outage recovery or OS service persistence. The first unseeded harness run produced 50 failed shell requests; its JSON is retained. Adding the required synthetic property fixed the fixture, without changing application behavior.

## Remote baseline evidence

PR #52 CI run `38247953936`, tested merge `976184725c2212fc330e0b3ea3f7e11c6e556052` from head `d328484`: PostgreSQL/Redis integration passed (SQLite migration 1 test; adapter/backup/Redis suite 17 tests). A 10-user/25-second deterministic-AI Locust smoke logged 412 aggregate requests, zero failures, approximately 16.62 RPS; its CSV assertion used an earlier 399-request snapshot, also zero failures. Neither figure measures real AI throughput. [Retained excerpts](evidence/master-2026-10-12/github-postgres-redis-excerpts.log).

## Capacity decision and next work

30,000 concurrent users remain a target. Maximum fresh local HTTP concurrency was 10 worker threads on shell/health endpoints, with fewer than two seconds of measured stage traffic. No guest-session or AI capacity was established. Representative hardware sizing, sustained latency/error distributions, provider token throughput, queue saturation, PostgreSQL contention, Redis sharing, proxy streaming, representative outage/recovery and long stability remain unverified. Fresh bounded lab PostgreSQL/Redis interruptions, reconnection and process/container persistence passed as described below.

Run the existing confirmation-gated Locust stages on an isolated Linux target after migration/restore/proxy acceptance. Start at 10 users, collect request mix, p50/p95/p99, CPU/RSS, database/pool/queue errors, and provider waits; stop on failures or configured resource ceilings. Advance only when each previous stage meets documented acceptance. Do not extrapolate these short local samples to hotel capacity.

## Fresh bounded resilience acceptance

`scripts/docker_runtime_smoke.py` passed four phases: fresh build, production-settings validation, non-root writes/readiness and persisted records after recreation. `scripts/failure_recovery_smoke.py` passed seven phases including 16 service integration tests, app restart, PostgreSQL and Redis interruption (liveness 200/readiness 503), and reconnection with intact configuration. Actual PostgreSQL integration: 14 PASS including migration/indexes/backup restore; actual Redis checks: 4 PASS. Logs are in the security/master evidence directories. Initial failures and their credential-fixture/client-version corrections remain in the test ledger. These are controlled brief lab interruptions; no physical reboot, failover, sustained traffic or 30,000-user capacity was accepted.

Next actions: execute final-candidate hosted checks and representative Linux/hotel proxy acceptance, then a bounded authenticated guest/provider load and soak plan with explicit latency/error/resource ceilings. Hardware and paid authorized provider capacity are external dependencies; no third-party load was generated.

Final tested implementation commit: `ecfe3f42963896cd86a291450fa574a4c26b197f`. Reports/evidence are committed separately; their receipt is discoverable with `git log -1 -- audit/MASTER_PERFORMANCE_REVIEW.md`. All test results refer to these unchanged committed implementation bytes, including explicitly scoped container receipts and local skips.
