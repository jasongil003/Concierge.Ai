#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ORIGINAL_ARGS=("$@")
# shellcheck source=../common/runtime.sh
. "$SCRIPT_DIR/../common/runtime.sh"
# shellcheck source=../common/configure.sh
. "$SCRIPT_DIR/../common/configure.sh"
detect_platform

release_dir=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --release-dir) release_dir=$2; shift 2 ;;
        *) die "Unknown argument: $1" ;;
    esac
done
[ -n "$release_dir" ] && [ -f "$release_dir/RELEASE_VERSION" ] || die "A verified release directory is required."
[ "$(id -u)" -eq 0 ] || die "Run with sudo."

python3 "$release_dir/deploy/common/preflight.py" appliance --port 8080

if [ "${CONCIERGE_OPERATION_LOCK_HELD:-}" != 1 ]; then
    python3 "$release_dir/deploy/common/operation_lock.py" run \
        --lock /opt/concierge/.deployment.lock -- "$0" "${ORIGINAL_ARGS[@]}"
    exit $?
fi

python3 "$release_dir/deploy/common/preflight.py" appliance --port 8080

if [ -e /opt/concierge/current ] || [ -L /opt/concierge/current ]; then
    die "An appliance release already exists at /opt/concierge/current. Use 'sudo concierge update' to upgrade; no installed release or persisted state was changed."
fi

[ -r /etc/os-release ] || die "This installer supports Ubuntu Server 24.04 LTS and 26.04 LTS only."
. /etc/os-release
[ "${ID:-}" = ubuntu ] && { [ "${VERSION_ID:-}" = 24.04 ] || [ "${VERSION_ID:-}" = 26.04 ]; } || \
    die "Supported OS targets are Ubuntu Server 24.04 LTS and 26.04 LTS."
case "$CONCIERGE_ARCH" in x86_64|arm64) ;; *) die "Only amd64/x86_64 and arm64/aarch64 are supported." ;; esac
assert_space 8 /opt

getent group concierge >/dev/null || groupadd --system concierge
id concierge >/dev/null 2>&1 || useradd --system --gid concierge --home-dir /nonexistent --shell /usr/sbin/nologin concierge
mkdir -p /opt/concierge/releases /var/lib/concierge /var/backups/concierge /etc/concierge /etc/systemd/system
chown -R concierge:concierge /var/lib/concierge /var/backups/concierge
chmod 0750 /var/lib/concierge /var/backups/concierge
chown 10001:10001 /var/backups/concierge
chmod 0700 /var/backups/concierge
generate_config /etc/concierge/concierge.env /var/lib/concierge /var/backups/concierge '172.29.0.2,172.29.0.1/32,127.0.0.1/32,::1/128' 'http://host.docker.internal:11434' concierge

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl docker.io docker-compose-v2 python3 unattended-upgrades
systemctl enable --now docker.service
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer

release_version=$(cat "$release_dir/RELEASE_VERSION")
APP_ROOT=/opt/concierge
mkdir -p "$APP_ROOT/releases/$release_version"
cp -R "$release_dir"/. "$APP_ROOT/releases/$release_version/"
chmod -R go-w "$APP_ROOT/releases/$release_version"
ln -sfn "$APP_ROOT/releases/$release_version" "$APP_ROOT/current.next"
mv -f "$APP_ROOT/current.next" "$APP_ROOT/current"
install -o root -g root -m 0755 "$APP_ROOT/current/deploy/common/concierge" /usr/local/bin/concierge
install -o root -g root -m 0644 "$APP_ROOT/current"/deploy/linux/*.service "$APP_ROOT/current"/deploy/linux/*.timer /etc/systemd/system/
chmod 0640 /etc/concierge/concierge.env
systemctl daemon-reload
systemctl enable concierge.service concierge-health.timer concierge-backup.timer concierge-maintenance.timer
systemctl start concierge.service concierge-health.timer concierge-backup.timer concierge-maintenance.timer

if ! wait_for_health http://127.0.0.1:8080 180; then
    die "Installation reached service startup but health validation failed; installed files and persisted state were retained. Run 'sudo concierge doctor' and inspect 'sudo journalctl -u concierge.service'."
fi
admin_status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
    -H 'Host: 127.0.0.1' http://127.0.0.1:8080/admin/login || true)
[ "$admin_status" = 200 ] || die "The localhost Admin endpoint returned HTTP $admin_status."
platform_record_manifest
release_commit=$(cat /opt/concierge/current/RELEASE_COMMIT 2>/dev/null || printf unknown)
info "installation completed; health validation passed."
info "deployment mode: appliance  version: v${release_version}  commit: ${release_commit}"
info "Admin URL: http://127.0.0.1:8080/admin/login  internal URL: http://127.0.0.1:8080"
info "service: concierge.service  state: /var/lib/concierge  health: READY"
info "diagnostics: sudo concierge status  |  sudo concierge doctor"
