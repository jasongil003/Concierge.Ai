#!/usr/bin/env python3
"""Atomically record non-secret installation metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
VERSION = re.compile(r"^(?:[vV]?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*|[A-Fa-f0-9]{7,40}|local|unknown)$")
COMMIT = re.compile(r"^(?:[A-Fa-f0-9]{7,40}|unknown)$")
REVISION = re.compile(r"^\d{8}_\d{4}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = result.stdout.strip()
    return value if SAFE.fullmatch(value) else "unknown"


def _identity_metadata(root: Path, filename: str, env_key: str, pattern: re.Pattern[str], git_args: tuple[str, ...]) -> str:
    value = os.getenv(env_key, "").strip()
    if not pattern.fullmatch(value):
        try:
            value = (root / filename).read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
    if not pattern.fullmatch(value):
        value = _git(root, *git_args)
    return value if pattern.fullmatch(value) else "unknown"


def write_manifest(path: Path, root: Path, mode: str) -> dict[str, str]:
    root = root.resolve()
    version = _identity_metadata(root, "RELEASE_VERSION", "CONCIERGE_VERSION", VERSION, ("describe", "--tags", "--always", "--dirty"))
    commit = _identity_metadata(root, "RELEASE_COMMIT", "CONCIERGE_COMMIT", COMMIT, ("rev-parse", "--short=12", "HEAD"))
    try:
        source = (root / "app" / "database.py").read_text(encoding="utf-8")
    except OSError:
        source = ""
    match = re.search(r'^CURRENT_SCHEMA_REVISION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    schema_revision = match.group(1) if match and REVISION.fullmatch(match.group(1)) else "unknown"
    if mode not in {"source", "docker-dev", "appliance", "docker-production"}:
        raise ValueError("Deployment mode contains unsupported characters.")
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = {}
    installed_at = previous.get("installed_at") if isinstance(previous, dict) else None
    if not isinstance(installed_at, str) or not TIMESTAMP.fullmatch(installed_at):
        installed_at = now
    data = {
        "manifest_version": "1",
        "version": version,
        "commit": commit,
        "deployment_mode": mode,
        "installed_at": installed_at,
        "updated_at": now,
        "schema_revision": schema_revision,
        "installer_version": "1",
    }
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    result = write_manifest(args.path, args.root, args.mode)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
