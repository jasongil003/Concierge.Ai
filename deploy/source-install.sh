#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
INSTALL_LOG=$(mktemp "${TMPDIR:-/tmp}/concierge-install.XXXXXX")
VERBOSE=0
WITH_QA=0
NO_START=0
UNATTENDED=0
INSTALLER_STARTING=0
STEP=starting
VENV_PYTHON=
PLATFORM=
PLATFORM_LABEL=

cleanup_exit() {
    status=$?
    if [[ $status -eq 0 ]]; then
        rm -f "$INSTALL_LOG"
    else
        printf 'Installer output log: %s\n' "$INSTALL_LOG" >&2
    fi
}

cleanup_failed_start() {
    status=$1
    line=$2
    trap - ERR
    if [[ $INSTALLER_STARTING -eq 1 && -n "$VENV_PYTHON" ]]; then
        "$VENV_PYTHON" "$ROOT_DIR/deploy/source_service.py" --root "$ROOT_DIR" --platform "$PLATFORM" --unattended stop >/dev/null 2>&1 || true
        if [[ "$STEP" == service-configuration ]]; then
            printf '\n[✗] Concierge.AI service setup failed.\n' >&2
        else
            printf '\n[✗] Concierge.AI failed to start.\n' >&2
        fi
        printf 'Check: ./concierge logs\n' >&2
        if [[ "$PLATFORM" == linux ]]; then
            printf '      sudo journalctl -u concierge-ai.service -n 100 --no-pager\n' >&2
        fi
    else
        printf '\n[✗] Installation failed during %s (line %s).\n' "$STEP" "$line" >&2
    fi
    exit "$status"
}

trap cleanup_exit EXIT
trap 'cleanup_failed_start "$?" "$LINENO"' ERR

run_logged() {
    if [[ $VERBOSE -eq 1 ]]; then
        "$@"
        return
    fi
    if "$@" >"$INSTALL_LOG" 2>&1; then
        return 0
    else
        status=$?
        printf 'Command failed: %s\n' "$*" >&2
        tail -n 60 "$INSTALL_LOG" >&2 || true
        return "$status"
    fi
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --verbose) VERBOSE=1; shift ;;
        --with-qa) WITH_QA=1; shift ;;
        --no-start) NO_START=1; shift ;;
        --unattended) UNATTENDED=1; shift ;;
        -h|--help)
            cat <<'EOF'
Usage: ./install.sh [--verbose] [--with-qa] [--no-start] [--unattended]

  --verbose     Show full pip, application setup, and optional QA output.
  --with-qa     Install npm dependencies and Playwright Chromium (requires Node.js).
  --no-start    Configure a startup service but do not start Concierge.AI.
  --unattended  Do not prompt for sudo during Linux service setup.
EOF
            exit 0
            ;;
        *) fail "Unknown option: $1" ;;
    esac
done

if [[ $(id -u) -eq 0 ]]; then
    fail "Run ./install.sh as your normal account, without sudo."
fi

command -v git >/dev/null 2>&1 || fail "Git is required to verify that this is a source checkout."
git -C "$ROOT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 || fail "This installer installs the checked-out Git source; clone Concierge.AI first."

STEP=platform-detection
case "$(uname -s)" in
    Linux)
        PLATFORM=linux
        if [[ -r /etc/os-release ]]; then
            # shellcheck disable=SC1091
            . /etc/os-release
            PLATFORM_LABEL=${PRETTY_NAME:-${NAME:-Linux}}
        else
            PLATFORM_LABEL=Linux
        fi
        if [[ -n "${WSL_DISTRO_NAME:-}" ]] || { [[ -r /proc/version ]] && grep -qi microsoft /proc/version; }; then
            if [[ -r /proc/version ]] && grep -qi 'wsl2\|microsoft-standard-wsl2' /proc/version; then
                PLATFORM_LABEL="${WSL_DISTRO_NAME:-$PLATFORM_LABEL} under WSL2"
            else
                PLATFORM_LABEL="${WSL_DISTRO_NAME:-$PLATFORM_LABEL} under WSL"
            fi
        fi
        ;;
    Darwin)
        PLATFORM=macos
        PLATFORM_LABEL="macOS $(sw_vers -productVersion 2>/dev/null || uname -r)"
        ;;
    *)
        fail "Unsupported operating system: $(uname -s). Supported platforms are Ubuntu/Linux, WSL Ubuntu, and macOS."
        ;;
esac

printf '\nConcierge.AI Installer\n======================\n\n'
printf '[✓] Platform: %s\n' "$PLATFORM_LABEL"

STEP=python-detection
PYTHON_BIN=
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" "$ROOT_DIR/deploy/source_venv.py" check >/dev/null 2>&1; then
        PYTHON_BIN=$(command -v "$candidate")
        break
    fi
done
[[ -n "$PYTHON_BIN" ]] || fail "Python 3.11–3.14 is required; Python 3.12+ is preferred. Install a supported Python with venv support, then rerun ./install.sh."
PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')
"$PYTHON_BIN" -m venv --help >/dev/null 2>&1 || fail "Python $PYTHON_VERSION is missing venv support. Install the OS venv package (for Ubuntu: sudo apt install python3.12-venv) and rerun."
printf '[✓] Python: %s\n' "$PYTHON_VERSION"

STEP=port-check
SERVICE_ARGS=(--root "$ROOT_DIR" --platform "$PLATFORM")
if ! "$PYTHON_BIN" "$ROOT_DIR/deploy/source_service.py" "${SERVICE_ARGS[@]}" port-check; then
    if ! "$PYTHON_BIN" "$ROOT_DIR/deploy/source_service.py" "${SERVICE_ARGS[@]}" owns; then
        fail 'Port 8080 is already in use by another application. Stop it or change its port before installing Concierge.AI.'
    fi
fi

STEP=virtual-environment
VENV_DIR="$ROOT_DIR/.venv"
VENV_STATUS=$("$PYTHON_BIN" "$ROOT_DIR/deploy/source_venv.py" create --root "$ROOT_DIR")
if [[ "$VENV_STATUS" == existing ]]; then
    VENV_PYTHON="$VENV_DIR/bin/python"
    if ! "$VENV_PYTHON" "$ROOT_DIR/deploy/source_venv.py" check >/dev/null 2>&1; then
        fail "Existing .venv uses an unsupported Python version. Preserve it, move it aside, then rerun with Python 3.11–3.14."
    fi
    printf '[✓] Existing virtual environment detected\n'
else
    VENV_PYTHON="$VENV_DIR/bin/python"
    printf '[✓] Virtual environment created\n'
fi

STEP=python-dependencies
run_logged "$VENV_PYTHON" -m pip install --upgrade pip
run_logged "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"
printf '[✓] Python dependencies installed\n'

STEP=application-configuration
PREPARE_OUTPUT=$("$VENV_PYTHON" "$ROOT_DIR/deploy/source_install.py" prepare --root "$ROOT_DIR")
SECRET_STATUS=$(printf '%s\n' "$PREPARE_OUTPUT" | awk -F= '$1 == "secret" {print $2}')
ADMIN_STATUS=$(printf '%s\n' "$PREPARE_OUTPUT" | awk -F= '$1 == "admin" {print $2}')
EXISTING_ADMIN=$(printf '%s\n' "$PREPARE_OUTPUT" | awk -F= '$1 == "existing_admin" {print $2}')
printf '[✓] Environment configured\n'
if [[ "$SECRET_STATUS" == generated ]]; then
    printf '[✓] Encryption secret generated\n'
else
    printf '[✓] Existing encryption secret preserved\n'
fi
chmod 600 "$ROOT_DIR/.env"

STEP=database-and-bootstrap
INITIALIZE_OUTPUT=$("$VENV_PYTHON" "$ROOT_DIR/deploy/source_install.py" initialize --root "$ROOT_DIR" --python "$VENV_PYTHON")
DATABASE_KIND=$(printf '%s\n' "$INITIALIZE_OUTPUT" | awk -F= '$1 == "database" {print $2}')
EXISTING_ADMIN=$(printf '%s\n' "$INITIALIZE_OUTPUT" | awk -F= '$1 == "existing_admin" {print $2}')
if [[ "$DATABASE_KIND" == postgresql ]]; then
    printf '[✓] Database migrations applied\n'
else
    printf '[✓] SQLite database initialized\n'
fi
if [[ "$EXISTING_ADMIN" == yes || "$ADMIN_STATUS" == existing ]]; then
    printf '[✓] Existing administrator preserved\n'
else
    printf '[✓] Administrator initialized\n'
fi

STEP=optional-dependencies
OPTIONAL_OUTPUT=$("$VENV_PYTHON" "$ROOT_DIR/deploy/source_install.py" optional-status)
NODE_STATUS=$(printf '%s\n' "$OPTIONAL_OUTPUT" | awk -F= '$1 == "node" {print $2}')
NPM_STATUS=$(printf '%s\n' "$OPTIONAL_OUTPUT" | awk -F= '$1 == "npm" {print $2}')
OLLAMA_STATUS=$(printf '%s\n' "$OPTIONAL_OUTPUT" | awk -F= '$1 == "ollama" {print $2}')
if [[ "$OLLAMA_STATUS" == present ]]; then
    printf '[✓] Ollama detected\n'
else
    printf '[i] Ollama not installed — hosted AI providers can still be used.\n'
fi
if [[ "$NODE_STATUS" == present && "$NPM_STATUS" == present ]]; then
    printf '[✓] Node.js detected (optional browser QA)\n'
    if [[ $WITH_QA -eq 1 ]]; then
        run_logged npm --prefix "$ROOT_DIR" ci
        run_logged npx --prefix "$ROOT_DIR" playwright install chromium
        printf '[✓] Browser QA dependencies installed\n'
    fi
else
    if [[ "$NODE_STATUS" == present ]]; then
        printf '[!] npm not installed — browser QA tools skipped.\n'
    else
        printf '[!] Node.js not installed — browser QA tools skipped.\n'
    fi
    if [[ $WITH_QA -eq 1 ]]; then
        fail '--with-qa requires Node.js and npm. Install Node.js with npm, then rerun ./install.sh --with-qa.'
    fi
fi

STEP=service-configuration
RUN_USER=$(id -un)
SERVICE_INSTALL_ARGS=("${SERVICE_ARGS[@]}" install --user "$RUN_USER")
if [[ $NO_START -eq 1 ]]; then
    SERVICE_INSTALL_ARGS+=(--no-start)
fi
if [[ $UNATTENDED -eq 1 ]]; then
    SERVICE_INSTALL_ARGS+=(--unattended)
fi
if [[ $NO_START -eq 0 ]]; then
    INSTALLER_STARTING=1
fi
SERVICE_OUTPUT=$("$VENV_PYTHON" "$ROOT_DIR/deploy/source_service.py" "${SERVICE_INSTALL_ARGS[@]}")
SERVICE_MODE=$(printf '%s\n' "$SERVICE_OUTPUT" | awk -F= '$1 == "service" {print $2}')
printf '[✓] Service configured%s\n' "${SERVICE_MODE:+ ($SERVICE_MODE)}"

if [[ $NO_START -eq 1 ]]; then
    printf '\nService is configured but was not started (--no-start). Run ./start.sh when ready.\n'
    exit 0
fi

STEP=startup-health
INSTALLER_STARTING=1
if ! "$VENV_PYTHON" "$ROOT_DIR/deploy/source_service.py" "${SERVICE_ARGS[@]}" wait-health --timeout 120; then
    exit 1
fi
printf '[✓] Health check passed\n'
INSTALLER_STARTING=0

printf '\nInstallation complete.\n\n'
printf 'Guest:\nhttp://localhost:8080\n\n'
printf 'Admin:\nhttp://localhost:8080/admin\n\n'
printf 'Default login:\nUsername: root\nPassword: admin\n\n'
printf 'Change the default password after first login.\n'
if [[ "$PLATFORM" == linux ]]; then
    HOST_IP=$("$VENV_PYTHON" -c '
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("192.0.2.1", 80))
    print(s.getsockname()[0])
except OSError:
    pass
finally:
    s.close()
' 2>/dev/null || true)
    if [[ -n "$HOST_IP" ]]; then
        printf '\nHost network address: %s (Concierge.AI listens on localhost only by default).\n' "$HOST_IP"
    fi
fi
