# On-Prem Deployment

The container's backup tools default to PostgreSQL major 16, matching the tested
PostgreSQL 16 service. They are installed from the PostgreSQL project's signed
[Debian package repository](https://www.postgresql.org/download/linux/debian/).
For a different server major, rebuild with `--build-arg POSTGRES_CLIENT_MAJOR=<major>`
and repeat the actual dump/restore drill. A newer client is not proof that a
dump restores to an older server: the audit reproduced a client-17/server-16
failure on `SET transaction_timeout`. Appliance archives use authenticated
AES-256-GCM encryption with the independent 32-byte
`CONCIERGE_BACKUP_ENCRYPTION_KEY`; installers generate it and operators must
escrow it separately from the archive. Off-host replication, independent key
retrieval, and clean-target recovery remain deployment acceptance requirements.

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
the source virtual environment is installed. Unauthenticated
`GET /health/version` returns only `status` and the semantic `version`.
`/health/live` means the process answers; `/health/ready` means its database
connection/schema and required upload storage pass readiness. Authenticated
Platform Admins can request the richer, sanitized
`GET /api/admin/system/diagnostics` report. It uses the existing
`system.configure` permission and reports database, Redis, storage, proxy,
uptime, backup/update, and provider status without returning credentials or
connection strings. Global `GET /health/details` is also restricted to
Platform Admins.

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
r