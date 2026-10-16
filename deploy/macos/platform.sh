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
    platform_runtime_preflight
    launchctl kickstart -k system/com.conciergeai.server
    launchctl kickstart -k system/com.conciergeai.proxy
}
platform_service_restart() { platform_runtime_preflight && /usr/local/libexec/concierge-restart; }
platform_service_stop() {
    launchctl kill SIGTERM system/com.conciergeai.proxy >/dev/null 2>&1 || true
    launchctl kill SIGTERM system/com.conciergeai.server >/dev/null 2>&1 || true
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 \
        /opt/concierge/current/deploy/common/preflight.py port-free --port 8080 --timeout 60 && \
        /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 \
        /opt/concierge/current/deploy/common/preflight.py port-free --port 8081 --timeout 60
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
