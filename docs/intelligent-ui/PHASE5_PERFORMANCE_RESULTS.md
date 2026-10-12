# Phase 5 performance results

## Local bounded sample

Command: `.venv/bin/python scripts/phase4_performance_sample.py`.

Environment: macOS Apple Silicon; CPython 3.11.16; Node v26.7.0 is not in the measured request path. FastAPI `TestClient`, temporary SQLite, synthetic data, in-process requests, 101 timed samples per operation. No live provider, browser networking, TLS/reverse proxy, Redis/PostgreSQL, or concurrent-session load was used.

| Operation | Samples | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Guest shell `GET /` | 101 | 5.277 | 6.175 | 6.561 |
| Liveness `GET /health/live` | 101 | 0.768 | 0.896 | 0.951 |
| Encrypted transcript write | 101 | 0.873 | 1.053 | 1.116 |
| Encrypted transcript retrieval | 101 | 0.633 | 0.752 | 4.261 |

The script reported 0.772 process CPU seconds for the complete sample. RSS was 109.2 MiB at sample start and 128.8 MiB at sample end; these are endpoint readings, not peak memory. Guest session creation, hotel/restaurant query under concurrency, streaming first token/full answer, confirmed action, and provider failure recovery were not measured by this script.

## Interpretation

This sample is a reproducible local request-path baseline only. It provides no deployment SLO, target hardware estimate, sustained-throughput evidence, or capacity claim. In particular, it does not justify support for 30,000 simultaneous guests.

## Controlled pilot measurement plan

Before running load, the pilot owner must set request-rate limits and SLOs. Use the candidate behind the intended proxy with synthetic properties and sessions, bounded ramp-up, and a rollback stop condition. Capture hardware/runtime, database/cache/provider versions, cold/warm conditions, concurrency and sample count. Measure p50/p95/p99 for guest page load, session creation, hotel facts, restaurants, history read/write, first SSE event, complete answer and signed-confirmed action. Record error and retry rates, CPU, peak RSS, connection-pool pressure and provider concurrency. Interrupt provider/network/database safely and verify recovery and no duplicate service actions.
