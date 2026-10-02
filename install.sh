#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
if ! command -v git >/dev/null 2>&1 || ! git -C "$ROOT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    printf 'Error: ./install.sh must run from a Git checkout of Concierge.AI.\n' >&2
    exit 1
fi
CHECKOUT_ROOT=$(git -C "$ROOT_DIR" rev-parse --show-toplevel)
if [[ "$CHECKOUT_ROOT" != "$ROOT_DIR" ]]; then
    printf 'Error: run ./install.sh from the root of the Concierge.AI Git checkout.\n' >&2
    exit 1
fi
exec bash "$ROOT_DIR/deploy/source-install.sh" "$@"
