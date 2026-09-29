# Load testing

The repository defines gradual Locust stages at 10, 50, 100, 250, 500, and
1,000 virtual guests, separate high-scale profiles at 5,000, 10,000, and
30,000 virtual guests, a 100-to-5,000-user spike, and a four-hour 5,000-user
soak. These are defined test profiles only. None of these targets is verified
production capacity.

## What the runner records

`python loadtest/run_stages.py` runs the progressive stages. Select another
profile with `--profile high-scale`, `--profile spike`, or `--profile soak`.
The high-scale option runs all three user targets in sequence. Each run writes
Locust CSV files and a JSON report. It records:

- success rate and request throughput
- HTTP latency p50, p95, and p99
- Locust failures and HTTP error responses
- database errors and rate-limit events from the authenticated Prometheus endpoint
- mean and peak CPU, memory percentage, and RSS samples from the API process
- AI-provider concurrency-slot wait p50 and p95 from a Prometheus histogram
- Locust failure count

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

Set `LOADTEST_STAFF_CONVERSATION_FLOW=true` for a small integration smoke with
at least one open restaurant. Each virtual guest checks the valid no-conversation
404, escalates once, and reads the active conversation successfully. Keep this
flow for integration smoke runs so property and IP escalation rate limits remain
representative.

```bash
python -m pip install -r loadtest/requirements.txt
export LOADTEST_BASE_URL=http://127.0.0.1:8092
export LOADTEST_METRICS_TOKEN='<test-only metrics token>'
export PROPERTY_ID='<disposable test property id>'
export LOADTEST_CONFIRMATION=YES
python loadtest/run_stages.py
```

Replace the last command with `python loadtest/run_stages.py --profile
high-scale`, `--profile spike`, or `--profile soak` when the test environment
and injector are sized for that profile. The spike holds 100 users for one
minute, raises the target to 5,000 users at 500 users per second, then holds
that target for five minutes. The soak holds 5,000 users for four hours after
spawning. Use an isolated, disposable environment for every profile.

The metrics token must match `METRICS_TOKEN` in the test application. The
runner checks `/health/ready` and `/metrics` before starting. Store the output
directory with the run date, image revision, database/Redis versions, hardware,
AI endpoint/model, injector location, and configuration used. Preserve raw CSV
and JSON artifacts with any published capacity result.

The PostgreSQL/Redis CI job runs a separate short 10-user smoke test against a
deterministic local AI service, including both staff-message conversation states.
It checks that requests succeed; it is not a scale test and should not be
reported as capacity evidence. Do not publish a
capacity claim until the corresponding profile has completed against
representative application, database, Redis, AI, and network infrastructure,
and its raw CSV and JSON artifacts are reviewed.
