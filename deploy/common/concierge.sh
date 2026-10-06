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
    archive_name="concierge-${stamp}.zip"
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
            die "Update failed during ${failure_stage}: ${failure_reason}. Previous release pointer was restored, but the service could not start. Persisted data was retained. Verified backup: ${backup_name:-not created}. Run concierge doctor."
            ;;
        operator_recovery_required_schema_incompatible)
            die "Update failed during ${failure_stage}: ${failure_reason}. Previous release cannot read the migrated database schema. The previous release pointer was restored, but the service was not started and no database downgrade was attempted. Operator recovery required. Verified backup: ${backup_name:-not created}."
            ;;
        previous_release_unhealthy)
            die "Update failed during ${failure_stage}: ${failure_reason}. Previous release pointer restored and the previous release started successfully, but its readiness check failed. Persisted data was retained and not restored. Operator recovery required. Verified backup: ${backup_name:-not created}."
            ;;
        *)
            die "Update failed during ${failure_stage}: ${failure_reason}. Previous release pointer was restored, but rollback readiness FAILED. Persisted data was retained and not restored. Verified backup: ${backup_name:-not created}. Run concierge doctor and use the backup only through a planned recovery."
            ;;
    esac
}

update_release() {
    require_root
    allow_incompatible_rollback=no
    for option in "$@"; do
        case "$option" in
            --allow-incompatible-rollback) allow_incompatible_rollback=yes ;;
            *) die "Usage: sudo concierge update [--allow-incompatible-rollback]" ;;
        esac
    done
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
    platform_runtime_preflight || die "Update preflight failed. No service or application data was changed. Run concierge doctor, resolve any runtime/port conflict, then retry."
    previous_target=$(readlink "$APP_ROOT/current")
    previous_dir=$(cd "$APP_RELEASE" && pwd -P)
    if [ -r "$CONFIG_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        . "$CONFIG_FILE"
        set +a
    fi
    case "${DATABASE_URL:-}" in
        postgresql:*|postgresql+*:*|postgres:*) database_type=postgresql ;;
        ""|sqlite:*|sqlite+*:* ) database_type=sqlite ;;
        *) die "Update schema preflight cannot identify the configured database type; no changes were made." ;;
    esac
    current_schema=$(platform_schema_revision) || \
        die "Update schema preflight failed while reading the local database schema. No service or database changes were made."
    [ -n "$current_schema" ] && [ "$current_schema" != unavailable ] || \
        die "Update schema preflight failed: active database schema is unknown. No changes were made."
    assessment_args=(assess --current-schema "$current_schema" --database-type "$database_type" \
        --candidate "$temporary/release/unpacked" --previous "$previous_dir")
    if [ "$allow_incompatible_rollback" = yes ]; then
        assessment_args+=(--allow-incompatible-rollback)
    fi
    assessment=$("$CONCIERGE_TOOL_PYTHON" "$temporary/release/unpacked/deploy/common/schema_compatibility.py" "${assessment_args[@]}") || \
        die "Update schema preflight failed while evaluating release metadata. No changes were made."
    can_update=$(printf '%s' "$assessment" | "$CONCIERGE_TOOL_PYTHON" -c 'import json,sys; print("yes" if json.load(sys.stdin).get("can_update") else "no")')
    rollback_compatible=$(printf '%s' "$assessment" | "$CONCIERGE_TOOL_PYTHON" -c 'import json,sys; print("yes" if json.load(sys.stdin).get("rollback_compatible") else "no")')
    pre_migration_rollback_compatible=$(printf '%s' "$assessment" | "$CONCIERGE_TOOL_PYTHON" -c 'import json,sys; print("yes" if json.load(sys.stdin).get("pre_migration_rollback_compatible") else "no")')
    migration_required=$(printf '%s' "$assessment" | "$CONCIERGE_TOOL_PYTHON" -c 'import json,sys; print("yes" if json.load(sys.stdin).get("migration_required") else "no")')
    preflight_reason=$(printf '%s' "$assessment" | "$CONCIERGE_TOOL_PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("reason", "Schema compatibility check failed."))')
    rollback_warning=$(printf '%s' "$assessment" | "$CONCIERGE_TOOL_PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("rollback_warning", ""))')
    if [ -n "$rollback_warning" ]; then
        info "$rollback_warning"
    fi
    if [ "$can_update" != yes ]; then
        die "Update schema preflight blocked v${new_version}: ${preflight_reason} No service, pointer, or database changes were made."
    fi
    if [ "$rollback_compatible" != yes ] && [ "$allow_incompatible_rollback" = yes ]; then
        info "Rollback compatibility override requested; a verified backup is required before migration."
    fi
    if [ "$migration_required" = yes ]; then
        info "database schema: migration required to $(cat "$temporary/release/unpacked/RELEASE_SCHEMA_REVISION")"
    else
        info "database schema: migration not required"
    fi
    if make_backup; then
        :
    else
        backup_result=$?
        case "$backup_result" in
            31) die "Update failed during backup creation; no service or database changes were made." ;;
            32) die "Update failed during backup verification; refusing to update. No service or database changes were made." ;;
            *) die "Update failed during backup; refusing to update. No service or database changes were made." ;;
        esac
    fi
    backup_name="$BACKUP_ROOT/$archive_name"
    if ! platform_service_stop; then
        die "Update aborted during service stop. The current release pointer and persisted data were not changed; service state may need attention. Verified backup: ${backup_name:-not created}. Run concierge doctor."
    fi
    if ! platform_install_release "$temporary/release/unpacked"; then
        restore_previous_release "release staging" "candidate release could not be installed"
    fi
    if ! platform_migrate; then
        restore_previous_release "migration failed" "database initialization or migration failed"
    fi
    if ! platform_service_start; then
        restore_previous_release "candidate startup" "the service manager could not start the candidate release"
    fi
    if ! wait_for_health http://127.0.0.1:8080 180; then
        restore_previous_release "readiness validation" "candidate did not pass live and ready checks"
    fi
    platform_record_manifest || die "The new release is healthy, but deployment metadata could not be recorded. Active version: v${new_version}. Run concierge doctor."
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
        database_schema_revision=$(platform_schema_revision 2>/dev/null || printf unknown)
        "$CONCIERGE_TOOL_PYTHON" "$APP_RELEASE/deploy/common/diagnostics.py" status \
            --mode appliance --root "$APP_RELEASE" --config "$CONFIG_FILE" \
            --state-directory "$STATE_ROOT" --base-url http://127.0.0.1:8080 --bind 127.0.0.1 \
            --database-schema-revision "$database_schema_revision"
        ;;
    doctor)
        database_schema_revision=$(platform_schema_revision 2>/dev/null || printf unknown)
        "$CONCIERGE_TOOL_PYTHON" "$APP_RELEASE/deploy/common/diagnostics.py" doctor \
            --mode appliance --root "$APP_RELEASE" --config "$CONFIG_FILE" \
            --state-directory "$STATE_ROOT" --base-url http://127.0.0.1:8080 --bind 127.0.0.1 \
            --database-schema-revision "$database_schema_revision"
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
Usage: concierge {status|doctor|health|backup|update|local-ai ...|boot-test {prepare|verify}}
System jobs: internal-serve, internal-stop, internal-health, internal-backup, internal-maintenance
EOF
        exit 2
        ;;
esac
