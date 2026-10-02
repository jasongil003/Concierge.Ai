#!/bin/bash
set -euo pipefail

APP_ROOT=/opt/concierge
APP_RELEASE="$APP_ROOT/current"
[ -d "$APP_RELEASE" ] || { echo "Concierge.AI is not installed at $APP_ROOT." >&2; exit 1; }
# shellcheck disable=SC1090
. "$APP_RELEASE/deploy/common/runtime.sh"
case "$(uname -s)" in
    Linux)
        CONCIERGE_OS=linux
        # shellcheck disable=SC1090
        . "$APP_RELEASE/deploy/linux/platform.sh"
        ;;
    Darwin)
        CONCIERGE_OS=macos
        # shellcheck disable=SC1090
        . "$APP_RELEASE/deploy/macos/platform.sh"
        ;;
    *) die "Unsupported host platform." ;;
esac

require_root() {
    [ "$(id -u)" -eq 0 ] || die "Use sudo for appliance management commands."
}

make_backup() {
    require_root
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    archive_name="concierge-${stamp}.zip"
    platform_backup_create "$archive_name"
    platform_backup_verify "$BACKUP_ROOT/$archive_name"
    info "backup created and verified: $BACKUP_ROOT/$archive_name"
}

update_release() {
    require_root
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/concierge-update.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT
    fetch_release "$temporary/release"
    new_version=$(cat "$temporary/release/unpacked/RELEASE_VERSION")
    current_version=$(cat "$APP_RELEASE/RELEASE_VERSION")
    if [ "$new_version" = "$current_version" ]; then
        info "already running stable release v${current_version}"
        return 0
    fi
    info "updating v${current_version} -> v${new_version}"
    make_backup
    backup_name=$(ls -1t "$BACKUP_ROOT"/concierge-*.zip | head -n 1)
    platform_backup_verify "$backup_name" || die "The pre-update backup did not verify; refusing to update."
    previous_target=$(readlink "$APP_ROOT/current")
    platform_service_stop || true
    if ! platform_install_release "$temporary/release/unpacked"; then
        ln -sfn "$previous_target" "$APP_ROOT/current.next"
        mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"
        platform_service_start || true
        die "Release installation failed; the previous release pointer was restored."
    fi
    if ! platform_migrate; then
        ln -sfn "$previous_target" "$APP_ROOT/current.next"
        mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"
        platform_service_start || true
        die "The application migration failed; the previous release pointer was restored. The verified backup is retained."
    fi
    platform_service_start
    if ! wait_for_health http://127.0.0.1:8080 180; then
        platform_service_stop || true
        ln -sfn "$previous_target" "$APP_ROOT/current.next"
        mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"
        platform_service_start || true
        wait_for_health http://127.0.0.1:8080 120 || true
        die "The update failed health checks; the previous release was restored. The verified backup and new release are retained."
    fi
    info "updated to v${new_version}; previous release retained at $previous_target"
}

internal_recover() {
    platform_internal_health
}

boot_test_prepare() {
    require_root
    platform_boot_components || die "One or more appliance services are not running."
    wait_for_health http://127.0.0.1:8080 30 || die "Concierge live/readiness checks failed."
    admin_status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 -H 'Host: 127.0.0.1' http://127.0.0.1:8080/admin/login || true)
    [ "$admin_status" = 200 ] || die "Localhost Admin endpoint returned HTTP $admin_status."
    make_backup
    platform_result=$(platform_data_signature)
    if [ "$CONCIERGE_OS" = macos ]; then python_path=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14; else python_path=python3; fi
    property_count=$(printf '%s' "$platform_result" | "$python_path" -c 'import json,sys; print(json.load(sys.stdin)["count"])')
    signature=$(printf '%s' "$platform_result" | "$python_path" -c 'import json,sys; print(json.load(sys.stdin)["signature"])')
    "$python_path" "$APP_RELEASE/deploy/common/boot_test.py" prepare --state-file "$STATE_ROOT/boot-test.json" \
        --platform "$PLATFORM_NAME" --version "$(cat "$APP_RELEASE/RELEASE_VERSION")" \
        --boot-id "$(platform_boot_id)" --property-count "$property_count" --signature "$signature"
    info "Now reboot the appliance without starting Docker, logging into the desktop, or launching Concierge manually."
}

boot_test_verify() {
    require_root
    platform_boot_components || die "Docker/runtime, Concierge, or its proxy is not running after boot."
    wait_for_health http://127.0.0.1:8080 180 || die "Concierge live/readiness checks failed after boot."
    admin_status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 -H 'Host: 127.0.0.1' http://127.0.0.1:8080/admin/login || true)
    [ "$admin_status" = 200 ] || die "Localhost Admin endpoint returned HTTP $admin_status."
    platform_result=$(platform_data_signature)
    if [ "$CONCIERGE_OS" = macos ]; then python_path=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14; else python_path=python3; fi
    property_count=$(printf '%s' "$platform_result" | "$python_path" -c 'import json,sys; print(json.load(sys.stdin)["count"])')
    signature=$(printf '%s' "$platform_result" | "$python_path" -c 'import json,sys; print(json.load(sys.stdin)["signature"])')
    "$python_path" "$APP_RELEASE/deploy/common/boot_test.py" verify --state-file "$STATE_ROOT/boot-test.json" \
        --boot-id "$(platform_boot_id)" --property-count "$property_count" --signature "$signature"
}

case "${1:-}" in
    status)
        platform_service_status
        ;;
    health)
        curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
        printf '\n'
        ;;
    backup)
        make_backup
        ;;
    update)
        update_release
        ;;
    internal-serve)
        require_root
        platform_internal_serve
        ;;
    internal-stop)
        require_root
        platform_internal_stop
        ;;
    internal-health)
        require_root
        internal_recover
        ;;
    internal-backup)
        make_backup
        ;;
    internal-maintenance)
        require_root
        if declare -F platform_runtime_maintenance >/dev/null; then
            platform_runtime_maintenance
        fi
        platform_retention
        ;;
    local-ai)
        require_root
        case "${2:-status}" in
            status) platform_local_ai_status ;;
            enable) type platform_local_ai_enable >/dev/null 2>&1 && platform_local_ai_enable || die "Optional local AI is not available for this platform." ;;
            disable) type platform_local_ai_disable >/dev/null 2>&1 && platform_local_ai_disable || die "Optional local AI is not available for this platform." ;;
            uninstall) type platform_local_ai_uninstall >/dev/null 2>&1 && platform_local_ai_uninstall || die "Optional local AI is not available for this platform." ;;
            *) die "Usage: concierge local-ai {status|enable|disable|uninstall}" ;;
        esac
        ;;
    boot-test)
        case "${2:-}" in
            prepare) boot_test_prepare ;;
            verify) boot_test_verify ;;
            *) die "Usage: sudo concierge boot-test {prepare|verify}" ;;
        esac
        ;;
    *)
        cat >&2 <<'EOF'
Usage: concierge {status|health|backup|update|local-ai ...|boot-test {prepare|verify}}
System jobs: internal-serve, internal-stop, internal-health, internal-backup, internal-maintenance
EOF
        exit 2
        ;;
esac
