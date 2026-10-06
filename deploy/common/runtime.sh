#!/bin/bash
# Shared appliance bootstrap, release, health, and file-system helpers.

set -euo pipefail

CONCIERGE_REPOSITORY="${CONCIERGE_REPOSITORY:-jasongil003/Concierge.Ai}"
CONCIERGE_RELEASE_BASE="https://github.com/${CONCIERGE_REPOSITORY}/releases"

die() { printf 'concierge: %s\n' "$*" >&2; exit 1; }
info() { printf 'concierge: %s\n' "$*"; }

detect_platform() {
    case "$(uname -s)" in
        Linux) CONCIERGE_OS=linux ;;
        Darwin) CONCIERGE_OS=macos ;;
        *) die "Unsupported operating system: $(uname -s). Windows/WSL is development-only." ;;
    esac
    case "$(uname -m)" in
        x86_64|amd64) CONCIERGE_ARCH=x86_64 ;;
        arm64|aarch64) CONCIERGE_ARCH=arm64 ;;
        *) die "Unsupported architecture: $(uname -m)." ;;
    esac
    if [ "$CONCIERGE_OS" = macos ]; then
        if /usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null | grep -qx '1'; then
            CONCIERGE_ARCH=arm64
        fi
        CONCIERGE_CHIP=$(/usr/sbin/sysctl -n machdep.cpu.brand_string 2>/dev/null || /usr/sbin/sysctl -n hw.model)
        CONCIERGE_RAM_BYTES=$(/usr/sbin/sysctl -n hw.memsize)
    else
        CONCIERGE_CHIP=$(awk -F: '/model name|Hardware|Model/ {gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null || true)
        [ -n "$CONCIERGE_CHIP" ] || CONCIERGE_CHIP="$(uname -m) CPU"
        CONCIERGE_RAM_BYTES=$(( $(awk '/MemTotal:/ {print $2}' /proc/meminfo) * 1024 ))
    fi
    CONCIERGE_RAM_GIB=$(( CONCIERGE_RAM_BYTES / 1024 / 1024 / 1024 ))
    CONCIERGE_DISK_KIB=$(df -Pk / | awk 'NR == 2 {print $4}')
    CONCIERGE_DISK_GIB=$(( CONCIERGE_DISK_KIB / 1024 / 1024 ))

    if [ "$CONCIERGE_OS" = linux ] && command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
        CONCIERGE_ACCELERATOR="NVIDIA GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
    elif [ "$CONCIERGE_OS" = macos ] && [ "$CONCIERGE_ARCH" = arm64 ]; then
        CONCIERGE_ACCELERATOR="Apple Silicon unified memory"
    else
        CONCIERGE_ACCELERATOR="CPU inference"
    fi

    info "host: OS=$CONCIERGE_OS arch=$CONCIERGE_ARCH chip=$CONCIERGE_CHIP RAM=${CONCIERGE_RAM_GIB}GiB disk-free=${CONCIERGE_DISK_GIB}GiB accelerator=$CONCIERGE_ACCELERATOR"
    if [ "$CONCIERGE_RAM_GIB" -lt 8 ]; then
        info "local AI: not advisable at this memory size; Concierge works without local AI."
    elif [ "$CONCIERGE_RAM_GIB" -lt 16 ]; then
        info "local AI: small quantized models may fit; use a remote provider or disable local AI for predictable capacity."
    else
        info "local AI: optional and potentially suitable; benchmark before selecting a model."
    fi
}

check_network() {
    command -v curl >/dev/null 2>&1 || die "curl is required to download a verified release."
    curl --fail --silent --show-error --location --connect-timeout 10 --max-time 30 \
        --output /dev/null https://github.com
    info "network: GitHub is reachable"
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        die "Neither sha256sum nor shasum is available."
    fi
}

fetch_release() {
    release_dir=$1
    mkdir -p "$release_dir"
    metadata="$release_dir/concierge-release.env"
    curl --fail --silent --show-error --location --retry 3 \
        "${CONCIERGE_RELEASE_BASE}/latest/download/concierge-release.env" -o "$metadata" || \
        die "No published stable release is available at ${CONCIERGE_RELEASE_BASE}/latest."

    version=$(awk -F= '$1 == "VERSION" {print $2; exit}' "$metadata")
    artifact=$(awk -F= '$1 == "ARTIFACT" {print $2; exit}' "$metadata")
    expected_sha=$(awk -F= '$1 == "SHA256" {print $2; exit}' "$metadata")
    commit=$(awk -F= '$1 == "COMMIT" {print $2; exit}' "$metadata")
    build_date=$(awk -F= '$1 == "BUILD_DATE" {print $2; exit}' "$metadata")
    printf '%s' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || die "Release metadata has an invalid VERSION."
    [ "$artifact" = "concierge-ai-${version}.tar.gz" ] || die "Release metadata has an invalid ARTIFACT."
    printf '%s' "$expected_sha" | grep -Eq '^[0-9a-fA-F]{64}$' || die "Release metadata has an invalid SHA256."
    printf '%s' "$commit" | grep -Eq '^[0-9a-fA-F]{7,40}$' || die "Release metadata has an invalid COMMIT."

    archive="$release_dir/$artifact"
    curl --fail --silent --show-error --location --retry 3 \
        "${CONCIERGE_RELEASE_BASE}/download/v${version}/${artifact}" -o "$archive" || \
        die "Could not download stable release v${version}."
    actual_sha=$(sha256_file "$archive")
    actual_sha=$(printf '%s' "$actual_sha" | tr '[:upper:]' '[:lower:]')
    expected_sha=$(printf '%s' "$expected_sha" | tr '[:upper:]' '[:lower:]')
    [ "$actual_sha" = "$expected_sha" ] || die "SHA-256 verification failed for $artifact."
    tar -tzf "$archive" | awk 'BEGIN {bad=0} /^\// || /(^|\/)\.\.(\/|$)/ {bad=1} END {exit bad}' || \
        die "Release archive contains an unsafe path."
    mkdir -p "$release_dir/unpacked"
    tar -xzf "$archive" -C "$release_dir/unpacked"
    [ -f "$release_dir/unpacked/deploy/install.sh" ] || die "Release archive is missing deploy/install.sh."
    printf '%s\n' "$version" > "$release_dir/unpacked/RELEASE_VERSION"
    printf '%s\n' "$commit" > "$release_dir/unpacked/RELEASE_COMMIT"
    if printf '%s' "$build_date" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'; then
        printf '%s\n' "$build_date" > "$release_dir/unpacked/RELEASE_BUILD_DATE"
    fi
    info "release: v${version} (${commit:0:12}), SHA-256 verified"
}

wait_for_health() {
    base_url=${1:-http://127.0.0.1:8080}
    max_seconds=${2:-120}
    index=0
    while [ "$index" -lt "$max_seconds" ]; do
        if curl --fail --silent --show-error --max-time 3 "$base_url/health/live" >/dev/null 2>&1 && \
           curl --fail --silent --show-error --max-time 3 "$base_url/health/ready" >/dev/null 2>&1; then
            info "health: live and ready at ${base_url}"
            return 0
        fi
        sleep 1
        index=$((index + 1))
    done
    return 1
}

assert_space() {
    required_gib=${1:-5}
    target=${2:-/}
    while [ ! -e "$target" ]; do
        target=$(dirname "$target")
    done
    available_kib=$(df -Pk "$target" | awk 'NR == 2 {print $4}')
    available_gib=$((available_kib / 1024 / 1024))
    [ "$available_gib" -ge "$required_gib" ] || die "At least ${required_gib} GiB free space is required on $target (found ${available_gib} GiB)."
}
