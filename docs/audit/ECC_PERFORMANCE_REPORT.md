# ECC performance and resilience report

**Audit date:** 2026-10-14 (Asia/Manila)  
**Starting commit:** `82f9df2bafb4b3a632912762364fd6c7dff4a532`  
**Test host:** Darwin arm64, Python 3.11.16; local development machine.  
**Capacity verdict:** The target of 30,000 concurrent guests is **unverified**.

## Measurements made in this audit

All test data and SQLite files were created in temporary directories. These are short diagnostic samples, not deployment or AI load tests. The audit's backend and browser checks were also active on this host, so the timings include possible local contention and should not be used as a reproducible performance baseline.

`.venv/bin/python scripts/master_audit_http_sample.py` launched one Uvicorn worker on a disposable loopback port. Each stage issued 100 requests split between `/` and `/health/live`. All 300 returned HTTP 200. The script then restarted the worker and confirmed health. The listed workers are **client request threads**, not application processes or concurrent guest sessions.

| Client threads | Requests | Error rate | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | End RSS (MiB) | CPU seconds in stage |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 100 | 0% | 277.41 | 4.659 | 7.117 | 7.652 | 118.80 | 0.323 |
| 5 | 100 | 0% | 243.20 | 18.851 | 31.570 | 57.252 | 119.73 | 0.379 |
| 10 | 100 | 0% | 261.56 | 37.479 | 54.634 | 58.147 | 122.48 | 0.368 |

`.venv/bin/python scripts/phase4_performance_sample.py` used in-process FastAPI `TestClient` and temporary SQLite. Each operation had 101 timed iterations after warm-up:

| Operation | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: |
| Guest shell | 6.508 | 8.904 | 11.269 |
| Liveness endpoint | 0.834 | 1.376 | 1.572 |
| Encrypted transcript write | 1.049 | 1.857 | 2.829 |
| Encrypted transcript read | 0.699 | 0.895 | 4.957 |

That process used 0.956 CPU seconds during the sample. RSS rose from 110.8 to 128.3 MiB while the test initialized and ran. This short one-process change is **not** a memory-leak measurement. Neither sample exercised guest authentication, full chat, streaming, AI inference, the reverse proxy, PostgreSQL, Redis, or a real guest network.

## Architecture and limits found in source

- The production Compose profile intentionally starts **one Uvicorn worker** with SQLite in a persistent volume and no Redis (`docker-compose.yml:20-23`, `docker-compose.yml:37-43`). Its proxy publishes loopback HTTP only (`docker-compose.yml:51-62`). This is an appliance MVP topology, not a measured multi-node 30,000-connection topology.
- A separate PostgreSQL adapter has finite pool settings: default 8 connections plus 4 overflow at application configuration (`app/config.py:78-83`), a 5-second pool wait, connection pre-ping, and database timeouts (`app/database.py:99-110`). The pool is per worker. Actual database connection capacity and contention under load were not measured here.
- AI provider concurrency defaults to eight, with bounded queue capacity 32 and a 1.5-second queue wait (`app/config.py:136-143`). Provider slots and optional Redis-backed coordination appear in `app/ai_providers.py:1093-1176`; their operational behavior across deployed replicas needs a dedicated load test.
- Metrics include active requests, request queue depth, provider queue wait, and PostgreSQL pool use (`app/metrics.py`, `loadtest/run_stages.py`). The existing load runner records latency, throughput, errors, CPU, RSS, queue, and pool samples. Defined stages reach 10,000 virtual guests at most (`docs/LOAD_TESTING.md:3-20`). These are test definitions, not passed stages.
- A local process restart returned healthy in the 300-request shell/health sample. That result does not verify session recovery, in-flight stream continuity, service request durability, automatic appliance recovery, or off-host disaster recovery.

## Staged acceptance work

1. Provision a disposable representative deployment with PostgreSQL, Redis, a trusted TLS proxy, deterministic mock AI, synthetic properties, and a separate load injector. Record revision, instance sizes, pool settings, database limits, network, and dataset size.
2. Run the existing 10-user smoke, then 50, 100, 250, 500, and 1,000-user controlled stages. Exercise session start/resume, chat, dining, service request idempotency, and administrator reads. Capture p50/p95/p99, throughput, HTTP and timeout error rate, CPU, RSS growth, pool utilization, queue depths, and provider wait. Stop on the first failed gate.
3. On dedicated infrastructure only, run 2,500, 5,000, and 10,000-user stages, plus spike and soak profiles. Test both mock and separately approved real provider capacity. Induce database, Redis, provider, and worker failure in an isolated environment and verify recovery and no false request confirmations.
4. Define a 30,000-connection workload model, including idle versus active chat share, message rate, stream lifetime, retention, and SLO. Extend the injector and infrastructure only after lower stages pass. Measure 30,000 on the intended topology; do not extrapolate the local shell sample to that target.

**Open acceptance dependencies:** representative hardware, PostgreSQL/Redis service runs, proxy and network topology, real AI provider quotas, long-duration soak, backup/key recovery rehearsal, and target-host reboot validation. Docker runtime was unavailable on this host, so container and database service acceptance was not repeated in this audit.
