# On-Prem Deployment

## Minimum prototype

You need:

- ANTlabs lab gateway or guest network
- one computer for Concierge.Ai
- Ollama installed on the AI host
- Python 3.12+ or Docker
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
# Set a unique ADMIN_BOOTSTRAP_PASSWORD and generate CREDENTIAL_ENCRYPTION_SECRET
# with `openssl rand -hex 32` before the first run.
ollama pull qwen3:4b
ollama serve

uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-proxy-headers
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
docker compose up --build
```

The production Compose profile fails closed until `.env` contains a unique
`ADMIN_BOOTSTRAP_PASSWORD`, `CREDENTIAL_ENCRYPTION_SECRET`, `METRICS_TOKEN`,
`CANONICAL_HOSTS`, `PUBLIC_BASE_URL`, and a restrictive `ADMIN_ALLOWED_CIDRS`.
The application also refuses to start in development if
`ADMIN_BOOTSTRAP_PASSWORD` is blank or uses the former `ChangeMe123!` default.
Generate a unique password for each installation.
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

New properties receive an editable starter service catalog for Housekeeping,
Maintenance, Front Desk, and Bell Services. Review it for the hotel's actual
offerings; existing non-empty catalogs are preserved, and removed starter
items do not return on later restarts.

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
