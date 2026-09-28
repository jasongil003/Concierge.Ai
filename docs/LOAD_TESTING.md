# Controlled load testing

The repository defines gradual Locust stages at 10, 50, 100, 250, 500, and
1,000 virtual guests. These stages prepare measurements; they are not evidence
of a user-capacity guarantee.

## What the runner records

`python loadtest/run_stages.py` runs each stage for the duration in
`loadtest/profiles.json` and writes Locust CSV files plus one JSON report per
stage. It records:

- success rate and request throughput
- HTTP latency p50, p95, and p99
- Locust failures and HTTP error responses
- database errors and rate-limit events from the authenticated Prometheus endpoint
- mean and peak CPU, memory percentage, and RSS samples from the API process
- AI-provider concurrency-slot wait p50 and p95 from a Prometheus histogram

The runner samples API-process CPU and memory through the authenticated
Prometheus endpoint while Locust is active. For meaningful capacity results,
run the injector on a separate machine from the API. AI-provider queue
percentiles are bucket approximations from the configured Prometheus
histogram; a stage with no AI calls reports no percentile.

## Run against an isolated test installation

Use a disposable property, a deterministic AI endpoint, and an isolated
database/Redis namespace. The workload creates one idempotent service request
per virtual guest and may perform an optional admin retention write. It must
not target a production installation.

```bash
python -m pip install -r loadtest/requirements.txt
export LOADTEST_BASE_URL=http://127.0.0.1:8092
export LOADTEST_METRICS_TOKEN='<test-only metrics token>'
export PROPERTY_ID='<disposable test property id>'
export LOADTEST_CONFIRMATION=YES
python loadtest/run_stages.py
```

The metrics token must match `METRICS_TOKEN` in the test application. The
runner checks `/health/ready` and `/metrics` before starting. Store the output
directory with the run date, image revision, database/Redis versions, hardware,
AI endpoint/model, injector location, and configuration used. Preserve raw CSV
and JSON artifacts with any published capacity result.

The PostgreSQL/Redis CI job runs a separate short 10-user smoke test against a
deterministic local AI service. It checks that requests succeed; it is not a
scale test and should not be reported as capacity evidence.
