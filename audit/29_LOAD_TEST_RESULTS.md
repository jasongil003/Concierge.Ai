# 29 — Load test results

Status: **OPEN**.

No production load measurements were run in this environment, so no p50/p95/p99, throughput, CPU, memory, or concurrency numbers are reported. Fabricated estimates are intentionally omitted.

The remediation replaced guest/admin/chat in-memory request counters with an atomic SQLite-backed limiter shared by processes on the same appliance. A regression test proves limits survive limiter instance recreation and remain property-scoped. This addresses enforcement consistency but is not a capacity benchmark.

Required next measurement pass: application-only mocked-AI runs at 10/50/100/500 concurrent guests; SQLite lock/error and WAL assessment; real-provider sampling under a strict low quota; and a separate Redis-compatible limiter exercise for multi-instance cloud topology.
