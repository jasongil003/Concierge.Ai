#!/bin/bash

PLATFORM_NAME=linux-systemd
APP_ROOT=/opt/concierge
export STATE_ROOT=/var/lib/concierge
BACKUP_ROOT=/var/backups/concierge
CONFIG_FILE=/etc/concierge/concierge.env
EVENT_LOG=/var/lib/concierge/recovery-events.jsonl
RECOVERY_STATE=/var/lib/concierge/recovery-state.json
RECOVERY_RESTART_COMMAND=(systemctl restart concierge.service)

platform_service_start() { systemctl start concierge.service; }
platform_service_restart() { systemctl restart concierge.service; }
platform_service_stop() { systemctl stop concierge.service; }
platform_service_status() { systemctl --no-pager --full status concierge.service; }
platform_active() { systemctl is-active --quiet concierge.service; }

platform_compose() {
    version=$(cat /opt/concierge/current/RELEASE_VERSION)
    CONCIERGE_CONFIG_FILE="$CONFIG_FILE" CONCIERGE_VERSION="$version" \
        docker compose --project-name concierge --project-directory /opt/concierge/current \
        --env-file "$CONFIG_FILE" -f /opt/concierge/current/docker-compose.yml "$@"
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
    ln -sfn "$target" "$APP_ROOT/current.next"
    mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"
    platform_compose config --quiet
    systemctl daemon-reload
}

platform_backup_create() {
    archive_name=$1
    platform_compose exec -T concierge python -m app.backup create "/backups/$archive_name" >/dev/null
}

platform_backup_verify() {
    archive_path=$1
    platform_compose exec -T concierge python -m app.backup verify "/backups/$(basename "$archive_path")" >/dev/null
}

platform_retention() {
    find "$BACKUP_ROOT" -type f -name 'concierge-*.zip' -mtime +30 -delete
    current=$(readlink "$APP_ROOT/current")
    ls -1dt "$APP_ROOT"/releases/*/ 2>/dev/null | tail -n +4 | while IFS= read -r old_release; do
        old_release=${old_release%/}
        [ "$old_release" = "$current" ] || rm -rf "$old_release"
    done
}

platform_restart_command() { systemctl restart concierge.service; }

platform_internal_serve() {
    platform_compose up --build --remove-orphans
}

platform_internal_stop() {
    platform_compose down --timeout 45
}

platform_migrate() {
    platform_compose build concierge
    platform_compose run --rm --no-deps concierge python -c 'import app.main'
}

platform_internal_health() {
    python3 /opt/concierge/current/deploy/common/ops.py recover \
        --platform "$PLATFORM_NAME" --event-log "$EVENT_LOG" --state-file "$RECOVERY_STATE" \
        --max-restarts 3 --window-seconds 900 --post-restart-wait 45 \
        -- "${RECOVERY_RESTART_COMMAND[@]}"
}

platform_local_ai_status() {
    curl --fail --silent --show-error --max-time 2 http://127.0.0.1:11434/api/tags
}

platform_boot_id() { cat /proc/sys/kernel/random/boot_id; }

platform_data_signature() {
    platform_compose exec -T concierge python -c 'import hashlib,json; from app.config import settings; from app.properties import PropertyStore; records=[r.to_dict(include_secrets=True) for r in PropertyStore(settings.db_path).list()]; print(json.dumps({"count":len(records),"signature":hashlib.sha256(json.dumps(records,sort_keys=True,separators=(",",":")).encode()).hexdigest()}))'
}

platform_boot_components() {
    systemctl is-active --quiet docker.service
    systemctl is-active --quiet concierge.service
    services=$(platform_compose ps --status running --services)
    printf '%s\n' "$services" | grep -qx concierge || return 1
    printf '%s\n' "$services" | grep -qx proxy || return 1
}
