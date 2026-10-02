#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
cd "$ROOT_DIR"

if [ "$(uname -s)" != "Linux" ]; then
  echo "[ERROR] The systemd service installer is available on Linux only." >&2
  exit 1
fi
if [ ! -d /run/systemd/system ] || ! command -v systemctl >/dev/null 2>&1; then
  echo "[ERROR] systemd is not available on this Linux host." >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] Run this optional setup with sudo: sudo ./install-service.sh" >&2
  exit 1
fi
SERVICE_USER=${SUDO_USER:-}
if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "root" ]; then
  echo "[ERROR] Run this script with sudo from the account that owns the installation." >&2
  exit 1
fi
if [ ! -x .venv/bin/python ] || [ ! -f .env ]; then
  echo "[ERROR] Run ./install.sh before installing the system service." >&2
  exit 1
fi

.venv/bin/python deploy/source_install.py validate --root "$ROOT_DIR" --python "$ROOT_DIR/.venv/bin/python"
exec .venv/bin/python deploy/source_service.py --root "$ROOT_DIR" --platform linux install --user "$SERVICE_USER"
