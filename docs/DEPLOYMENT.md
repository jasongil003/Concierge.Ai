# On-Prem Deployment

For appliance installation on Ubuntu Server or an Apple Silicon Mac mini, follow
the [Appliance Installation](APPLIANCE_INSTALLATION.md) guide. That guide covers
machine services, backup/recovery, releases, local AI, and the mandatory real
reboot acceptance procedure. Appliance support remains **incomplete until the
reboot acceptance test has passed on each target platform**.

This page retains the manual development and lab setup instructions below.

## Supported modes and diagnosis

Concierge.AI supports these modes:

| Mode | Runtime | Default listener | Persistent state |
| --- | --- | --- | --- |
| `source` | Python from a Git checkout; optional systemd/LaunchAgent service | `127.0.0.1:8080` | `<checkout>/state` unless `.env` selects another path |
| `docker-dev` | Development Docker Compose project | `127.0.0.1:8081` on the host | Checkout-specific Compose volume mounted at `/state` |
| `appliance` | Ubuntu Docker Compose under systemd, or macOS Python under launchd | `127.0.0.1:8080` | `/var/lib/concierge` or `/Library/Application Support/Concierge.AI` |

One runtime should own a Concierge installation's listening port and state. Do
not run Docker development, source/systemd, and appliance deployments against
the same port or database. Their default state locations are separate. If you
customize a database path, keep it exclusive to one deployment mode unless you
have a tested shared-state upgrade plan.

Start troubleshooting with:

```bash
concierge doctor
```

The read-only report shows active runtime/version/build identity, health, port
owner, service state, database type and schema revision, and state-directory
access. It does not print environment secrets or database contents.
`concierge status` prints a concise summary and can run from a checkout before
the source virtual environment is installed. `GET /health/version` provides
sanitized version, commit, build date, deployment mode, profile, Python version,
and schema revision. `/health/live` means the process answers; `/health/ready`
means its database connection/schema and required upload storage pass readiness.
Authenticated Super Admins can request the richer, sanitized
`GET /api/admin/system/diagnostics` report. It uses the existing
`system.configure` permission and reports database, Redis, storage, proxy,
uptime, backup/update, and provider status without returning credentials or
connection strings.

Development Compose is loopback-only and uses its own host port and named
volume:

```bash
./deploy/docker-compose.sh dev up --build
```

Open `http://127.0.0.1:8081`. For an intentional trusted-LAN test, bind the
development listener explicitly:

```bash
CONCIERGE_DEV_BIND_HOST=0.0.0.0 ./deploy/docker-compose.sh dev up --build
```

This exposes unencrypted development HTTP to reachable interfaces; it does not
prove Internet reachability and must not be used as a public deployment.

If diagnosis reports a port conflict, inspect the named process/container and
service before deciding which runtime to change. Installers refuse conflicting
source/appliance modes and never terminate the port owner. On Ubuntu,
`concierge.service` supervises the appliance Compose project; it is the same
runtime, not a second API. The development Compose state volume remains separate
from the appliance volume.

An older SQLite database without Concierge's schema marker is upgraded through
the stores' idempotent, additive compatibility migrations during application
initialization. Existing records are retained. After all store initializers
succeed, the app records the current schema revision. A newer recorded revision
causes startup to fail with a compatibility message; the database is opened
read-only for that comparison. PostgreSQL startup/readiness checks the Alembic
revision. Migration failures stop candidate startup; the installer does not
reset a database.

Appliance installs and updates serialize on `/opt/concierge/.deployment.lock`.
The OS lock is released when its owner exits, so stale lock-file contents do
not block the next operation. A busy operation reports its PID and start time.
Successful installs/updates write sanitized `deployment.json` metadata under
their state directory. Backup archives also carry version, commit, schema
revision, deployment mode, database type, and checksums without environment
credentials.

## Minimum prototype

You need:

- ANTlabs lab gateway or guest network
- one computer for Concierge.Ai
- Ollama installed on the AI host
- Python 3.11–3.14 (3.12+ preferred) or Docker
- a local 4B-class model

A domain and SSL certificate are not required for the first LAN test.

## Option A: run with Python

```bash
git clone https://github.com/jasongil003/Concierge.Ai.git
cd Concierge.Ai
git checkout main

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# For a manual run, set CREDENTIAL_ENCRYPTION_SECRET to a random value of at
# least 32 characters. The source installer generates and persists it for you.
ollama pull qwen3:4b
ollama serve

./concierge serve
```

Open:

```text
http://localhost:8080
```

Health check:

```text
http://localhost:8080/health
```

## Option B: application in Docker, Ollama on host

```bash
cp .env.example .env
# Add unique production secrets and configure ANTlabs browser handoff first.
./deploy/docker-compose.sh appliance up --build
```

Before starting a production Compose profile copied from `.env.example`, replace
the local bootstrap password with a unique value of at least 12 characters and
restrict access to `.env`. The managed appliance installer instead prompts for
a hidden, confirmed administrator password and does not print it. Keep the
management interface restricted to the configured trusted administrator
networks.
The production Compose profile fails closed until `.env` contains a valid
`CREDENTIAL_ENCRYPTION_SECRET`, `METRICS_TOKEN`,
`CANONICAL_HOSTS`, `PUBLIC_BASE_URL`, and a restrictive `ADMIN_ALLOWED_CIDRS`.
The Compose profile preserves an explicitly configured bootstrap account. The
example `.env` retains its local development bootstrap value for compatibility;
it must not be used for a production installation.
Set `ANTLABS_MODE=browser_handoff` and configure `ANTLABS_AUTH_URL` as
`https://<sg5-host>/login/main.ant?c=proc` before starting it. The live adapter
uses the SG5 built-in processor; its connection check verifies reachability, not
guest authentication or Internet access. Complete the guest-device validation
in `docs/ANTLABS_INTEGRATION.md` before production. The example's `mock` mode is
for local development only.

On a clean installation, the database starts without a property profile.
Sign in with the bootstrap administrator and create the first property from the
Admin onboarding screen. Add its name, timezone, and address there, then
configure guest-facing content and services separately. No property JSON file
is loaded during startup. `PROPERTY_ID` is optional and can identify the
configured property in a single-property deployment; leave it blank when
property routing is based on each property's domain. Do not reuse a development
database volume for production: stored property data survives image rebuilds.

New properties start without hotel-specific content. Configure rooms,
facilities, dining, services, policies, and knowledge from information verified
by the property. The application does not provide an active template library;
future templates should require explicit administrator selection, preview,
confirmation, and copying into property-scoped editable records.

Upgrades do not automatically remove existing service catalog rows. This
preserves administrator-created data, including rows whose names resemble the
former starter catalog. Review legacy departments and services in the property
admin UI and remove any confirmed unused records there. The upgrade removes
only the obsolete seed-tracking metadata table; it does not delete catalog or
other property content.

This on-prem profile runs one Concierge API instance and stores its database at
`/state/concierge.db` inside the `concierge-state` Docker volume. It does not
start a database container: `DATABASE_URL` is intentionally blank so SQLite
remains the active database. With Redis unconfigured, request limits use the
shared SQLite limiter. Keep the single API worker/instance for this SQLite
profile; evaluate a separate database deployment before increasing concurrent
replicas. Ollama must already be running on the host.

The compose configuration points the container at `host.docker.internal:11434`.
It binds its HTTP listener to `127.0.0.1:8080`; it does not publish an Internet
facing HTTP port or provide TLS itself. Put a trusted TLS reverse proxy in front
of that loopback listener. It must replace `X-Forwarded-For` and set
`X-Forwarded-Proto` from the actual client connection. Set
`FORWARDED_ALLOW_IPS` to the exact proxy addresses for the initial
Management Access configuration, including the Compose Nginx address
(`172.29.0.2`). Add the actual application-facing proxy to Management Access →
Trusted Management Proxy Ranges, and configure Guest Access proxy ranges
separately. The app keeps the socket peer intact and trusts forwarding headers
only when that peer matches the corresponding saved proxy ranges. Do not set
`FORWARDED_ALLOW_IPS=*`.

List every public guest/admin hostname in `CANONICAL_HOSTS`, and set
`PUBLIC_BASE_URL` to an HTTPS origin using one of those hostnames. The app
rejects other Host values, refuses non-HTTPS application traffic in production
and staging, restricts Admin routes to `ADMIN_ALLOWED_CIDRS`, and disables
`/docs`, `/redoc`, and `/openapi.json` in those environments. Health probes on
loopback remain available to Docker.

## First ANTlabs lab test

For local development only, keep:

```env
ANTLABS_MODE=mock
```

Then verify:

1. a phone on the guest VLAN can reach the Concierge server before authentication
2. normal Internet access is still blocked
3. Concierge UI loads
4. hotel FAQ fast paths work
5. local model responses work
6. the temporary session expires after inactivity

Only after those steps should the gateway authentication handoff be enabled.

## Production-like pilot

Recommended next step:

```text
concierge.example.com
        |
        | internal DNS
        v
10.x.x.x local Concierge server
```

Add:

- valid HTTPS certificate
- internal DNS
- ANTlabs HTTPS walled-garden rule
- dedicated service VLAN
- firewall policy
- reverse proxy
- persistent database
- monitoring
- log retention policy
- backup/restore procedure

## HTTPS

For the lab, HTTP is acceptable.

For a guest pilot, use a trusted HTTPS certificate. Do not rely on a self-signed certificate on guest devices. The development profile and direct Python command are for an isolated LAN only; the production profile requires a correctly configured external TLS proxy.

## Model sizing

Start small:

```env
OLLAMA_MODEL=qwen3:4b
MAX_OUTPUT_TOKENS=160
OLLAMA_THINK=false
```

Then benchmark:

- time to first token
- tokens per second
- 5 concurrent requests
- 10 concurrent requests
- 20 concurrent requests
- CPU/GPU utilization
- memory pressure
- queue time

Do not select a larger model until measured answer quality requires it.

## Security note

The development profile is bound to loopback, uses mock guest authentication,
and is not a production configuration. Do not bind the development app to a
public or guest-facing interface: it has no TLS and uses a development cookie
policy. Production startup rejects mock ANTlabs mode, default credentials,
insecure cookies, and unsafe property-selection settings.

Terminate TLS at a trusted reverse proxy and configure the hotel firewall,
guest VLAN, canonical hostnames, Admin source CIDRs, trusted proxy addresses,
and ANTlabs walled-garden policy before a guest pilot. The included Compose
listener is loopback-only. Do not expose the app or its HTTP proxy directly to
the public Internet or connect it to production PMS data until the remaining
security milestones in the roadmap are complete.
