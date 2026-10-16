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

if [ "$CONCIERGE_OS" = macos ]; then
    CONCIERGE_TOOL_PYTHON=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
else
    CONCIERGE_TOOL_PYTHON=python3
fi

require_root() {
    [ "$(id -u)" -eq 0 ] || die "Use sudo for appliance management commands."
}

case "${1:-}" in
    update|backup|internal-backup|internal-health|internal-maintenance)
        lock_operation=1
        ;;
    *)
        lock_operation=0
        ;;
esac
if [ "${CONCIERGE_OPERATION_LOCK_HELD:-}" != 1 ] && [ "$lock_operation" = 1 ]; then
    require_root
    exec "$CONCIERGE_TOOL_PYTHON" "$APP_RELEASE/deploy/common/operation_lock.py" run \
        --lock "$APP_ROOT/.deployment.lock" -- "$0" "$@"
fi

make_backup() {
    require_root
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    archive_name="concierge-${stamp}.zip.enc"
    [ ! -e "$BACKUP_ROOT/$archive_name" ] || return 31
    platform_backup_create "$archive_name" || return 31
    platform_backup_verify "$BACKUP_ROOT/$archive_name" || return 32
    info "backup created and verified: $BACKUP_ROOT/$archive_name"
}

restore_previous_release() {
    failure_stage=$1
    failure_reason=$2
    rollback_schema_compatible=${rollback_compatible:-no}
    if [ "$failure_stage" = "release staging" ]; then
        rollback_schema_compatible=${pre_migration_rollback_compatible:-no}
    fi
    if ! platform_service_stop; then
        die "Update failed during ${failure_stage}: ${failure_reason}. The candidate could not be stopped, so the previous release pointer was not restored. Persisted data and release pointers were retained. Verified backup: ${backup_name:-not created}. Run concierge doctor before further changes."
    fi
    if ! ln -sfn "$previous_target" "$APP_ROOT/current.next" || ! mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"; then
        die "Update failed during ${failure_stage}: ${failure_reason}. Application rollback failed. Persisted data was retained and not restored. Verified backup: ${backup_name:-not created}. Run concierge doctor before further changes."
    fi
    if [ "$rollback_schema_compatible" != yes ]; then
        die "Update failed during ${failure_stage}: ${failure_reason}. Previous release pointer restored; previous release cannot read the current database schema. The previous service was not started and the database was not downgraded. Operator recovery required. Verified backup: ${backup_name:-not created}."
    fi
    service_started=no
    if platform_service_start; then service_started=yes; fi
    health_passed=no
    if [ "$service_started" = yes ] && wait_for_health http://127.0.0.1:8080 120; then health_passed=yes; fi
    rollback_result=$("$CONCIERGE_TOOL_PYTHON" "$temporary/release/unpacked/deploy/common/update_decision.py" \
        --pointer-restored yes --service-started "$service_started" --health-passed "$health_passed" \
        --previous-schema-compatible "$rollback_schema_compatible")
    case "$rollback_result" in
        rollback_success)
            die "Update failed during ${failure_stage}: ${failure_reason}. Previous release pointer restored; previous release started successfully and passed readiness. Application rollback: SUCCESS. Persisted data was retained and not restored. Verified backup: ${backup_name:-not created}. Run concierge doctor before retrying."
            ;;
        previous_release_start_failed)
            die "Update failed during ${failure_stage}: ${failure_reason}. Previous release pointer was restored, but the service could not start. Persist