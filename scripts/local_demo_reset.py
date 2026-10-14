#!/usr/bin/env python3
"""Remove only state that this checkout's local-demo launcher owns."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    demo = root / ".local-demo"
    expected_state = demo / "state"
    expected_uploads = demo / "uploads"
    expected_database = expected_state / "concierge.db"

    checks = {
        "DEMO_MODE": os.environ.get("DEMO_MODE") == "true",
        "CONCIERGE_LOCAL_DEMO": os.environ.get("CONCIERGE_LOCAL_DEMO") == "1",
        "APP_ENVIRONMENT": os.environ.get("APP_ENVIRONMENT") == "development",
        "CONCIERGE_DEPLOYMENT_MODE": os.environ.get("CONCIERGE_DEPLOYMENT_MODE") == "source",
        "DATABASE_URL": not os.environ.get("DATABASE_URL", "").strip(),
        "DB_PATH": Path(os.environ.get("DB_PATH", "")).expanduser().resolve() == expected_database.resolve(),
        "UPLOAD_ROOT": Path(os.environ.get("UPLOAD_ROOT", "")).expanduser().resolve() == expected_uploads.resolve(),
    }
    if not all(checks.values()):
        failures = ", ".join(name for name, valid in checks.items() if not valid)
        print(f"Refusing to reset; local-demo safety checks failed: {failures}", file=sys.stderr)
        return 2

    marker = demo / "DEMO_STATE"
    expected_marker = f"Concierge.AI local demo state v1\nrepo={root}\n"
    if demo.is_symlink() or demo.resolve().parent != root.resolve():
        print("Refusing to reset; .local-demo is not a real directory inside this checkout.", file=sys.stderr)
        return 2
    if not marker.is_file() or marker.is_symlink() or marker.read_text(encoding="utf-8") != expected_marker:
        print("Refusing to reset; the checkout-owned demo marker is missing or invalid.", file=sys.stderr)
        return 2

    for path, expected_parent in ((expected_state, demo), (expected_uploads, demo)):
        if path.is_symlink():
            print(f"Refusing to reset symlinked demo path: {path}", file=sys.stderr)
            return 2
        if path.exists():
            resolved = path.resolve()
            if resolved.parent != expected_parent.resolve() or resolved == root.resolve():
                print(f"Refusing to reset path outside the demo directory: {path}", file=sys.stderr)
                return 2
        elif path.parent.resolve() != expected_parent.resolve():
            print(f"Refusing to create/reset path outside the demo directory: {path}", file=sys.stderr)
            return 2

    for path in (expected_state, expected_uploads):
        if path.exists():
            shutil.rmtree(path)
    expected_state.mkdir(parents=True, exist_ok=True)
    expected_uploads.mkdir(parents=True, exist_ok=True)
    print(f"Reset only {expected_state} and {expected_uploads}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
