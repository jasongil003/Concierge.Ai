# Load testing

The Locust framework separates a short **smoke test**, progressive **load test** stages, an explicitly selected **stress/spike test**, and an optional **soak test**. Profile definitions are not capacity claims. The largest defined stage is 10,000 virtual guests; 30,000-user capacity is **not verified**.

## Profiles

- `controlled`: 10, 50, 100, 250, 500, and 1,000 users, one minute per stage.
- `high-scale`: 2,500, 5,000, and 10,000 users. Runs only when explicitly selected and the operator sets `LOADTEST_DEDICATED_INFRASTRUCTURE=YES`.
- `spike`: warm up at 100 users, then raise to 5,000 users and hold for five minutes. Requires dedicated-infrastructure confirmation.
- `soak`: defaults to 500 users for 30 minutes. `LOADTEST_SOAK_USERS` can be 500–1,000 and `LOADTEST_SOAK_DURATION` must be at least 30 minutes (for example, `60m`). Requires dedicated-infrastructure confirmation. This profile is opt-in and never runs in normal CI.

All runs also require `LOADTEST_CONFIRMATION=YES` because guest traffic creates an idempotent service request per virtual guest. Never point it at production. The runner refuses high-scale, spike, and soak runs without the dedicated-infrastructure confirmation, so the normal command only uses controlled stages.

## Workloads and collected evidence

Guest workflows cover the landing page, session start/resume, assistant request, restaurant listing and menu retrieval, service request creation, and optional staff escalation. Set `LOADTEST_STAFF_CONVERSATION_FLOW=true` for the small integration smoke. Set both `LOADTEST_ADMIN_USERNAME` and `LOADTEST_ADMIN_PASSWORD` to include the low-weight admin dashboard read user.

Each stage records requests/sec, average latency and p50/p95/p99, Locust failures and HTTP errors, timeout failures/rate, API-process CPU and RSS/memory, RSS growth, PostgreSQL pool checked-out/capacity/overflow peaks, Redis readiness, database/rate-limit/worker error counters, request queue depth, active requests, and AI-provider queue wait percentiles when available. PostgreSQL pool metrics are unavailable on SQLite, so a stage without measurable pool capacity is not reported as passing its pool acceptance check. The runner records the target readiness response and raw Locust CSV plus JSON summaries.

For representative results, run the injector separately from the application and database. Record the image revision, database and Redis versions, hardware, AI endpoint/model, injector location, and deployment configuration beside each result. A local run on the same laptop is diagnostic only.

## Run against an isolated installation

Install Locust with `python -m pip install -r loadtest/requirements.txt`, provision a disposable property and deterministic AI endpoint, then:

```bash
export LOADTEST_BASE_URL=http://127.0.0.1:8092
export LOADTEST_METRICS_TOKEN='<test-only metrics token>'
export PROPERTY_ID='<disposable test property id>'
export LOADTEST_CONFIRMATION=YES
python loadtest/run_stages.py
```

For dedicated infrastructure only, add `LOADTEST_DEDICATED_INFRASTRUCTURE=YES` and select `--profile high-scale`, `--profile spike`, or `--profile soak`. The optional soak can be sized with `LOADTEST_SOAK_USERS=500` and `LOADTEST_SOAK_DURATION=30m` (or higher within the documented limits).

## Starting acceptance thresholds

Defaults live in `loadtest/profiles.json` and can be overridden with `LOADTEST_MAX_ERROR_RATE_PERCENT`, `LOADTEST_MAX_P95_LATENCY_MS`, `LOADTEST_MAX_TIMEOUT_RATE_PERCENT`, and `LOADTEST_MAX_RSS_GROWTH_MB`. Starting targets are under 1% request failures, p95 at or below 1,000 ms, zero timeouts, RSS growth at or below 512 MB per stage, no PostgreSQL pool exhaustion, Redis healthy when configured, and no worker failures. A stage is reported as accepted only when all measured thresholds pass. Tune these against the property's actual service objective before using them as release gates.

Passing a profile covers only the tested revision, workload, and infrastructure. It does not prove general production capacity, support for 30,000 concurrent users, absence of memory growth in a longer run, or behavior with live property hardware and provider integrations.
