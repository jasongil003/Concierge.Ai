#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=../common/runtime.sh
. "$SCRIPT_DIR/../common/runtime.sh"
# shellcheck source=../common/configure.sh
. "$SCRIPT_DIR/../common/configure.sh"
# shellcheck source=platform.sh
. "$SCRIPT_DIR/platform.sh"

release_dir=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --release-dir) release_dir=$2; shift 2 ;;
        *) die "Unknown argument: $1" ;;
    esac
done
[ -n "$release_dir" ] && [ -f "$release_dir/RELEASE_VERSION" ] || die "A verified release directory is required."
[ "$(id -u)" -eq 0 ] || die "Run with sudo."
detect_platform
[ "$CONCIERGE_ARCH" = arm64 ] || die "Production macOS appliances require Apple Silicon (arm64)."
assert_space 10 /opt
macos_major=$(sw_vers -productVersion | cut -d. -f1)
case "$macos_major" in
    15|26|27) ;;
    *) die "Use a currently supported macOS release: Sequoia 15, Tahoe 26, or Golden Gate 27." ;;
esac

create_service_account() {
    if dscl . -read /Users/_concierge >/dev/null 2>&1; then
        return
    fi
    candidate=600
    while dscl . -list /Users UniqueID | awk -v id="$candidate" '$2 == id { found = 1 } END { exit !found }' || \
        dscl . -list /Groups PrimaryGroupID | awk -v id="$candidate" '$2 == id { found = 1 } END { exit !found }'; do
        candidate=$((candidate + 1))
        [ "$candidate" -lt 1000 ] || die "Could not allocate an unused system account identifier."
    done
    dscl . -create /Groups/_concierge
    dscl . -create /Groups/_concierge PrimaryGroupID "$candidate"
    dscl . -create /Groups/_concierge RealName "Concierge.AI service"
    dscl . -create /Users/_concierge
    dscl . -create /Users/_concierge UserShell /usr/bin/false
    dscl . -create /Users/_concierge RealName "Concierge.AI service"
    dscl . -create /Users/_concierge UniqueID "$candidate"
    dscl . -create /Users/_concierge PrimaryGroupID "$candidate"
    dscl . -create /Users/_concierge NFSHomeDirectory /var/empty
}

create_service_account
mkdir -p /opt/concierge/releases "$STATE_ROOT" "$BACKUP_ROOT" /Library/Logs/Concierge.AI /Library/LaunchDaemons /usr/local/bin /usr/local/libexec
chown -R _concierge:_concierge "$STATE_ROOT"
chmod 0750 "$STATE_ROOT"
chown root:_concierge "$BACKUP_ROOT"
chmod 0770 "$BACKUP_ROOT"
chown -R _concierge:_concierge /Library/Logs/Concierge.AI
chmod 0750 /Library/Logs/Concierge.AI
platform_ensure_python
generate_config "$CONFIG_FILE" "$STATE_ROOT" "$BACKUP_ROOT" '127.0.0.1/32,::1/128' 'http://127.0.0.1:11434' _concierge

release_version=$(cat "$release_dir/RELEASE_VERSION")
platform_install_release "$release_dir"
platform_service_start
chmod 0640 "$CONFIG_FILE"
chown root:_concierge "$CONFIG_FILE"
if ! wait_for_health http://127.0.0.1:8080 180; then
    launchctl print system/com.conciergeai.server || true
    tail -n 100 /Library/Logs/Concierge.AI/server.err.log || true
    die "Concierge did not become healthy. Inspect its LaunchDaemon logs and configuration."
fi
admin_status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
    -H 'Host: 127.0.0.1' http://127.0.0.1:8080/admin/login || true)
[ "$admin_status" = 200 ] || die "The localhost Admin endpoint returned HTTP $admin_status."
info "installed v${release_version}; five machine LaunchDaemons are enabled at /Library/LaunchDaemons."
info "the app runs as _concierge after boot without a graphical login."
info "localhost: http://127.0.0.1:8080  Admin: http://127.0.0.1:8080/admin/login"
