# Phase 6 Performance and Capacity

## Current evidence

The Phase 6 host has no Linux acceptance stack, PostgreSQL, Redis, or reverse proxy. The supported local performance sample uses in-process FastAPI `TestClient`, temporary SQLite, and synthetic records. It is useful as an application microbenchmark only. It cannot measure proxy streaming, provider latency, worker contention, PostgreSQL/Redis load, deployed CPU/RAM, or 30,000 concurrent-session capacity.

**Fresh Phase 6 sample:** `/tmp/phase5-venv/bin/python scripts/phase4_performance_sample.py`; CPython 3.12.14 on macOS Apple Silicon; 101 timed samples per operation after one warm-up. Synthetic data and temporary SQLite. Historical Phase 5 measurements are not used as the current baseline.

| Operation | Samples | p50 (ms) | p95 (ms) | p99 (ms) | Environment |
| --- | ---: | ---: | ---: | ---: | --- |
| Guest shell `GET /` | 101 | 5.255 | 5.926 | 6.458 | FastAPI `TestClient`, temporary SQLite |
| Liveness `GET /health/live` | 101 | 0.840 | 0.950 | 1.034 | FastAPI `TestClient`, temporary SQLite |
| Encrypted transcript write | 101 | 0.858 | 1.081 | 1.163 | Synthetic guest/property, temporary SQLite |
| Encrypted transcript retrieval | 101 | 0.632 | 0.729 | 4.158 | Synthetic guest/property, temporary SQLite |

The process used 0.759 CPU seconds for the sample; RSS was 109.9 MiB at start and 128.0 MiB at end. These are endpoint readings, not peak RSS. No provider, network proxy, Redis/PostgreSQL, or concurrent workload was involved.

## Capacity conclusion

No capacity claim is supported. Representative target hardware, concurrency, duration, resource saturation, failure rate, and recovery were not observed. ECC finding `ECC-PERF-001` remains **BLOCKED**. On a Linux acceptance host, first run a bounded low-concurrency test, record CPU/RAM and all percentile/error metrics, and increase only within an approved cap. Derive any capacity model from those measurements and state its uncertainty.
