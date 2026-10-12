#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
PYTHON="$REPO_ROOT/.venv/bin/python"
DEMO_PORT="${INTELLIGENT_UI_DEMO_PORT:-8080}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing $PYTHON. Create the project virtual environment and install requirements first." >&2
  exit 1
fi

if [[ ! "$DEMO_PORT" =~ ^[0-9]+$ ]] || (( DEMO_PORT < 1 || DEMO_PORT > 65535 )); then
  echo "INTELLIGENT_UI_DEMO_PORT must be a TCP port from 1 through 65535 (received: $DEMO_PORT)." >&2
  exit 2
fi

if ! "$PYTHON" - "$DEMO_PORT" <<'PY'
import socket
import sys

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind(("127.0.0.1", int(sys.argv[1])))
    except OSError as exc:
        print(f"127.0.0.1:{sys.argv[1]} is unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1)
PY
then
  echo "Choose another port with INTELLIGENT_UI_DEMO_PORT=8081 ./scripts/start-intelligent-ui-demo.sh" >&2
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$DEMO_PORT" -sTCP:LISTEN >&2 || true
  fi
  exit 1
fi

echo "Starting the local app on http://127.0.0.1:$DEMO_PORT (global Intelligent UI switch enabled for this process)."
echo "Property opt-in is still required. The app uses the DB_PATH and other settings from your environment/.env."
cd "$REPO_ROOT"
INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=true exec "$PYTHON" -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "$DEMO_PORT" \
  --no-proxy-headers
