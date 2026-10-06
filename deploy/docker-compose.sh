#!/bin/bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
mode=${1:-}
[ "$#" -gt 0 ] || { printf 'Usage: %s {dev|appliance} docker-compose-arguments...\n' "$0" >&2; exit 2; }
shift
case "$mode" in
    dev)
        compose_file="$ROOT_DIR/docker-compose.dev.yml"
        project_suffix=$(python3 -c 'import hashlib,os,sys; print(hashlib.sha256(os.path.realpath(sys.argv[1]).encode()).hexdigest()[:10])' "$ROOT_DIR")
        project_name="concierge-dev-$project_suffix"
        preflight_mode=docker-dev
        default_port=8081
        ;;
    appliance)
        compose_file="$ROOT_DIR/docker-compose.yml"
        project_name=concierge
        preflight_mode=appliance
        default_port=8080
        ;;
    *) printf 'Unknown deployment mode: %s\n' "$mode" >&2; exit 2 ;;
esac

if [ "$mode" = appliance ]; then
    config_file=${CONCIERGE_CONFIG_FILE:-$ROOT_DIR/.env}
    admin_password=${ADMIN_BOOTSTRAP_PASSWORD:-}
    if [ -z "$admin_password" ] && [ -r "$config_file" ]; then
        admin_password=$(python3 - "$config_file" <<'PY'
from pathlib import Path
import re
import sys

try:
    lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
except OSError:
    lines = []
for line in lines:
    match = re.match(r"^\s*(?:export\s+)?ADMIN_BOOTSTRAP_PASSWORD\s*=\s*(.*?)\s*$", line)
    if not match:
        continue
    value = match.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    print(value)
    break
PY
)
    fi
    if [ "${#admin_password}" -lt 12 ] || [ "$admin_password" = admin ]; then
        printf 'Production Compose requires a unique ADMIN_BOOTSTRAP_PASSWORD of at least 12 characters in the environment or config file.\n' >&2
        exit 1
    fi
fi

if [ -z "${CONCIERGE_VERSION:-}" ]; then
    CONCIERGE_VERSION=$(git -C "$ROOT_DIR" describe --tags --always --dirty 2>/dev/null || cat "$ROOT_DIR/RELEASE_VERSION" 2>/dev/null || printf unknown)
fi
if [ -z "${CONCIERGE_COMMIT:-}" ]; then
    CONCIERGE_COMMIT=$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD 2>/dev/null || cat "$ROOT_DIR/RELEASE_COMMIT" 2>/dev/null || printf unknown)
fi
if [ -z "${CONCIERGE_BUILD_DATE:-}" ]; then
    CONCIERGE_BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
fi
[[ "$CONCIERGE_VERSION" =~ ^([vV]?[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)*|[A-Fa-f0-9]{7,40}|local|unknown)$ ]] || {
    printf 'Build version is not in a supported version format.\n' >&2
    exit 1
}
[[ "$CONCIERGE_COMMIT" =~ ^([A-Fa-f0-9]{7,40}|unknown)$ ]] || {
    printf 'Build commit is not a valid abbreviated Git commit.\n' >&2
    exit 1
}
[[ "$CONCIERGE_BUILD_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
    printf 'CONCIERGE_BUILD_DATE must be a UTC ISO timestamp.\n' >&2
    exit 1
}
export CONCIERGE_VERSION CONCIERGE_COMMIT CONCIERGE_BUILD_DATE
operation=${1:-}
preflight_port=$default_port
if [ "$mode" = dev ]; then
    preflight_port=${CONCIERGE_DEV_PORT:-$default_port}
fi
case "$operation" in
    up|start|restart|run)
        python3 "$ROOT_DIR/deploy/common/preflight.py" "$preflight_mode" \
            --port "$preflight_port" --project-name "$project_name"
        ;;
esac
exec docker compose --project-name "$project_name" --project-directory "$ROOT_DIR" -f "$compose_file" "$@"
