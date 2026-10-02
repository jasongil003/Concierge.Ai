#!/bin/bash
# Public release bootstrap. This file is also published as concierge-install.sh.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
if [ -f "$SCRIPT_DIR/common/runtime.sh" ]; then
    # Development checkout or extracted verified release.
    # shellcheck disable=SC1090
    . "$SCRIPT_DIR/common/runtime.sh"
else
    command -v curl >/dev/null 2>&1 || { echo "curl is required." >&2; exit 1; }
    BOOTSTRAP_TMP=$(mktemp -d "${TMPDIR:-/tmp}/concierge-bootstrap.XXXXXX")
    trap 'rm -rf "$BOOTSTRAP_TMP"' EXIT
    curl --fail --silent --show-error --location --retry 3 \
        "https://github.com/${CONCIERGE_REPOSITORY:-jasongil003/Concierge.Ai}/releases/latest/download/concierge-runtime.sh" \
        -o "$BOOTSTRAP_TMP/runtime.sh"
    # shellcheck disable=SC1090
    . "$BOOTSTRAP_TMP/runtime.sh"
fi

detect_platform
check_network
assert_space 5 /
if [ "$(id -u)" -ne 0 ]; then
    die "Run the installer with sudo so it can install machine-level services."
fi

if [ "$CONCIERGE_OS" = linux ]; then
    [ "${CONCIERGE_ARCH}" = x86_64 ] || [ "${CONCIERGE_ARCH}" = arm64 ] || die "Ubuntu target architecture must be amd64 or arm64."
else
    [ "${CONCIERGE_ARCH}" = arm64 ] || die "Production macOS appliances require Apple Silicon (arm64). Intel Macs are not a supported production target."
fi

if [ -z "${BOOTSTRAP_TMP:-}" ]; then
    BOOTSTRAP_TMP=$(mktemp -d "${TMPDIR:-/tmp}/concierge-bootstrap.XXXXXX")
    trap 'rm -rf "$BOOTSTRAP_TMP"' EXIT
fi
fetch_release "$BOOTSTRAP_TMP/release"
INSTALLER="$BOOTSTRAP_TMP/release/unpacked/deploy/${CONCIERGE_OS}/install.sh"
[ -f "$INSTALLER" ] || die "This stable release has no ${CONCIERGE_OS} installer."
bash "$INSTALLER" --release-dir "$BOOTSTRAP_TMP/release/unpacked"
