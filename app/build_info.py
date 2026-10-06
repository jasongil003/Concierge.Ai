"""Safe application build identity shared by health and backup metadata."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys


_SAFE_VERSION = re.compile(r"^(?:[vV]?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*|[A-Fa-f0-9]{7,40}|local|unknown)$")
_SAFE_COMMIT = re.compile(r"^(?:[A-Fa-f0-9]{7,40}|unknown)$")
_SAFE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")


def _release_file(name: str) -> str | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / name
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if _SAFE_VERSION.fullmatch(value) or _SAFE_COMMIT.fullmatch(value):
            return value
    return None


def _version(value: str | None) -> str:
    value = (value or "").strip()
    return value if _SAFE_VERSION.fullmatch(value) else "unknown"


def _commit(value: str | None) -> str:
    value = (value or "").strip()
    return value if _SAFE_COMMIT.fullmatch(value) else "unknown"


def deployment_mode() -> str:
    configured = os.getenv("CONCIERGE_DEPLOYMENT_MODE", "").strip()
    if configured not in {"source", "docker-dev", "appliance", "docker-production"}:
        configured = "unknown"
    if configured != "unknown":
        return configured
    if Path("/.dockerenv").exists():
        return "docker-dev" if os.getenv("APP_ENVIRONMENT", "").casefold() == "development" else "appliance"
    if Path("/opt/concierge/current").exists():
        return "appliance"
    return "source"


def _git_value(*arguments: str) -> str | None:
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=root, check=True, capture_output=True, text=True, timeout=1,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError, TypeError):
        return None
    value = result.stdout.strip()
    return value if _SAFE_COMMIT.fullmatch(value) or _SAFE_VERSION.fullmatch(value) else None


def _git_timestamp() -> str | None:
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%cI", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError, TypeError):
        return None
    value = result.stdout.strip()
    return value if _SAFE_TIMESTAMP.fullmatch(value) else None


def build_identity() -> dict[str, str]:
    version = _version(os.getenv("CONCIERGE_VERSION"))
    commit = _commit(os.getenv("CONCIERGE_COMMIT"))
    if version == "unknown":
        version = _version(_release_file("RELEASE_VERSION"))
    if version == "unknown":
        version = _version(_git_value("describe", "--tags", "--always", "--dirty"))
    if commit == "unknown":
        commit = _commit(_release_file("RELEASE_COMMIT"))
    if commit == "unknown":
        commit = _commit(_git_value("rev-parse", "--short=12", "HEAD"))
    build_date = os.getenv("CONCIERGE_BUILD_DATE", "").strip()
    if not _SAFE_TIMESTAMP.fullmatch(build_date):
        build_date = _release_file("RELEASE_BUILD_DATE") or ""
    if not _SAFE_TIMESTAMP.fullmatch(build_date):
        build_date = _git_timestamp() or ""
    if not _SAFE_TIMESTAMP.fullmatch(build_date):
        build_date = "unknown"
    profile = os.getenv("APP_ENVIRONMENT", "unknown").strip().casefold()
    if profile not in {"development", "staging", "production", "test"}:
        profile = "unknown"
    return {
        "version": version if version != "unknown" else "0.0.0+source",
        "commit": commit,
        "build_date": build_date,
        "deployment_mode": deployment_mode(),
        "profile": profile,
        "runtime": "python",
        "python_version": sys.version.split()[0],
    }


# Build identity and process environment are immutable for a running release.
BUILD_IDENTITY = build_identity()
