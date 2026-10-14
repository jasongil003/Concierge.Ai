#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
PYTHON="$ROOT_DIR/.venv/bin/python"
DEMO_DIR="$ROOT_DIR/.local-demo"
STATE_DIR="$DEMO_DIR/state"
UPLOAD_DIR="$DEMO_DIR/uploads"
LOG_FILE="$DEMO_DIR/server.log"
PID_FILE="$DEMO_DIR/server.pid"
MARKER_FILE="$DEMO_DIR/DEMO_STATE"
PORT="${CONCIERGE_LOCAL_DEMO_PORT:-8082}"
BASE_URL="http://127.0.0.1:$PORT"

usage() {
  cat <<'EOF'
Usage: ./scripts/local-demo.sh <command>

Commands:
  start          Start and seed the isolated Hotel De Luna demo on loopback
  stop           Stop only the process started by this launcher
  restart        Restart the isolated demo app
  seed           Create or update fictional hotel content through Admin APIs
  import <zip>   Import the Hotel De Luna V2 package into the isolated demo
  reset [--yes]  Clear only .local-demo/state and .local-demo/uploads, then seed
  foreground     Run the local demo in the current terminal until Ctrl+C
  health         Check the local demo health endpoint
  logs           Follow the local demo application log
  backend-tests  Run the repository Python test suite
  e2e-tests      Run the repository Playwright suite (ephemeral test database)
  screenshots    Capture guest and admin browser states from the seeded demo
EOF
}

fail() { printf 'local-demo: %s\n' "$*" >&2; exit 1; }

configure_environment() {
  [[ -x "$PYTHON" ]] || fail "Missing $PYTHON. Install the project requirements into .venv first."
  [[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || fail "CONCIERGE_LOCAL_DEMO_PORT must be a TCP port from 1 through 65535."
  local admin_password
  admin_password=$("$PYTHON" "$ROOT_DIR/scripts/local_demo_credentials.py" --ensure --field admin_password)

  # The local demo intentionally clears inherited remote database and provider
  # configuration before app.config imports .env. A blank exported value also
  # prevents python-dotenv from filling it from a developer's root .env file.
  unset DATABASE_URL REDIS_URL GEMINI_API_KEY OPENAI_API_KEY COMPATIBLE_API_BASE_URL COMPATIBLE_API_KEY GOOGLE_PLACES_API_KEY
  export APP_NAME="Concierge.AI Local Demo"
  export APP_ENVIRONMENT=development
  export CONCIERGE_DEPLOYMENT_MODE=source
  export CONCIERGE_LOCAL_DEMO=1
  export DEMO_MODE=true
  export APP_HOST=127.0.0.1 APP_PORT="$PORT"
  export PROPERTY_ID=hotel-de-luna-demo
  export DB_PATH="$STATE_DIR/concierge.db"
  export STATE_DIRECTORY="$STATE_DIR"
  export UPLOAD_ROOT="$UPLOAD_DIR"
  export DATABASE_URL= REDIS_URL=
  export ADMIN_BOOTSTRAP_USERNAME=demo-admin
  export ADMIN_BOOTSTRAP_PASSWORD="$admin_password"
  export CREDENTIAL_ENCRYPTION_SECRET='Local-Demo-Only-Secret-Do-Not-Reuse-2036'
  export ADMIN_ALLOWED_CIDRS=127.0.0.1/32,::1/128
  export CANONICAL_HOSTS=localhost,127.0.0.1
  export PUBLIC_BASE_URL="$BASE_URL"
  export ADMIN_COOKIE_SECURE=false
  export ALLOW_BODY_PROPERTY_SELECTION=false
  export ALLOW_DEMO_SETTINGS=true
  export INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=true
  export ENABLE_BACKGROUND_WORKERS=false
  export SESSION_TTL_MINUTES=60
  export AI_PROVIDER_MODE=auto AI_DEFAULT_MODE=auto AI_GUEST_MODE_SWITCH=true
  export LOCAL_AI_ENABLED=true
  export OLLAMA_BASE_URL=http://127.0.0.1:11434
  export LOCAL_AI_ALLOWED_ENDPOINTS=http://127.0.0.1:11434
  export OLLAMA_MODEL=qwen3:8b
  export GEMINI_API_KEY= OPENAI_API_KEY= COMPATIBLE_API_BASE_URL= COMPATIBLE_API_KEY= GOOGLE_PLACES_API_KEY=
  export ANTLABS_MODE=mock
  export APP_DEBUG=false
}

seed_local_data() {
  local package="$DEMO_DIR/hotel_de_luna_v2.zip"
  if [[ -f "$package" ]]; then
    "$PYTHON" "$ROOT_DIR/scripts/import_hotel_de_luna_v2.py" --archive "$package" --base-url "$BASE_URL"
  else
    "$PYTHON" "$ROOT_DIR/scripts/seed_local_demo.py" --base-url "$BASE_URL"
  fi
}

write_marker() {
  mkdir -p "$DEMO_DIR"
  local marker="Concierge.AI local demo state v1\nrepo=$ROOT_DIR\n"
  if [[ -e "$MARKER_FILE" ]]; then
    [[ "$(cat "$MARKER_FILE")" == "$(printf '%b' "$marker")" ]] || fail "Demo state marker does not match this checkout. Refusing to continue."
  else
    printf '%b' "$marker" > "$MARKER_FILE"
  fi
}

listener_pid() {
  lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

is_managed_process() {
  [[ -f "$PID_FILE" ]] || return 1
  local saved_pid current_listener
  saved_pid=$(cat "$PID_FILE")
  [[ "$saved_pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$saved_pid" 2>/dev/null || return 1
  current_listener=$(listener_pid)
  [[ "$current_listener" == "$saved_pid" ]]
}

start_demo() {
  configure_environment
  write_marker
  mkdir -p "$STATE_DIR" "$UPLOAD_DIR"
  if is_managed_process; then
    printf 'Local demo is already running at %s (pid %s).\n' "$BASE_URL" "$(cat "$PID_FILE")"
    return
  fi
  local current_listener
  current_listener=$(listener_pid)
  [[ -z "$current_listener" ]] || fail "Port $PORT is owned by pid $current_listener. No process was stopped; choose another port with CONCIERGE_LOCAL_DEMO_PORT."
  : > "$LOG_FILE"
  (
    cd "$ROOT_DIR"
    nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --no-proxy-headers --log-level info >> "$LOG_FILE" 2>&1 < /dev/null &
    echo $! > "$PID_FILE"
  )
  local attempt
  for attempt in {1..60}; do
    if curl --silent --fail --max-time 1 "$BASE_URL/health/ready" >/dev/null 2>&1; then
      printf 'Local demo is ready at %s (pid %s).\n' "$BASE_URL" "$(cat "$PID_FILE")"
      printf 'Guest UI: %s/\nAdmin portal: %s/admin\nAPI: %s/docs\n' "$BASE_URL" "$BASE_URL" "$BASE_URL"
      return
    fi
    if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      tail -80 "$LOG_FILE" >&2 || true
      fail "The local demo process exited before becoming healthy."
    fi
    sleep 1
  done
  tail -80 "$LOG_FILE" >&2 || true
  fail "The local demo did not become healthy within 60 seconds."
}

run_foreground() {
  configure_environment
  write_marker
  mkdir -p "$STATE_DIR" "$UPLOAD_DIR"
  local current_listener
  current_listener=$(listener_pid)
  [[ -z "$current_listener" ]] || fail "Port $PORT is owned by pid $current_listener. No process was stopped."
  echo $$ > "$PID_FILE"
  printf 'Running local demo at %s in the foreground; press Ctrl+C to stop it.\n' "$BASE_URL"
  cd "$ROOT_DIR"
  exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --no-proxy-headers --log-level info
}

stop_demo() {
  configure_environment
  if [[ ! -f "$PID_FILE" ]]; then
    printf 'No local demo process is recorded.\n'
    return
  fi
  local saved_pid current_listener attempt
  saved_pid=$(cat "$PID_FILE")
  [[ "$saved_pid" =~ ^[0-9]+$ ]] || fail "Invalid local demo PID file. Inspect $PID_FILE before removing it."
  if ! kill -0 "$saved_pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    printf 'Removed stale local demo PID file; no process was running.\n'
    return
  fi
  current_listener=$(listener_pid)
  [[ "$current_listener" == "$saved_pid" ]] || fail "Recorded PID $saved_pid does not own port $PORT. Refusing to signal a possibly unrelated process."
  kill -TERM "$saved_pid"
  for attempt in {1..20}; do
    if ! kill -0 "$saved_pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      printf 'Stopped local demo (pid %s).\n' "$saved_pid"
      return
    fi
    sleep 0.5
  done
  fail "The local demo process did not stop after SIGTERM. Review $LOG_FILE."
}

ensure_demo() {
  configure_environment
  if ! is_managed_process; then start_demo; fi
}

safe_reset() {
  configure_environment
  write_marker
  local confirmation=${1:-}
  if [[ "$confirmation" != "--yes" ]]; then
    printf 'This clears only the isolated local demo database and uploads under %s. Type RESET to continue: ' "$DEMO_DIR"
    local answer
    read -r answer
    [[ "$answer" == RESET ]] || fail "Reset cancelled."
  fi
  stop_demo
  "$PYTHON" "$ROOT_DIR/scripts/local_demo_reset.py"
  start_demo
  seed_local_data
  printf 'Local demo data has been reset and seeded.\n'
}

command_name=${1:-}
[[ -n "$command_name" ]] || { usage; exit 2; }
shift

case "$command_name" in
  start) start_demo; seed_local_data ;;
  import)
    [[ $# -eq 1 ]] || fail "Usage: ./scripts/local-demo.sh import /path/to/Hotel_De_Luna_V2_Complete_Demo.zip"
    ensure_demo
    "$PYTHON" "$ROOT_DIR/scripts/import_hotel_de_luna_v2.py" --archive "$1" --base-url "$BASE_URL"
    ;;
  foreground) run_foreground ;;
  stop) stop_demo ;;
  restart) stop_demo; start_demo ;;
  seed) ensure_demo; seed_local_data ;;
  reset) safe_reset "${1:-}" ;;
  health)
    configure_environment
    curl --fail --silent --show-error --max-time 3 "$BASE_URL/health/ready" || fail "Local demo health check failed."
    printf '\n'
    ;;
  logs)
    [[ -f "$LOG_FILE" ]] || fail "No log exists yet. Run ./scripts/local-demo.sh start first."
    tail -f "$LOG_FILE"
    ;;
  backend-tests)
    # pytest's conftest creates and validates an independent temporary SQLite
    # state root before importing the app. Keep demo credentials and feature
    # flags out of that process while preventing any inherited remote services.
    unset DEMO_MODE CONCIERGE_LOCAL_DEMO APP_NAME APP_HOST APP_PORT APP_DEBUG PROPERTY_ID DB_PATH STATE_DIRECTORY UPLOAD_ROOT
    unset ADMIN_BOOTSTRAP_PASSWORD CREDENTIAL_ENCRYPTION_SECRET
    export APP_ENVIRONMENT=test CONCIERGE_TESTING=1
    export ADMIN_BOOTSTRAP_USERNAME=root ALLOW_DEMO_SETTINGS=false
    unset DATABASE_URL REDIS_URL
    export PYTHON_DOTENV_DISABLED=1
    unset GEMINI_API_KEY OPENAI_API_KEY COMPATIBLE_API_BASE_URL COMPATIBLE_API_KEY GOOGLE_PLACES_API_KEY
    cd "$ROOT_DIR"
    exec "$PYTHON" -m pytest
    ;;
  e2e-tests)
    cd "$ROOT_DIR"
    exec npm run test:e2e
    ;;
  screenshots)
    ensure_demo
    cd "$ROOT_DIR"
    if [[ -f "$DEMO_DIR/hotel_de_luna_v2.zip" ]]; then
      exec node scripts/local_demo_v2_screenshots.mjs "$BASE_URL"
    fi
    exec node scripts/local_demo_screenshots.mjs "$BASE_URL"
    ;;
  -h|--help|help) usage ;;
  *) usage >&2; fail "Unknown command '$command_name'." ;;
esac
