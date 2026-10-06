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

The load Compose profile is an overlay on `docker-compose.yml`. Use a unique Compose project name for every run. Compose scopes networks and the persistent volume to that project. The overlay attaches the API (`concierge`) to the project frontend and to a dedicated internal `loadtest` network; `mock-ai` joins only `loadtest`. The proxy and API share the project frontend, which is also marked internal in this overlay. The load profile removes the base host-gateway mapping and keeps the proxy published on loopback, using `LOADTEST_PORT` (default `18080`). No production service is attached to either project network and the containers have no external network egress.

The API uses the deterministic OpenAI-compatible mock endpoint, disables background workers, and writes to the project-scoped SQLite volume. This Compose profile does not define PostgreSQL or Redis services. Locust runs on the host; there is no injector image. The Concierge and mock-AI images are built locally from Dockerfiles whose Python base images are digest-pinned. The proxy's Nginx image is pinned by digest. The profile does not pull a PostgreSQL, Redis, or injector image.

Use a disposable host with Docker Compose v2.24 or later (the overlay uses `!reset` and `!override`). Build a temporary env file containing synthetic-only values, then validate the fully merged topology before starting it:

```bash
load_state="$(mktemp -d "${TMPDIR:-/tmp}/concierge-load.XXXXXX")"
cat > "$load_state/safe.env" <<EOF
CONCIERGE_CONFIG_FILE=$load_state/safe.env
CONCIERGE_BACKUP_DIR=$load_state/backups
CONCIERGE_VERSION=local
LOADTEST_PORT=18080
ADMIN_BOOTSTRAP_USERNAME=loadtest-admin
ADMIN_BOOTSTRAP_PASSWORD=LoadtestOnly-Admin-123!
CREDENTIAL_ENCRYPTION_SECRET=LoadtestOnly-Encryption-Secret-1234567890
METRICS_TOKEN=LoadtestOnly-Metrics-Token-1234567890
CANONICAL_HOSTS=localhost
PUBLIC_BASE_URL=https://localhost
ADMIN_ALLOWED_CIDRS=127.0.0.1/32
ANTLABS_MODE=mock
EOF
project="concierge-loadtest-$(id -u)-$$"
docker compose --project-name "$project" --env-file "$load_state/safe.env" \
  -f docker-compose.yml -f docker-compose.load.yml config
```

Do not put hotel or production credentials in this file. After review, start the isolated profile on a host where port 18080 is free:

```bash
docker compose --project-name "$project" --env-file "$load_state/safe.env" \
  -f docker-compose.yml -f docker-compose.load.yml up --build -d
```

Install Locust with `python -m pip install -r loadtest/requirements.txt`, provision a disposable property and synthetic guest identities, then run:

```bash
export LOADTEST_BASE_URL=http://127.0.0.1:18080
export LOADTEST_METRICS_TOKEN='<test-only metrics token>'
export PROPERTY_ID='<disposable test property id>'
export LOADTEST_CONFIRMATION=YES
python loadtest/run_stages.py
```

Stop the stack and remove only its disposable Compose project and temporary env directory when finished. Never reuse the project name or its volume for a hotel deployment.

For dedicated infrastructure only, add `LOADTEST_DEDICATED_INFRASTRUCTURE=YES` and select `--profile high-scale`, `--profile spike`, or `--profile soak`. The optional soak can be sized with `LOADTEST_SOAK_USERS=500` and `LOADTEST_SOAK_DURATION=30m` (or higher within the documented limits).

## Starting acceptance thresholds

Defaults live in `loadtest/profiles.json` and can be overridden with `LOADTEST_MAX_ERROR_RATE_PERCENT`, `LOADTEST_MAX_P95_LATENCY_MS`, `LOADTEST_MAX_TIMEOUT_RATE_PERCENT`, and `LOADTEST_MAX_RSS_GROWTH_MB`. Starting targets are under 1% request failures, p95 at or below 1,000 ms, zero timeouts, RSS growth at or below 512 MB per stage, no PostgreSQL pool exhaustion, Redis healthy when configured, and no worker failures. A stage is reported as accepted only when all measured thresholds pass. Tune these against the property's actual service objective before using them as release gates.

Passing a profile covers only the tested revision, workload, and infrastructure. It does not prove general production capacity, support for 30,000 concurrent users, absence of memory growth in a longer run, or behavior with live property hardware and provider integrations.
