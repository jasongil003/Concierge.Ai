#!/usr/bin/env python3
"""Read-only Concierge.AI runtime and deployment diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone


SAFE_PROFILE = {"development", "staging", "production", "test"}
SAFE_HEALTH_REASONS = {
    "Database is not ready.",
    "Redis is not ready.",
    "Required storage is not ready.",
    "Database migration required; restart with the current application to apply supported SQLite upgrades.",
    "PostgreSQL schema is not migrated; run `alembic upgrade head` before starting the API.",
    "PostgreSQL schema revision is unknown; refusing to serve traffic against unrecognized persisted state.",
    "Database schema is newer than this application build; install a compatible application release.",
    "Database migration required; run `alembic upgrade head` before starting the API.",
    "SQLite schema revision is older than this application build; refusing to mark it current without a supported migration.",
    "SQLite schema revision is not recognized; refusing to start against unknown persisted state.",
    "SQLite schema metadata could not be read safely.",
}


def detect_mode(
    *, root: Path, docker: list[dict[str, str]], services: dict[str, str], manual: list[dict[str, str]],
    in_container: bool | None = None,
) -> str:
    active_docker = [
        item for item in docker
        if not item.get("status") or item["status"].casefold().startswith(("up", "restarting", "paused"))
    ]
    docker_dev = any(
        item.get("project", "").startswith("concierge-dev-")
        or re.search(r":\d+->8080/tcp", item["ports"])
        for item in active_docker
    )
    appliance_docker = any(re.search(r":8080->80/tcp", item["ports"]) for item in active_docker)
    if docker_dev:
        return "docker-dev"
    if appliance_docker:
        return "appliance"
    if in_container is None:
        in_container = Path("/.dockerenv").exists()
    if in_container:
        return "docker-dev" if os.getenv("APP_ENVIRONMENT", "").casefold() == "development" else "appliance"
    if Path("/opt/concierge/current").exists():
        return "appliance"
    if any(value.startswith("active") for value in services.values()) or manual:
        return "source"
    return "source" if (root / "deploy" / "source_service.py").is_file() else "unknown"


def read_config(path: Path | None) -> dict[str, str]:
    """Read only non-secret settings needed for diagnosis; never print raw values."""
    if path is None:
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    allowed = {
        "APP_ENVIRONMENT", "DB_PATH", "DATABASE_URL", "UPLOAD_ROOT", "CONCIERGE_INTERNAL_PORT",
        "CONCIERGE_DEV_BIND_HOST", "CONCIERGE_DEV_PORT", "CONCIERGE_BACKUP_DIR",
        "REDIS_URL",
        "GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "COMPATIBLE_API_KEY",
    }
    secret_presence_names = {"REDIS_URL"}
    api_key_names = {
        "GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "COMPATIBLE_API_KEY",
    }
    for line in lines:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match or match.group(1) not in allowed:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        key = match.group(1)
        values[key] = ("configured" if value else "") if key in api_key_names | secret_presence_names else value
    for key in allowed:
        if key in os.environ:
            values[key] = ("configured" if os.environ[key] else "") if key in api_key_names | secret_presence_names else os.environ[key]
 