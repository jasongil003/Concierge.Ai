#!/usr/bin/env python3
"""Create the repository-local virtual environment without external packages."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import venv
from pathlib import Path


def supported_python(version: tuple[int, int] | None = None) -> bool:
    version = version or sys.version_info[:2]
    return (3, 11) <= version <= (3, 14)


def ensure_venv(root: Path) -> str:
    root = root.resolve()
    venv_dir = root / ".venv"
    venv_python = venv_dir / "bin" / "python"
    if venv_python.is_file():
        return "existing"
    if venv_dir.exists():
        raise RuntimeError("Found an incomplete .venv directory. Inspect it and move it aside before rerunning ./install.sh.")
    try:
        # POSIX Python builds can fail when copied to a venv path; match the
        # platform's usual `python -m venv` symlink behavior instead.
        venv.EnvBuilder(with_pip=True, symlinks=(os.name != "nt")).create(venv_dir)
    except Exception as exc:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise RuntimeError(f"Could not create .venv with pip using Python {sys.version_info.major}.{sys.version_info.minor}: {exc}") from exc
    if not venv_python.is_file():
        raise RuntimeError("Python venv creation completed without .venv/bin/python.")
    return "created"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "create"))
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.command == "check":
        print(f"{sys.version_info.major}.{sys.version_info.minor}")
        return 0 if supported_python() else 1
    if args.root is None:
        parser.error("create requires --root")
    try:
        print(ensure_venv(args.root))
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Virtual environment error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
