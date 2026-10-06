#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ORIGINAL_ARGS=("$@")
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

source_runtime_active() {
    ps -axo args= | awk '
        index($0, "uvicorn") && index($0, "app.main:app") && !index($0, "/opt/concierge/current/") { found = 1 }
        END { exit !found }
    '
}

if launchctl print system/com.conciergeai.source >/dev/null 2>&1 || source_runtime_active; then
    die "The source-mode LaunchAgent is active; appliance install would create competing runtimes. No state or services were changed. Run concierge doctor and stop only the runtime you intend to replace."
fi
if nc -z -w 1 127.0.0.1 8080 >/dev/null 2>&1 && ! launchctl print system/com.conciergeai.server >/dev/null 2>&1; then
    die "Port 8080 is occupied by another runtime. No state or services were changed. Identify the owner and run concierge doctor before continuing."
fi

if [ "${CONCIERGE_OPERATION_LOCK_HELD:-}" != 1 ]; then
    /usr/bin/perl "$release_dir/deploy/common/operation_lock.pl" run \
        --lock /opt/concierge/.deployment.lock -- "$0" "${ORIGINAL_ARGS[@]}"
    exit $?
fi

if launchctl print system/com.conciergeai.source >/dev/null 2>&1 || source_runtime_active; then
    die "The source-mode LaunchAgent is active; appliance install would create competing runtimes."
fi
if [ -e "$APP_ROOT/current" ] || [ -L "$APP_ROOT/current" ]; then
    die "An appliance release already exists at $APP_ROOT/current. Use 'sudo concierge update' to upgrade; no installed release or persisted state was changed."
fi
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
    die "Installation reached LaunchDaemon startup but health validation failed; installed files and persisted state were retained. Run 'sudo concierge doctor' and inspect /Library/Logs/Concierge.AI/ without sharing secrets."
fi
admin_status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
    -H 'Host: 127.0.0.1' http://127.0.0.1:8080/admin/login || true)
[ "$admin_status" = 200 ] || die "The localhost Admin endpoint returned HTTP $admin_status."
platform_record_manifest
release_commit=$(cat /opt/concierge/current/RELEASE_COMMIT 2>/dev/null || printf unknown)
info "installation completed; health validation passed."
info "deployment mode: appliance  version: v${release_version}  commit: ${release_commit}"
info "Admin URL: http://127.0.0.1:8080/admin/login  internal URL: http://127.0.0.1:8080"
info "service: com.conciergeai.server + com.conciergeai.proxy  state: $STATE_ROOT  health: READY"
info "diagnostics: sudo concierge status  |  sudo concierge doctor"
info "installed v${release_version}; five machine LaunchDaemons are enabled at /Library/LaunchDaemons."
info "the app runs as _concierge after boot without a graphical login."
info "localhost: http://127.0.0.1:8080  Admin: http://127.0.0.1:8080/admin/login"
