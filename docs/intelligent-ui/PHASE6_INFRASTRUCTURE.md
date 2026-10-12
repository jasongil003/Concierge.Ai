# Phase 6 Infrastructure

## Existing architecture reused

The appliance profile in `docker-compose.yml` builds the repository's Python 3.12 application image and pinned Nginx proxy, keeps the application on a private bridge, publishes only proxy HTTP on host loopback `127.0.0.1:8080`, and stores SQLite/uploads in a project-scoped volume. It intentionally runs one worker with SQLite. `docker-compose.load.yml` adds the deterministic mock AI for isolated load work. The CI workflow already pins PostgreSQL 16 and Redis 7 for integration tests.

`scripts/phase6/docker-compose.overlay.yml` composes with the existing appliance file; it does not create another application or proxy image. It uses the app's staging safety validation, adds PostgreSQL/Redis, connects them only to an internal backend network, disables background workers and local AI, and changes the proxy/database/cache host binds to loopback-only Phase 6 ports. The global Intelligent UI flag remains `false`. A disposable Postgres database and Redis AOF volume are labeled as Phase 6 resources and are removed only by the project-scoped `cleanup` command.

## Host result

**BLOCKED: runtime unavailable.** This host is macOS on Apple Silicon. Docker CLI and Compose are installed, but the selected `desktop-linux` context has no server at its Docker socket. No Colima/Lima/Podman/Multipass/QEMU runtime or native PostgreSQL, Redis, or Nginx service was found. The existing WSL option is not applicable to this macOS host. I did not start Docker Desktop because that could start or alter unrelated user containers. No Phase 6 container or service was started.

The overlay is prepared for the next provisioned Linux/Docker host. `acceptance.sh config` is a daemon-free Compose render check; it parses the rendered JSON and asserts that proxy/PostgreSQL/Redis publish only to `127.0.0.1`, the app and service networks are internal, and the global guest UI flag remains false. It passed with dummy unsafe environment overrides because the harness discards inherited config/secrets and fixes the bind address. `doctor` refused a supplied remote `DOCKER_HOST` without querying it. `start` permits only a local Unix-socket Docker context and was observed to stop before resource creation because the daemon is unavailable. This is infrastructure preparation, not infrastructure acceptance.

## Commands on a Linux acceptance host

Install repository requirements and Playwright/Chromium first, and use a disposable checkout with no production credentials. The script generates credentials privately in a mode-restricted temporary directory; it does not print them or read the project's `.env`.

```sh
PHASE6_PYTHON=/path/to/python3.12 scripts/phase6/acceptance.sh config
PHASE6_PYTHON=/path/to/python3.12 scripts/phase6/acceptance.sh start
scripts/phase6/acceptance.sh status
scripts/phase6/acceptance.sh health
PHASE6_PYTHON=/path/to/python3.12 scripts/phase6/acceptance.sh test
PHASE6_PYTHON=/path/to/python3.12 scripts/phase6/acceptance.sh browser
scripts/phase6/acceptance.sh logs
scripts/phase6/acceptance.sh stop redis
scripts/phase6/acceptance.sh restart redis
scripts/phase6/acceptance.sh stop postgres
scripts/phase6/acceptance.sh restart postgres
scripts/phase6/acceptance.sh restart
scripts/phase6/acceptance.sh stop
scripts/phase6/acceptance.sh cleanup
```

`test` first runs the regular suite with inherited database/cache URLs cleared, then applies Alembic and runs the service-gated integration files against only the generated loopback ports. PostgreSQL backup integration runs only when host `pg_dump` is PostgreSQL 16; otherwise its skip is printed. `browser` uses a separate temporary SQLite app server on port 8092. Change `PHASE6_HTTP_PORT`, `PHASE6_POSTGRES_PORT`, and `PHASE6_REDIS_PORT` before the first `start` if a local port is occupied; the selected ports are saved with the private runtime config. The script fails rather than stopping another listener.

Service-specific `stop`/`restart` commands are for the Redis/PostgreSQL outage and recovery checks. Record health before and after; do not mark recovery passed until dependent app behavior and test assertions are captured.

`cleanup` targets `concierge-phase6-<source SHA>` and removes only that Compose project's containers, network, and explicitly labeled volumes (including its synthetic app state). It never runs a global container/image/volume prune. Preserve sanitized evidence outside the app volume before cleanup. Never place production secrets or actual hotel data in this stack.

## Readiness interpretation

The prepared configuration and staging-mode validation are **IMPLEMENTED** and rendered/validated locally without making a service connection. PostgreSQL/Redis/proxy/application startup, guest/admin navigation through this overlay, host-only port reachability, restart behavior, and cleanup are **NOT TESTED** until run on a host with a functioning Linux container runtime. The existing full local Python/browser checks are recorded separately and do not change this status.
