#!/bin/bash

PLATFORM_NAME=macos-launchd
APP_ROOT=/opt/concierge
STATE_ROOT="/Library/Application Support/Concierge.AI"
BACKUP_ROOT="/Library/Application Support/Concierge.AI/Backups"
CONFIG_FILE="/Library/Application Support/Concierge.AI/concierge.env"
EVENT_LOG="$STATE_ROOT/recovery-events.jsonl"
RECOVERY_STATE="$STATE_ROOT/recovery-state.json"
RECOVERY_RESTART_COMMAND=(/usr/local/libexec/concierge-restart)

platform_service_start() {
    launchctl kickstart -k system/com.conciergeai.server
    launchctl kickstart -k system/com.conciergeai.proxy
}
platform_service_restart() { /usr/local/libexec/concierge-restart; }
platform_service_stop() {
    launchctl kill SIGTERM system/com.conciergeai.proxy >/dev/null 2>&1 || true
    launchctl kill SIGTERM system/com.conciergeai.server >/dev/null 2>&1 || true
}
platform_service_status() {
    launchctl print system/com.conciergeai.server
    launchctl print system/com.conciergeai.proxy
}
platform_active() { launchctl print system/com.conciergeai.server >/dev/null 2>&1 && launchctl print system/com.conciergeai.proxy >/dev/null 2>&1; }

platform_ensure_python() {
    page_file=$(mktemp "${TMPDIR:-/tmp}/concierge-python-page.XXXXXX")
    curl --fail --silent --show-error --location --retry 3 https://www.python.org/downloads/macos/ -o "$page_file"
    pkg_url=$(grep -Eo 'https://www\.python\.org/ftp/python/3\.14\.[0-9]+/python-3\.14\.[0-9]+-macos[0-9]+\.pkg' "$page_file" | head -n 1 || true)
    rm -f "$page_file"
    [ -n "$pkg_url" ] || die "Python.org did not publish a supported Python 3.14 macOS installer."
    desired=$(printf '%s' "$pkg_url" | sed -E 's#.*python-(3\.14\.[0-9]+)-macos.*#\1#')
    python=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
    installed=$("$python" --version 2>/dev/null | awk '{print $2}' || true)
    PLATFORM_PYTHON_UPDATED=0
    if [ "$installed" != "$desired" ]; then
        pkg_file=$(mktemp "${TMPDIR:-/tmp}/concierge-python-pkg.XXXXXX")
        curl --fail --silent --show-error --location --retry 3 "$pkg_url" -o "$pkg_file"
        signature=$(pkgutil --check-signature "$pkg_file" 2>&1) || die "The Python.org installer package signature is invalid."
        printf '%s\n' "$signature" | grep -q 'Python Software Foundation' || die "The Python installer is not signed by the Python Software Foundation."
        installer -pkg "$pkg_file" -target /
        rm -f "$pkg_file"
        PLATFORM_PYTHON_UPDATED=1
    fi
    [ -x "$python" ] || die "Python 3.14 was not installed successfully."
}

platform_install_release() {
    release_dir=$1
    version=$(cat "$release_dir/RELEASE_VERSION")
    target="$APP_ROOT/releases/$version"
    if [ ! -d "$target" ]; then
        mkdir -p "$target"
        cp -R "$release_dir"/. "$target/"
        chmod -R go-w "$target"
    fi
    python=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
    [ -x "$python" ] || die "Python 3.14 is not installed."
    if [ ! -x "$target/.venv/bin/python" ]; then
        "$python" -m venv "$target/.venv"
        "$target/.venv/bin/python" -m pip install --requirement "$target/requirements.txt"
        "$target/.venv/bin/python" -m compileall -q "$target/app"
    fi
    chown -R root:wheel "$target"
    chmod -R go-w "$target"
    ln -sfn "$target" "$APP_ROOT/current.next"
    mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"
    for label in server proxy health backup maintenance; do
        install -o root -g wheel -m 0644 \
            "$APP_ROOT/current/deploy/macos/com.conciergeai.$label.plist" \
            /Library/LaunchDaemons/
    done
    if [ -f /Library/LaunchDaemons/com.conciergeai.ollama.plist ]; then
        install -o root -g wheel -m 0644 \
            "$APP_ROOT/current/deploy/macos/com.conciergeai.ollama.plist" \
            /Library/LaunchDaemons/
    fi
    plutil -lint /Library/LaunchDaemons/com.conciergeai.server.plist /Library/LaunchDaemons/com.conciergeai.proxy.plist /Library/LaunchDaemons/com.conciergeai.health.plist \
        /Library/LaunchDaemons/com.conciergeai.backup.plist /Library/LaunchDaemons/com.conciergeai.maintenance.plist >/dev/null
    install -o root -g wheel -m 0755 "$APP_ROOT/current/deploy/common/concierge" /usr/local/bin/concierge
    install -o root -g wheel -m 0755 "$APP_ROOT/current/deploy/macos/concierge-restart" /usr/local/libexec/concierge-restart
    for label in server proxy health backup maintenance; do
        launchctl bootout "system/com.conciergeai.$label" >/dev/null 2>&1 || true
        launchctl enable "system/com.conciergeai.$label"
        launchctl bootstrap system "/Library/LaunchDaemons/com.conciergeai.$label.plist"
    done
}

platform_backup_create() {
    archive_name=$1
    run_app_python -m app.backup create "$BACKUP_ROOT/$archive_name" >/dev/null
}

platform_backup_verify() {
    run_app_python -m app.backup verify "$1" >/dev/null
}

platform_retention() {
    find "$BACKUP_ROOT" -type f -name 'concierge-*.zip' -mtime +30 -delete
    current=$(readlink "$APP_ROOT/current" 2>/dev/null || true)
    ls -1dt "$APP_ROOT"/releases/*/ 2>/dev/null | tail -n +4 | while IFS= read -r old_release; do
        old_release=${old_release%/}
        [ "$old_release" = "$current" ] || rm -rf "$old_release"
    done
}

platform_restart_command() { /usr/local/libexec/concierge-restart; }
platform_internal_serve() { die "Concierge runs as a launchd LaunchDaemon on macOS."; }
platform_internal_stop() { platform_service_stop; }

platform_migrate() {
    run_app_python -c 'import app.main'
}

platform_internal_health() {
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 \
        /opt/concierge/current/deploy/common/ops.py recover \
        --platform "$PLATFORM_NAME" --event-log "$EVENT_LOG" --state-file "$RECOVERY_STATE" \
        --max-restarts 3 --window-seconds 900 --post-restart-wait 45 \
        -- "${RECOVERY_RESTART_COMMAND[@]}"
}

run_app_python() {
    set -a
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"
    set +a
    cd "$APP_ROOT/current" || return 1
    "$APP_ROOT/current/.venv/bin/python" "$@"
}

platform_runtime_maintenance() {
    platform_ensure_python
    if [ "$PLATFORM_PYTHON_UPDATED" = 1 ]; then
        for app_release in "$APP_ROOT"/releases/*; do
            [ -d "$app_release/.venv" ] || continue
            "$app_release/.venv/bin/python" -m pip install --requirement "$app_release/requirements.txt" >/dev/null
        done
        platform_service_restart
        wait_for_health http://127.0.0.1:8080 120 || die "Concierge remained unhealthy after the Python security update."
    fi
}

platform_local_ai_status() {
    curl --fail --silent --show-error --max-time 3 http://127.0.0.1:11434/api/tags
}

platform_boot_id() {
    sysctl -n kern.boottime | sed -E 's/.*sec = ([0-9]+).*/\1/'
}

platform_data_signature() {
    run_app_python -c 'import hashlib,json; from app.config import settings; from app.properties import PropertyStore; records=[r.to_dict(include_secrets=True) for r in PropertyStore(settings.db_path).list()]; print(json.dumps({"count":len(records),"signature":hashlib.sha256(json.dumps(records,sort_keys=True,separators=(",",":")).encode()).hexdigest()}))'
}

platform_boot_components() {
    launchctl print system/com.conciergeai.server >/dev/null
    launchctl print system/com.conciergeai.proxy >/dev/null
}

write_app_settings() {
    local_ai_enabled=$1
    ollama_url=$2
    approved_model=$3
    LOCAL_AI_ENABLED="$local_ai_enabled" OLLAMA_BASE_URL="$ollama_url" OLLAMA_MODEL="$approved_model" \
        /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 - "$CONFIG_FILE" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
updates = {
    "LOCAL_AI_ENABLED": os.environ["LOCAL_AI_ENABLED"],
    "OLLAMA_BASE_URL": os.environ["OLLAMA_BASE_URL"],
    "OLLAMA_MODEL": os.environ["OLLAMA_MODEL"],
    "LOCAL_AI_ALLOWED_ENDPOINTS": os.environ["OLLAMA_BASE_URL"],
}
lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.split("=", 1)[0] not in updates]
lines.extend(f"{key}='{value}'" for key, value in updates.items())
temporary = path.with_suffix(".tmp")
temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(temporary, 0o640)
temporary.replace(path)
PY
    chown root:_concierge "$CONFIG_FILE"
}

ollama_latest_metadata() {
    api_file=$(mktemp "${TMPDIR:-/tmp}/concierge-ollama-api.XXXXXX")
    curl --fail --silent --show-error --location --retry 3 \
        -H 'Accept: application/vnd.github+json' https://api.github.com/repos/ollama/ollama/releases/latest -o "$api_file"
    metadata=$(/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 - "$api_file" <<'PY'
import json
import sys

release = json.load(open(sys.argv[1], encoding="utf-8"))
asset = next((item for item in release.get("assets", []) if item.get("name") == "Ollama-darwin.zip"), None)
if not asset:
    raise SystemExit("Latest Ollama release has no macOS app asset.")
print(release.get("tag_name", ""))
print(asset.get("browser_download_url", ""))
print(asset.get("digest", ""))
PY
    ) || die "Could not read verified Ollama release metadata."
    rm -f "$api_file"
    printf '%s\n' "$metadata"
}

platform_local_ai_enable() {
    detect_platform
    [ "$CONCIERGE_OS" = macos ] && [ "$CONCIERGE_ARCH" = arm64 ] || die "Ollama appliance support is currently Apple Silicon only."
    [ "$CONCIERGE_RAM_GIB" -ge 8 ] || die "The approved qwen3:4b model requires at least 8 GiB unified memory."
    assert_space 10 "$STATE_ROOT"
    mkdir -p "$STATE_ROOT/Ollama/models"
    chown -R _concierge:_concierge "$STATE_ROOT/Ollama"
    chmod 0750 "$STATE_ROOT/Ollama" "$STATE_ROOT/Ollama/models"

    ollama_bin=/Applications/Ollama.app/Contents/Resources/ollama
    if [ ! -x "$ollama_bin" ]; then
        metadata=$(ollama_latest_metadata)
        tag=$(printf '%s\n' "$metadata" | sed -n '1p')
        url=$(printf '%s\n' "$metadata" | sed -n '2p')
        digest=$(printf '%s\n' "$metadata" | sed -n '3p')
        printf '%s' "$tag" | grep -Eq '^v?[0-9]+\.[0-9]+\.[0-9]+$' || die "Ollama's release tag is invalid."
        case "$url" in https://github.com/ollama/ollama/releases/download/*/Ollama-darwin.zip) ;; *) die "Ollama returned an untrusted download URL." ;; esac
        printf '%s' "$digest" | grep -Eq '^sha256:[0-9a-fA-F]{64}$' || die "Ollama release metadata has no GitHub SHA-256 digest."
        temporary=$(mktemp -d "${TMPDIR:-/tmp}/concierge-ollama.XXXXXX")
        curl --fail --silent --show-error --location --retry 3 "$url" -o "$temporary/Ollama-darwin.zip"
        actual="sha256:$(shasum -a 256 "$temporary/Ollama-darwin.zip" | awk '{print $1}')"
        actual=$(printf '%s' "$actual" | tr '[:upper:]' '[:lower:]')
        digest=$(printf '%s' "$digest" | tr '[:upper:]' '[:lower:]')
        [ "$actual" = "$digest" ] || die "Ollama archive SHA-256 verification failed."
        unzip -q "$temporary/Ollama-darwin.zip" -d "$temporary"
        [ -d "$temporary/Ollama.app" ] || die "Ollama archive did not contain Ollama.app."
        codesign --verify --deep --strict "$temporary/Ollama.app" || die "Ollama.app code-signature verification failed."
        mkdir -p /Applications
        ditto "$temporary/Ollama.app" /Applications/Ollama.app
        rm -rf "$temporary"
    fi
    [ -x "$ollama_bin" ] || die "Ollama's signed CLI is missing from its application bundle."
    install -o root -g wheel -m 0644 "$APP_ROOT/current/deploy/macos/com.conciergeai.ollama.plist" /Library/LaunchDaemons/
    plutil -lint /Library/LaunchDaemons/com.conciergeai.ollama.plist >/dev/null
    launchctl bootout system/com.conciergeai.ollama >/dev/null 2>&1 || true
    launchctl enable system/com.conciergeai.ollama
    launchctl bootstrap system /Library/LaunchDaemons/com.conciergeai.ollama.plist
    attempt=0
    until curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; do
        attempt=$((attempt + 1))
        [ "$attempt" -lt 60 ] || die "Ollama did not become healthy. Concierge itself remains available."
        sleep 2
    done
    sudo -u _concierge /usr/bin/env OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$STATE_ROOT/Ollama/models" \
        "$ollama_bin" pull qwen3:4b
    platform_local_ai_status >/dev/null || die "Ollama health verification failed after pulling qwen3:4b."
    write_app_settings true http://127.0.0.1:11434 qwen3:4b
    platform_service_restart
    info "Ollama is enabled under launchd, the approved qwen3:4b model is present, and health is passing."
}

platform_local_ai_disable() {
    launchctl bootout system/com.conciergeai.ollama >/dev/null 2>&1 || true
    launchctl disable system/com.conciergeai.ollama >/dev/null 2>&1 || true
    write_app_settings false '' qwen3:4b
    platform_service_restart
    info "Ollama is disabled. Concierge remains independent of it."
}

platform_local_ai_uninstall() {
    platform_local_ai_disable
    rm -f /Library/LaunchDaemons/com.conciergeai.ollama.plist
    rm -rf /Applications/Ollama.app
    if [ -L /usr/local/bin/ollama ] && [ "$(readlink /usr/local/bin/ollama)" = /Applications/Ollama.app/Contents/Resources/ollama ]; then
        rm -f /usr/local/bin/ollama
    fi
    rm -rf "$STATE_ROOT/Ollama"
    info "Ollama and its cached model data were removed; Concierge remains installed."
}
