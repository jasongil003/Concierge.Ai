#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short=8 HEAD)"
PHASE6_PROJECT="concierge-phase6-${GIT_SHA}"
RUNTIME_PARENT="${TMPDIR:-/tmp}"
RUNTIME_DIR="$RUNTIME_PARENT/${PHASE6_PROJECT}-$(id -u)"
RUNTIME_ENV="$RUNTIME_DIR/runtime.env"
PHASE6_PYTHON="${PHASE6_PYTHON:-$(command -v python3.12 || printf '%s' "$REPO_ROOT/.venv/bin/python")}"
HTTP_BIND="127.0.0.1"
HTTP_PORT="${PHASE6_HTTP_PORT:-18082}"
POSTGRES_PORT="${PHASE6_POSTGRES_PORT:-55432}"
REDIS_PORT="${PHASE6_REDIS_PORT:-56379}"
unset \
  PHASE6_HTTP_BIND PHASE6_HTTP_PORT PHASE6_POSTGRES_PORT PHASE6_REDIS_PORT \
  CONCIERGE_CONFIG_FILE CONCIERGE_VERSION CONCIERGE_COMMIT CONCIERGE_BUILD_DATE \
  ADMIN_BOOTSTRAP_USERNAME ADMIN_BOOTSTRAP_PASSWORD CREDENTIAL_ENCRYPTION_SECRET \
  METRICS_TOKEN CANONICAL_HOSTS PUBLIC_BASE_URL ADMIN_ALLOWED_CIDRS FORWARDED_ALLOW_IPS \
  CONCIERGE_BACKUP_DIR

die() {
  printf 'phase6: %s\n' "$1" >&2
  exit 1
}

compose() {
  docker compose \
    --project-name "$PHASE6_PROJECT" \
    --project-directory "$REPO_ROOT" \
    --env-file "$RUNTIME_ENV" \
    --file "$REPO_ROOT/docker-compose.yml" \
    --file "$SCRIPT_DIR/docker-compose.overlay.yml" \
    "$@"
}

secure_runtime_dir() {
  python3 - "$RUNTIME_DIR" <<'PY'
import os
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
if path.is_symlink():
    raise SystemExit("phase6 runtime directory must not be a symlink")
if not path.exists():
    path.mkdir(mode=0o700, parents=True)
info = path.stat()
if info.st_uid != os.getuid():
    raise SystemExit("phase6 runtime directory is owned by another user")
if stat.S_IMODE(info.st_mode) & 0o077:
    raise SystemExit("phase6 runtime directory permissions must be owner-only")
PY
}

project_volumes_exist() {
  docker volume inspect "${PHASE6_PROJECT}_concierge-state" >/dev/null 2>&1 \
    || docker volume inspect "${PHASE6_PROJECT}_phase6-postgres-data" >/dev/null 2>&1 \
    || docker volume inspect "${PHASE6_PROJECT}_phase6-redis-data" >/dev/null 2>&1
}

local_docker_endpoint() {
  [[ -z "${DOCKER_HOST:-}" ]] || return 1
  local context endpoint
  context="$(docker context show 2>/dev/null)" || return 1
  endpoint="$(docker context inspect "$context" --format '{{ (index .Endpoints "docker").Host }}' 2>/dev/null)" || return 1
  [[ "$endpoint" == unix://* ]]
}

validate_port() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[0-9]{1,5}$ ]] || die "$name must be a port number from 1024 through 65535"
  (( 10#$value >= 1024 && 10#$value <= 65535 )) || die "$name must be a port number from 1024 through 65535"
}

load_runtime_ports() {
  local key value
  while IFS='=' read -r key value; do
    case "$key" in
      PHASE6_HTTP_PORT) HTTP_PORT="$value" ;;
      PHASE6_POSTGRES_PORT) POSTGRES_PORT="$value" ;;
      PHASE6_REDIS_PORT) REDIS_PORT="$value" ;;
    esac
  done < "$RUNTIME_ENV"
  validate_port PHASE6_HTTP_PORT "$HTTP_PORT"
  validate_port PHASE6_POSTGRES_PORT "$POSTGRES_PORT"
  validate_port PHASE6_REDIS_PORT "$REDIS_PORT"
}

ensure_runtime_env() {
  secure_runtime_dir
  if [[ -e "$RUNTIME_ENV" ]]; then
    [[ ! -L "$RUNTIME_ENV" && -f "$RUNTIME_ENV" ]] || die "runtime env must be a regular file"
    python3 - "$RUNTIME_ENV" <<'PY'
import os
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
info = path.stat()
if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
    raise SystemExit("phase6 runtime env must be owned by this user with owner-only permissions")
PY
    load_runtime_ports
    return
  fi
  if [[ "${1:-}" == "check-volumes" ]] && project_volumes_exist; then
    die "Phase 6 volumes exist but their generated runtime env is missing; recover the env file or run scoped cleanup"
  fi
  command -v openssl >/dev/null || die "openssl is required to generate disposable test credentials"
  local admin_password encryption_secret metrics_token tmp_env
  admin_password="$(openssl rand -hex 24)A!"
  encryption_secret="$(openssl rand -hex 32)"
  metrics_token="$(openssl rand -hex 32)"
  validate_port PHASE6_HTTP_PORT "$HTTP_PORT"
  validate_port PHASE6_POSTGRES_PORT "$POSTGRES_PORT"
  validate_port PHASE6_REDIS_PORT "$REDIS_PORT"
  tmp_env="$RUNTIME_ENV.tmp.$$"
  (umask 077; : > "$tmp_env")
  cat > "$tmp_env" <<EOF
CONCIERGE_CONFIG_FILE=$RUNTIME_ENV
CONCIERGE_VERSION=phase6-local
CONCIERGE_COMMIT=$GIT_SHA
CONCIERGE_BUILD_DATE=local
ADMIN_BOOTSTRAP_USERNAME=phase6-admin
ADMIN_BOOTSTRAP_PASSWORD=$admin_password
CREDENTIAL_ENCRYPTION_SECRET=$encryption_secret
METRICS_TOKEN=$metrics_token
CANONICAL_HOSTS=localhost,127.0.0.1
PUBLIC_BASE_URL=https://localhost
ADMIN_ALLOWED_CIDRS=127.0.0.1/32,::1/128
FORWARDED_ALLOW_IPS=172.29.0.2
CONCIERGE_BACKUP_DIR=$RUNTIME_DIR/backups
PHASE6_HTTP_BIND=$HTTP_BIND
PHASE6_HTTP_PORT=$HTTP_PORT
PHASE6_POSTGRES_PORT=$POSTGRES_PORT
PHASE6_REDIS_PORT=$REDIS_PORT
EOF
  chmod 600 "$tmp_env"
  mv "$tmp_env" "$RUNTIME_ENV"
  mkdir -p "$RUNTIME_DIR/backups"
  chmod 700 "$RUNTIME_DIR/backups"
  load_runtime_ports
}

require_runtime_env() {
  [[ -f "$RUNTIME_ENV" && ! -L "$RUNTIME_ENV" ]] || die "no Phase 6 runtime found; run 'start' first"
  ensure_runtime_env
}

require_docker_daemon() {
  command -v docker >/dev/null || die "Docker CLI is not installed"
  local_docker_endpoint || die "refusing a remote Docker context or DOCKER_HOST override; Phase 6 may use only the local Unix-socket daemon"
  docker info >/dev/null 2>&1 || die "Docker daemon is unavailable; no Phase 6 container resources were started"
}

check_port_available() {
  python3 - "$1" "$2" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.socket() as sock:
    sock.settimeout(0.25)
    if sock.connect_ex((host, port)) == 0:
        raise SystemExit(f"phase6 port {host}:{port} is already in use; choose another PHASE6_*_PORT")
PY
}

wait_for_services() {
  local attempt
  for ((attempt = 1; attempt <= 90; attempt++)); do
    if compose exec -T postgres pg_isready -U concierge -d concierge >/dev/null 2>&1 \
      && [[ "$(compose exec -T redis redis-cli ping 2>/dev/null | tr -d '\r')" == "PONG" ]]; then
      return 0
    fi
    sleep 2
  done
  compose ps >&2 || true
  die "PostgreSQL/Redis did not become healthy within 180 seconds; inspect scoped logs"
}

seed_synthetic_data() {
  compose run --rm --no-deps concierge python -c '
from app.config import settings
from app.hospitality import HospitalityStore
from app.properties import PropertyRecord, PropertyStore

property_id = "phase6-synthetic"
PropertyStore(settings.db_path).upsert(PropertyRecord(
    property_id=property_id,
    hotel_name="Phase 6 Synthetic Hotel",
    domain="localhost",
    timezone="UTC",
    address="100 Test Way",
))
hospitality = HospitalityStore(settings.db_path)
if not hospitality.guest_facilities(property_id)["restaurants"]:
    hospitality.create_restaurant(property_id, {
        "name": "Synthetic Garden Kitchen",
        "cuisine": "Test Dataset",
        "description": "Synthetic acceptance fixture; no real hotel data.",
    })
'
}

usage() {
  cat <<'EOF'
Usage: scripts/phase6/acceptance.sh COMMAND

Commands:
  config    Render and validate the isolated Compose configuration (no daemon needed)
  doctor    Report local runtime prerequisites without changing services
  start     Start the scoped Phase 6 stack, migrate its database, and seed synthetic data
  stop      Stop the Phase 6 stack or one service (concierge, proxy, postgres, redis)
  restart   Restart the Phase 6 stack or one service (for restart/failure recovery checks)
  status    Show Phase 6 service state
  health    Check loopback proxy, PostgreSQL, and Redis readiness
  test      Run the full Python suite, then PostgreSQL/Redis integration tests
  browser   Run nonvisual Playwright tests against a separate temporary SQLite app
  logs      Show the last 200 log lines from the Phase 6 stack or one service
  cleanup   Remove only this source-SHA-scoped Compose project and its labeled volumes

The stack binds the app proxy, PostgreSQL, and Redis to loopback only. It uses
synthetic data and freshly generated test credentials in a private temp folder.
Set PHASE6_HTTP_PORT, PHASE6_POSTGRES_PORT, or PHASE6_REDIS_PORT to change ports.
EOF
}

command_name="${1:-help}"
case "$command_name" in
  config)
    config_created_env=0
    if [[ ! -e "$RUNTIME_ENV" ]]; then config_created_env=1; fi
    ensure_runtime_env
    config_status=0
    {
      compose config --format json |
        PHASE6_EXPECT_HTTP_PORT="$HTTP_PORT" \
        PHASE6_EXPECT_POSTGRES_PORT="$POSTGRES_PORT" \
        PHASE6_EXPECT_REDIS_PORT="$REDIS_PORT" \
        python3 -c '
import json
import os
import sys

config = json.load(sys.stdin)
services = config["services"]
expected = {
    "proxy": ("80", os.environ["PHASE6_EXPECT_HTTP_PORT"]),
    "postgres": ("5432", os.environ["PHASE6_EXPECT_POSTGRES_PORT"]),
    "redis": ("6379", os.environ["PHASE6_EXPECT_REDIS_PORT"]),
}
for service, (target, published) in expected.items():
    ports = services[service].get("ports", [])
    assert len(ports) == 1, f"{service} must publish exactly one acceptance port"
    port = ports[0]
    assert port.get("host_ip") == "127.0.0.1", f"{service} port must bind to loopback"
    assert str(port.get("target")) == target and str(port.get("published")) == published
assert config["networks"]["frontend"].get("internal") is True
assert config["networks"]["backend"].get("internal") is True
assert config["networks"]["ingress"].get("internal", False) is False
assert set(services["proxy"]["networks"]) == {"frontend", "ingress"}
assert all("ingress" not in services[name]["networks"] for name in ("concierge", "postgres", "redis"))
assert "backend" in services["postgres"]["networks"]
assert "backend" in services["redis"]["networks"]
assert "frontend" not in services["postgres"]["networks"]
assert "frontend" not in services["redis"]["networks"]
assert set(services["concierge"]["networks"]) == {"frontend", "backend"}
assert not services["concierge"].get("ports")
environment = services["concierge"]["environment"]
assert environment["APP_ENVIRONMENT"] == "staging"
assert environment["LOCAL_AI_ENABLED"] == "false"
assert environment["INTELLIGENT_GUEST_UI_GLOBAL_ENABLED"] == "false"
print("Phase 6 Compose config valid: staging validation is enabled; ports are loopback-only; DB/cache networks are internal.")
'
    } || config_status=$?
    if (( config_created_env )); then
      rm -f -- "$RUNTIME_ENV"
      rmdir -- "$RUNTIME_DIR/backups" 2>/dev/null || true
      rmdir -- "$RUNTIME_DIR" 2>/dev/null || true
    fi
    (( config_status == 0 )) || exit "$config_status"
    printf 'Project: %s\n' "$PHASE6_PROJECT"
    ;;
  doctor)
    printf 'Branch: %s\n' "$(git -C "$REPO_ROOT" branch --show-current)"
    printf 'HEAD: %s\n' "$(git -C "$REPO_ROOT" rev-parse HEAD)"
    printf 'Python 3.12: '
    if command -v python3.12 >/dev/null; then python3.12 --version; else printf 'unavailable\n'; fi
    printf 'Docker Compose: '
    if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then docker compose version; else printf 'unavailable\n'; fi
    if command -v docker >/dev/null 2>&1 && local_docker_endpoint; then
      if docker info >/dev/null 2>&1; then printf 'Docker daemon: available on a local Unix socket\n'; else printf 'Docker daemon: unavailable\n'; fi
    else
      printf 'Docker daemon: not queried (remote context/DOCKER_HOST is refused)\n'
    fi
    for binary in nginx pg_dump redis-cli gitleaks trivy shellcheck; do
      if command -v "$binary" >/dev/null; then printf '%s: available\n' "$binary"; else printf '%s: unavailable\n' "$binary"; fi
    done
    ;;
  start)
    require_docker_daemon
    ensure_runtime_env check-volumes
    if [[ -z "$(compose ps --quiet)" ]]; then
      check_port_available 127.0.0.1 "$HTTP_PORT"
      check_port_available 127.0.0.1 "$POSTGRES_PORT"
      check_port_available 127.0.0.1 "$REDIS_PORT"
    fi
    compose up --detach postgres redis
    wait_for_services
    # One-off jobs inherit the app's static frontend endpoint. Release it
    # before migrations/seeding when start is repeated on this test stack.
    compose stop concierge proxy
    compose run --rm --no-deps concierge alembic upgrade head
    seed_synthetic_data
    compose up --detach concierge proxy
    printf 'Phase 6 stack started. Local proxy: http://localhost:%s/\n' "$HTTP_PORT"
    printf 'No test credentials were printed. Guest UI global flag remains disabled by default.\n'
    ;;
  stop)
    require_runtime_env
    require_docker_daemon
    [[ $# -le 2 ]] || die "stop accepts at most one Phase 6 service name"
    if [[ -n "${2:-}" ]]; then
      case "$2" in concierge|proxy|postgres|redis) ;; *) die "unknown Phase 6 service: $2" ;; esac
      compose stop "$2"
    else
      compose stop
    fi
    ;;
  restart)
    require_runtime_env
    require_docker_daemon
    [[ $# -le 2 ]] || die "restart accepts at most one Phase 6 service name"
    if [[ -n "${2:-}" ]]; then
      case "$2" in concierge|proxy|postgres|redis) ;; *) die "unknown Phase 6 service: $2" ;; esac
      compose restart "$2"
    else
      compose restart
    fi
    ;;
  status)
    require_runtime_env
    require_docker_daemon
    compose ps --all
    ;;
  health)
    require_runtime_env
    require_docker_daemon
    compose exec -T postgres pg_isready -U concierge -d concierge
    compose exec -T redis redis-cli ping
    curl --fail --silent --show-error "http://localhost:${HTTP_PORT}/health/ready"
    printf '\n'
    ;;
  test)
    require_runtime_env
    require_docker_daemon
    command -v "$PHASE6_PYTHON" >/dev/null 2>&1 || die "set PHASE6_PYTHON to an installed Python 3.12 interpreter with requirements-dev.txt installed"
    python_version="$("$PHASE6_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    [[ "$python_version" == "3.12" ]] || die "PHASE6_PYTHON must be Python 3.12 (found $python_version)"
    env \
      -u DATABASE_URL -u REDIS_URL -u REDIS_TEST_URL \
      -u OPENAI_API_KEY -u GEMINI_API_KEY -u COMPATIBLE_API_KEY -u GOOGLE_PLACES_API_KEY \
      -u COMPATIBLE_API_BASE_URL -u LOCAL_AI_ALLOWED_ENDPOINTS -u ANTLABS_AUTH_URL \
      "$PHASE6_PYTHON" -m pytest -q
    export DATABASE_URL="postgresql+psycopg://concierge@127.0.0.1:${POSTGRES_PORT}/concierge"
    export REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/0"
    export REDIS_TEST_URL="redis://127.0.0.1:${REDIS_PORT}/2"
    if command -v pg_dump >/dev/null && pg_dump --version | grep -qE 'PostgreSQL 16\.'; then
      export PG_DUMP_AVAILABLE=1
    else
      unset PG_DUMP_AVAILABLE
      printf 'PostgreSQL backup integration will skip: PostgreSQL 16 pg_dump is unavailable on the host.\n'
    fi
    "$PHASE6_PYTHON" -m alembic upgrade head
    env \
      -u OPENAI_API_KEY -u GEMINI_API_KEY -u COMPATIBLE_API_KEY -u GOOGLE_PLACES_API_KEY \
      -u COMPATIBLE_API_BASE_URL -u LOCAL_AI_ALLOWED_ENDPOINTS -u ANTLABS_AUTH_URL \
      "$PHASE6_PYTHON" -m pytest -q \
      tests/test_postgres_sqlite_migration.py \
      tests/test_postgres_integration.py \
      tests/test_postgres_backup_integration.py \
      tests/test_redis_rate_limiter.py \
      tests/test_ai_provider_distributed_bulkhead.py
    ;;
  browser)
    require_runtime_env
    command -v "$PHASE6_PYTHON" >/dev/null 2>&1 || die "set PHASE6_PYTHON to Python 3.12 with application dependencies installed"
    env -u OPENAI_API_KEY -u GEMINI_API_KEY -u COMPATIBLE_API_KEY \
      -u GOOGLE_PLACES_API_KEY -u COMPATIBLE_API_BASE_URL -u LOCAL_AI_ALLOWED_ENDPOINTS \
      -u ANTLABS_AUTH_URL \
      PLAYWRIGHT_SERVER_COMMAND="$PHASE6_PYTHON -m uvicorn app.main:app --host 127.0.0.1 --port 8092 --no-proxy-headers" \
      PROPERTY_ID=ci-property npm --prefix "$REPO_ROOT" run test:e2e -- \
      --grep-invert @visual --retries=1 --reporter=list
    ;;
  logs)
    require_runtime_env
    require_docker_daemon
    [[ $# -le 2 ]] || die "logs accepts at most one Phase 6 service name"
    if [[ -n "${2:-}" ]]; then
      case "$2" in concierge|proxy|postgres|redis) ;; *) die "unknown Phase 6 service: $2" ;; esac
      compose logs --no-color --tail=200 "$2"
    else
      compose logs --no-color --tail=200
    fi
    ;;
  cleanup)
    require_runtime_env
    require_docker_daemon
    compose down --volumes --remove-orphans
    rm -f -- "$RUNTIME_ENV"
    rmdir -- "$RUNTIME_DIR/backups" 2>/dev/null || true
    rmdir -- "$RUNTIME_DIR" 2>/dev/null || true
    printf 'Removed only project %s and its Phase 6-labeled volumes.\n' "$PHASE6_PROJECT"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    die "unknown command: $command_name"
    ;;
esac
