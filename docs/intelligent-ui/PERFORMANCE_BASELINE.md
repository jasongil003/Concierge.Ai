# Phase 4 performance baseline

## Scope

This report separates local request-path measurements from provider, browser-network, and target-capacity acceptance. Previous Phase 3 in-process SQLite samples are historical evidence only: they covered 20 synthetic guest sessions, not a representative concurrent deployment.

## Phase 4 status

**ECC-PERF-001 remains BLOCKED for pilot capacity.** This macOS checkout has no configured authorized provider and no target proxy/database/cache/hardware. Therefore AI first-token/full-response latency, browser cold load, reverse-proxy timing, sustained concurrency, target CPU/memory, and error-rate SLOs were not measured. No 30,000-guest capacity claim is made.

The reproducible `.venv/bin/python scripts/phase4_performance_sample.py` run records 101 warm samples of in-process guest shell, liveness, encrypted transcript write, and encrypted retrieval on temporary SQLite. The current sample's guest shell p50/p95/p99 was 5.155/11.274/133.925 ms; the p99 outlier demonstrates why this local micro-sample cannot be treated as a deployment SLO. The rotation regression processes 240 synthetic transcript rows in seven batches of at most 37 cells and verifies idempotency. This is functional bounded-batch evidence, not a throughput or production-capacity benchmark.

## Required controlled-pilot measurements

Define SLOs with the pilot owner before load testing. Use the approved appliance image and proxy, synthetic sessions/property data, realistic response sizes, and a bounded non-destructive rate. Collect p50/p95/p99 with sufficient sample counts for guest page load, session creation, database query, encrypted history write/read, provider first token, first SSE delta, and full response. Also collect CPU, RSS, database pool utilization, provider concurrency/errors, request failures, and recovery after worker/provider restart.

Do not generate uncontrolled load or use production guest data. Record candidate SHA, exact runtime/hardware, sample counts, warm/cold conditions, and SLO result. If provider/proxy/hardware is unavailable, keep the finding BLOCKED.
