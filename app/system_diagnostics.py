"""Sanitized read-only runtime metadata for authenticated administrator diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import zipfile


_VERSION = re.compile(r"^(?:[vV]?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*|[A-Fa-f0-9]{7,40}|local|unknown)$")
_COMMIT = re.compile(r"^(?:[A-Fa-f0-9]{7,40}|unknown)$")
_SCHEMA = re.compile(r"^(?:\d{8}_\d{4}|unknown|unavailable)$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)$")


def _safe_string(value: object, pattern: re.Pattern[str]) -> str:
    return value if isinstance(value, str) and len(value) <= 128 and pattern.fullmatch(value) else "unknown"


def _safe_timestamp(value: object) -> str:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        return "unknown"
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    return value


def last_update(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unknown", "updated_at": "unknown", "version": "unknown", "commit": "unknown"}
    if not isinstance(value, dict):
        value = {}
    updated_at = _safe_timestamp(value.get("updated_at"))
    return {
        "status": "available" if updated_at != "unknown" else "unknown",
        "updated_at": updated_at,
        "version": _safe_string(value.get("version"), _VERSION),
        "commit": _safe_string(value.get("commit"), _COMMIT),
    }


def last_backup(directory: Path | None) -> dict[str, object]:
    if directory is None or not directory.is_dir():
        return {"status": "unknown"}
    archives = sorted(directory.glob("concierge-*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    for archive_path in archives[:20]:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                info = archive.getinfo("manifest.json")
                if info.file_size > 1024 * 1024:
                    continue
                manifest = json.loads(archive.read("manifest.json"))
            identity = manifest.get("concierge", {}) if isinstance(manifest, dict) else {}
            created_at = manifest.get("created_at") if isinstance(manifest, dict) else None
            if not isinstance(created_at, int) or created_at < 0:
                continue
            return {
                "status": "available",
                "created_at": datetime.fromtimestamp(created_at, timezone.utc).isoformat(timespec="seconds"),
                "version": _safe_string(identity.get("version"), _VERSION) if isinstance(identity, dict) else "unknown",
                "schema_revision": _safe_string(identity.get("schema_revision"), _SCHEMA) if isinstance(identity, dict) else "unknown",
            }
        except (OSError, ValueError, KeyError, TypeError, OverflowError, zipfile.BadZipFile):
            continue
    return {"status": "unknown"}


def provider_health(properties: list[object], store: object) -> dict[str, int | str]:
    summary: dict[str, int | str] = {"configured": 0, "healthy": 0, "unavailable": 0, "unknown": 0}
    for property_record in properties:
        property_id = getattr(property_record, "property_id", "")
        if not isinstance(property_id, str) or not property_id:
            continue
        try:
            connections = store.list_connections(property_id)
        except Exception:
            summary["unknown"] = int(summary["unknown"]) + 1
            continue
        for connection in connections:
            if not isinstance(connection, dict) or not connection.get("enabled"):
                continue
            status = connection.get("status")
            if not isinstance(status, str):
                status = ""
            if status in {"not_configured", "local"}:
                continue
            summary["configured"] = int(summary["configured"]) + 1
            if status in {"connected", "healthy", "ready"}:
                summary["healthy"] = int(summary["healthy"]) + 1
            elif status in {"failed", "error", "unavailable"}:
                summary["unavailable"] = int(summary["unavailable"]) + 1
            else:
                summary["unknown"] = int(summary["unknown"]) + 1
    if int(summary["unavailable"]):
        summary["status"] = "degraded"
    elif int(summary["unknown"]):
        summary["status"] = "unknown"
    elif int(summary["configured"]) == int(summary["healthy"]):
        summary["status"] = "healthy"
    else:
        summary["status"] = "not_configured"
    return summary


def backup_directory(deployment_mode: str, *, configured: str = "") -> Path | None:
    candidate = configured or os.getenv("CONCIERGE_BACKUP_DIR", "").strip()
    if candidate:
        return Path(candidate).expanduser()
    if deployment_mode == "appliance":
        if sys.platform == "darwin":
            return Path("/Library/Application Support/Concierge.AI/Backups")
        return Path("/var/backups/concierge")
    return None


def process_uptime(started_monotonic: float, now_monotonic: float | None = None) -> int:
    now = time.monotonic() if now_monotonic is None else now_monotonic
    return max(0, int(now - started_monotonic))
