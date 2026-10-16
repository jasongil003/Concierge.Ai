#!/usr/bin/env python3
"""Small, idempotent helpers for installing a checked-out source tree."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values


PLACEHOLDER_SECRETS = {
    "",
    "change-me",
    "changeme",
    "default",
    "replace-me",
    "your-secret-here",
    "replace-with-a-random-value",
}


class InstallerError(RuntimeError):
    """An actionable source-installer failure."""


def detect_platform(
    system: str | None = None,
    *,
    os_release: Path = Path("/etc/os-release"),
    proc_version: Path = Path("/proc/version"),
    wsl_distro_name: str | None = None,
) -> tuple[str, str]:
    """Return (platform, display label), with WSL identified as a Linux path."""
    system = system or os.uname().sysname
    if system == "Darwin":
        version = ""
        sw_vers = shutil.which("sw_vers")
        if sw_vers:
            try:
                version = subprocess.check_output(
                    [sw_vers, "-productVersion"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                pass
        return "macos", f"macOS{f' {version}' if version else ''}"
    if system != "Linux":
        raise InstallerError(f"Unsupported operating system: {system}. Supported platforms are Ubuntu/Linux and macOS.")

    release: dict[str, str] = {}
    try:
        for line in os_release.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
            if match:
                release[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    distro = wsl_distro_name or release.get("PRETTY_NAME") or release.get("NAME") or "Linux"
    try:
        is_wsl = bool(wsl_distro_name) or "microsoft" in proc_version.read_text(encoding="utf-8").casefold()
    except OSError:
        is_wsl = bool(wsl_distro_name)
    if is_wsl:
        try:
            wsl2 = "wsl2" in proc_version.read_text(encoding="utf-8").casefold()
        except OSError:
            wsl2 = False
        return "linux", f"{distro} under WSL{'2' if wsl2 else ''}"
    return "linux", distro


def _read_env(path: Path) -> dict[str, str]:
    parsed = dotenv_values(path)
    return {key: value for key, value in parsed.items() if key and value is not None}


def _sqlite_admin_count(root: Path, values: dict[str, str]) -> int:
    db_path = Path(values.get("DB_PATH", "state/concierge.db")).expanduser()
    if not db_path.is_absolute():
        db_path = root / db_path
    if not db_path.is_file():
        return 0
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_users'"
            ).fetchone()
            if not table:
                return 0
            return int(db.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0])
    except sqlite3.DatabaseError:
        # Leave corrupt or unfamiliar databases untouched; application startup
        # will report the underlying database error with its normal diagnostics.
        return 0


def _is_valid_encryption_secret(secret: str) -> bool:
    folded = secret.strip().casefold()
    return len(secret.strip()) >= 32 and folded not in PLACEHOLDER_SECRETS and "replace-with" not in folded


def _is_valid_backup_encryption_key(key: str) -> bool:
    return re.fullmatch(r"[0-9a-fA-F]{64}", key.strip()) is not None


def _valid_admin_bootstrap(username: str, password: str, app_environment: str = "development") -> bool:
    # The exact built-in credentials are intentionally valid in every
    # deployment mode. Other account passwords still use the normal policy.
    if username.casefold() == "root" and password == "admin":
        return True
    return (
        len(password) >= 12
        and re.search(r"[a-z