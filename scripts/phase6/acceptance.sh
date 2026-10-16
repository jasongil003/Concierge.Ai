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
  CONCIERGE_BACKUP_DIR CONCIERGE_BACKUP_ENCRYPTION_KEY

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
  encrypt