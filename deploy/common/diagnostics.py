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
    return values


def _sqlite_ai_credentials(path: Path | None) -> bool | None:
    if path is None or not path.is_file():
        return None
    import sqlite3

    try:
        with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=1) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_credentials'"
            ).fetchone()
            if not exists:
                return False
            return bool(db.execute("SELECT 1 FROM provider_credentials LIMIT 1").fetchone())
    except sqlite3.Error:
        return None


def _latest_backup(directory: Path | None) -> dict[str, str]:
    if directory is None or not directory.is_dir():
        return {"status": "unknown", "created_at": "unknown", "version": "unknown"}
    try:
        backups = sorted(directory.glob("concierge-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        backups = []
    for path in backups[:20]:
        try:
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("manifest.json")
                if info.file_size > 1024 * 1024:
                    continue
                manifest = json.loads(archive.read("manifest.json"))
            created = manifest.get("created_at")
            if not isinstance(created, int) or created < 0:
                continue
            identity = manifest.get("concierge", {})
            version = identity.get("version") if isinstance(identity, dict) else None
            if not isinstance(version, str) or not re.fullmatch(r"(?:[vV]?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*|[A-Fa-f0-9]{7,40}|local|unknown)", version):
                version = "unknown"
            return {
                "status": "available",
                "created_at": datetime.fromtimestamp(created, timezone.utc).isoformat(timespec="seconds"),
                "version": version,
            }
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, OverflowError):
            continue
    return {"status": "unknown", "created_at": "unknown", "version": "unknown"}


def _run(command: list[str], timeout: float = 2.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _service_state(command: list[str]) -> str:
    result = _run(command)
    if result is None or result.returncode:
        return "not detected"
    output = result.stdout.strip()
    if command[0] == "systemctl":
        values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if values.get("LoadState") == "not-found" or not values:
            return "not installed"
        active = values.get("ActiveState", "unknown")
        sub = values.get("SubState", "")
        restarts = values.get("NRestarts", "0")
        enabled = values.get("UnitFileState", "unknown")
        return f"{active}{('/' + sub) if sub and sub != active else ''}; enabled={enabled}; restarts={restarts}"
    state_match = re.search(r"^\s*state\s*=\s*([^\n]+)", output, re.MULTILINE)
    if not state_match:
        return "loaded/unknown"
    state = state_match.group(1).strip().casefold()
    normalized = "active/running" if state == "running" else f"inactive/{state}"
    enabled_match = re.search(r"^\s*enabled\s*=\s*(true|false|1|0)", output, re.MULTILINE | re.IGNORECASE)
    enabled = (
        "enabled" if enabled_match.group(1).casefold() in {"true", "1"}
        else "disabled" if enabled_match
        else "unknown"
    )
    runs_match = re.search(r"^\s*runs\s*=\s*(\d+)", output, re.MULTILINE)
    restarts = runs_match.group(1) if runs_match else "unknown"
    pid_match = re.search(r"^\s*pid\s*=\s*(\d+)", output, re.MULTILINE)
    pid = pid_match.group(1) if pid_match else "unknown"
    return f"{normalized}; enabled={enabled}; restarts={restarts}; pid={pid}"


def _service_pid(command: list[str]) -> str | None:
    result = _run(command)
    if result is None or result.returncode:
        return None
    if command[0] == "systemctl":
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        pid = values.get("MainPID", "")
    else:
        match = re.search(r"^\s*pid\s*=\s*(\d+)", result.stdout, re.MULTILINE)
        pid = match.group(1) if match else ""
    return pid if pid.isdigit() and pid != "0" else None


def _docker_runtimes() -> list[dict[str, str]]:
    result = _run(
        [
            "docker", "ps", "--all", "--filter", "name=concierge", "--format",
            '{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Label "com.docker.compose.project"}}',
        ],
        timeout=3,
    )
    if result is None or result.returncode:
        return []
    found: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t", 3)
        if len(fields) < 3:
            continue
        name, status, ports = fields
        project = fields[3] if len(fields) == 4 else ""
        found.append({"name": name[:120], "status": status[:80], "ports": ports[:200], "project": project[:120]})
    return found


def _manual_runtimes() -> list[dict[str, str]]:
    result = _run(["ps", "-axo", "pid=,comm=,args="], timeout=2)
    if result is None or result.returncode:
        return []
    found: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if "uvicorn" not in line or "app.main:app" not in line:
            continue
        parts = line.strip().split(None, 2)
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        # Inspect command arguments in memory for port attribution but never print them.
        command = parts[2] if len(parts) > 2 else ""
        port_match = re.search(r"(?:--port(?:=|\s+))(\d{1,5})", command)
        port = port_match.group(1) if port_match else "8080"
        found.append({"pid": parts[0], "process": Path(parts[1]).name[:80], "port": port})
    return found


def _port_owner(port: int) -> list[str]:
    result = _run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"])
    pids = result.stdout.splitlines() if result and not result.returncode else []
    if not pids and sys.platform.startswith("linux"):
        ss_result = _run(["ss", "-ltnp", f"sport = :{port}"])
        if ss_result and not ss_result.returncode:
            pids = re.findall(r"pid=(\d+)", ss_result.stdout)
    owners: list[str] = []
    for pid in pids:
        if not pid.strip().isdigit():
            continue
        process_result = _run(["ps", "-p", pid.strip(), "-o", "comm="])
        process = Path((process_result.stdout if process_result else "unknown").strip()).name or "unknown"
        owners.append(f"{process} (pid {pid.strip()})")
    return owners


def _request(url: str, timeout: float = 3) -> tuple[int | None, object | None, str | None]:
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(32769)
            if len(raw) > 32768:
                return response.status, None, "response exceeded diagnostic limit"
            try:
                return response.status, json.loads(raw.decode("utf-8")), None
            except (UnicodeDecodeError, json.JSONDecodeError):
                return response.status, None, "non-JSON response"
    except urllib.error.HTTPError as exc:
        reason = None
        try:
            detail = json.loads(exc.read(4096).decode("utf-8")).get("detail")
            if detail in SAFE_HEALTH_REASONS:
                reason = detail
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        return exc.code, None, reason or "request failed"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None, "unavailable or timed out"


def _sqlite_revision(path: Path | None) -> str:
    if path is None or not path.is_file():
        return "unknown"
    import sqlite3

    try:
        with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=1) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='concierge_schema_metadata'"
            ).fetchone()
            if not exists:
                return "legacy/unmarked"
            row = db.execute("SELECT revision FROM concierge_schema_metadata WHERE id=1").fetchone()
            return str(row[0]) if row and row[0] else "unknown"
    except (OSError, sqlite3.Error):
        return "unavailable"


def _deployment_manifest(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    patterns = {
        "version": r"(?:[vV]?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*|[A-Fa-f0-9]{7,40}|local|unknown)",
        "commit": r"(?:[A-Fa-f0-9]{7,40}|unknown)",
        "deployment_mode": r"(?:source|docker-dev|appliance|docker-production)",
        "schema_revision": r"(?:\d{8}_\d{4}|unknown)",
        "updated_at": r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+00:00|Z))",
    }
    result: dict[str, str] = {}
    patterns.update({
        "minimum_schema_revision": r"(?:\d{8}_\d{4}|unknown)",
        "maximum_schema_revision": r"(?:\d{8}_\d{4}|unknown)",
        "build_date": r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+00:00|Z)|unknown)",
    })
    for key in (
        "version", "commit", "deployment_mode", "schema_revision", "updated_at",
        "minimum_schema_revision", "maximum_schema_revision", "build_date",
    ):
        item = value.get(key)
        if not isinstance(item, str) or len(item) > 128 or not re.fullmatch(patterns[key], item):
            continue
        result[key] = item
    return result


def _docker_volume_exists(name: str) -> bool:
    result = _run(["docker", "volume", "inspect", name, "--format", "{{.Name}}"], timeout=2)
    return bool(result and result.returncode == 0 and result.stdout.strip() == name)


def _git_identity(root: Path) -> tuple[str, str]:
    try:
        version_result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"], cwd=root, capture_output=True, text=True, timeout=2
        )
        commit_result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=root, capture_output=True, text=True, timeout=2
        )
    except (OSError, subprocess.SubprocessError):
        return "", ""
    version = version_result.stdout.strip() if version_result and version_result.returncode == 0 else ""
    commit = commit_result.stdout.strip() if commit_result and commit_result.returncode == 0 else ""
    if version and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", version):
        version = ""
    if commit and not re.fullmatch(r"[A-Fa-f0-9]{7,40}", commit):
        commit = ""
    return version, commit


def _docker_dev_project(root: Path) -> str:
    suffix = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"concierge-dev-{suffix}"


def _host_ports(runtime: dict[str, str]) -> list[int]:
    return [int(match) for match in re.findall(r":(\d+)->\d+/(?:tcp|udp)", runtime.get("ports", ""))]


def collect(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.resolve() if args.root else Path.cwd().resolve()
    config = read_config(args.config)
    database_url = config.get("DATABASE_URL", "")
    mode = args.mode
    docker = _docker_runtimes()
    service_commands = {
        "concierge.service": ["systemctl", "show", "concierge.service", "--property=LoadState,ActiveState,SubState,NRestarts,UnitFileState,MainPID"],
        "concierge-ai.service": ["systemctl", "show", "concierge-ai.service", "--property=LoadState,ActiveState,SubState,NRestarts,UnitFileState,MainPID"],
    }
    if sys.platform == "darwin":
        service_commands = {
            "com.conciergeai.server": ["launchctl", "print", "system/com.conciergeai.server"],
            "com.conciergeai.proxy": ["launchctl", "print", "system/com.conciergeai.proxy"],
            "com.conciergeai.source": ["launchctl", "print", f"gui/{os.getuid()}/com.conciergeai.source"],
        }
    services = {name: _service_state(command) for name, command in service_commands.items()}
    manual = _manual_runtimes()
    if mode == "auto":
        mode = detect_mode(root=root, docker=docker, services=services, manual=manual)
    configured_dev_port = int(config.get("CONCIERGE_DEV_PORT", "8081") or "8081")
    if args.port is None and mode == "docker-dev":
        project = _docker_dev_project(root)
        running_dev = next((item for item in docker if item.get("project") == project and item["status"].casefold().startswith("up")), None)
        host_port = re.search(r":(\d+)->8080/tcp", running_dev["ports"]) if running_dev else None
        if host_port:
            configured_dev_port = int(host_port.group(1))
    port = args.port or (configured_dev_port if mode == "docker-dev" else int(config.get("CONCIERGE_INTERNAL_PORT", "8080") or "8080"))
    base_url = args.base_url or (f"http://127.0.0.1:{port}")
    db_path = None
    if database_url:
        backend = "PostgreSQL" if database_url.casefold().startswith(("postgresql:", "postgres:")) else "configured external database"
        db_location = "remote/configured; credentials hidden"
    else:
        backend = "SQLite"
        raw_path = config.get("DB_PATH", "state/concierge.db")
        db_path = Path(raw_path).expanduser()
        if not db_path.is_absolute():
            db_path = root / db_path
        db_location = str(db_path)
    state_dir = args.state_directory or (db_path.parent if db_path else root / "state")
    manifest_path = args.manifest or state_dir / "deployment.json"
    manifest = _deployment_manifest(manifest_path)

    live_code, _, _ = _request(base_url.rstrip("/") + "/health/live")
    ready_code, ready_body, ready_reason = _request(base_url.rstrip("/") + "/health/ready")
    version_code, version_body, _ = _request(base_url.rstrip("/") + "/health/version")
    # The public endpoint intentionally carries only status and semantic version.
    # Detailed identity and schema data come from local deployment metadata.
    public_version = version_body.get("version") if version_code == 200 and isinstance(version_body, dict) else None
    if not isinstance(public_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", public_version):
        public_version = "unknown"
    schema = str(getattr(args, "database_schema_revision", "unknown") or "unknown")
    if schema not in {"unknown", "unavailable", "legacy/unmarked"} and not re.fullmatch(r"\d{8}_\d{4}", schema):
        schema = "unknown"
    container_mode = mode in {"appliance", "docker-dev"} and bool(docker)
    project_name = _docker_dev_project(root) if mode == "docker-dev" else "concierge"
    volume_name = f"{project_name}_{'concierge-dev-state' if mode == 'docker-dev' else 'concierge-state'}"
    if container_mode and backend == "SQLite":
        db_path = None
        db_location = f"/state/concierge.db in Docker volume {volume_name}"
    if backend == "SQLite" and schema in {"unknown", "unavailable"}:
        schema = _sqlite_revision(db_path)
    port_owners = _port_owner(port)
    runtimes = []
    if docker:
        docker_groups: dict[str, list[dict[str, str]]] = {}
        for item in docker:
            group = item.get("project") or "unlabeled"
            docker_groups.setdefault(group, []).append(item)
        for project, items in docker_groups.items():
            runtimes.append({
                "kind": "Docker Compose",
                "name": ", ".join(item["name"] for item in items),
                "status": "; ".join(item["status"] for item in items),
                "ports": "; ".join(item["ports"] or "unpublished" for item in items),
                "project": project,
            })
    active_service_names = [name for name, status in services.items() if status.startswith("active")]
    docker_active = any(item["status"].casefold().startswith(("up", "restarting", "paused")) for item in docker)
    runtime_modes: set[str] = set()
    runtime_ports: list[tuple[str, int]] = []
    active_docker = [item for item in docker if item["status"].casefold().startswith(("up", "restarting", "paused"))]
    for item in active_docker:
        project = item.get("project", "")
        if project == "concierge-dev" or re.search(r":8081->8080/tcp", item["ports"]):
            runtime_modes.add("docker-dev")
            runtime_name = item["name"]
        elif project == "concierge" or re.search(r":8080->80/tcp", item["ports"]):
            runtime_modes.add("appliance")
            runtime_name = item["name"]
        else:
            runtime_modes.add("docker")
            runtime_name = item["name"]
        runtime_ports.extend((runtime_name, value) for value in _host_ports(item))
    service_pids = {
        pid for name in active_service_names
        if (pid := _service_pid(service_commands[name])) is not None
    }
    for name in active_service_names:
        if name == "concierge.service" and docker_active:
            # systemd owns the appliance Compose lifecycle; it is not a second API.
            continue
        if name in {"com.conciergeai.proxy"}:
            runtimes.append({"kind": "Service", "name": name, "status": services[name], "ports": "8080"})
            continue
        service_mode = "source" if name in {"concierge-ai.service", "com.conciergeai.source"} else "appliance"
        runtime_modes.add(service_mode)
        service_port = 8080
        runtimes.append({"kind": "Service", "name": name, "status": services[name], "ports": str(service_port)})
        runtime_ports.append((name, service_port))
    unmatched_manual = [item for item in manual if item["pid"] not in service_pids]
    if unmatched_manual:
        runtime_modes.add("manual")
        runtimes.extend({"kind": "uvicorn", **item, "status": "running", "ports": item["port"]} for item in unmatched_manual)
        runtime_ports.extend((f"uvicorn pid {item['pid']}", int(item["port"])) for item in unmatched_manual)
    port_listening = bool(port_owners) or _can_connect(port)
    port_conflict = (
        len([value for _, value in runtime_ports if value == port]) > 1
        or {"appliance", "source"} <= runtime_modes
        or {"appliance", "manual"} <= runtime_modes
    )
    profile = config.get("APP_ENVIRONMENT", "unknown").casefold()
    if profile == "unknown" and mode == "docker-dev":
        profile = "development"
    elif profile == "unknown" and mode == "appliance":
        profile = "production"
    if profile not in SAFE_PROFILE:
        profile = "unknown"
    state_exists = state_dir.exists()
    state_readable = state_exists and os.access(state_dir, os.R_OK)
    state_writable = state_exists and os.access(state_dir, os.W_OK)
    ready_checks = ready_body.get("checks", {}) if isinstance(ready_body, dict) else {}
    if ready_code == 200 and isinstance(ready_body, dict) and ready_body.get("status") == "ok":
        ready = "PASS"
    else:
        ready = "FAIL"
    live = "PASS" if live_code == 200 else "FAIL"
    identity_version = str(manifest.get("version", public_version))
    identity_commit = str(manifest.get("commit", "unknown"))
    identity_drift = bool(
        manifest
        and public_version != "unknown"
        and manifest.get("version")
        and public_version != manifest.get("version")
    )
    if container_mode:
        local_version, local_commit = _git_identity(root)
        if local_commit and identity_commit != "unknown" and identity_commit != local_commit:
            identity_drift = True
        if local_version and public_version != "unknown" and public_version != local_version:
            identity_drift = True
    if container_mode:
        storage_ready = ready == "PASS" and ready_checks.get("storage") == "healthy"
        state_exists = _docker_volume_exists(volume_name) or ready == "PASS"
        state_readable = state_exists and storage_ready
        state_writable = state_exists and storage_ready
    database_accessible = (
        ready == "PASS" and ready_checks.get("database") == "healthy"
        if container_mode
        else bool(db_path and db_path.is_file() and os.access(db_path, os.R_OK))
        if backend == "SQLite"
        else ready == "PASS"
    )
    restart_loop = any(
        "auto-restart" in value.casefold()
        or (value.casefold().startswith("failed") and bool((match := re.search(r"restarts=(\d+)", value)) and int(match.group(1)) > 0))
        for value in services.values()
    ) or any("restarting" in item["status"].casefold() for item in docker)
    container_unhealthy = any("unhealthy" in item["status"].casefold() for item in docker)
    if container_mode:
        state_directory = f"{state_dir} (Docker volume {volume_name} mounted at /state)"
        if args.state_directory is None:
            state_directory = f"Docker volume {volume_name} mounted at /state"
    else:
        state_directory = str(state_dir)
    service_failed = any(value.startswith(("failed", "activating")) for value in services.values())
    redis_check = ready_checks.get("redis") if isinstance(ready_checks, dict) else None
    redis_status = (
        "PASS" if redis_check == "healthy"
        else "NOT CONFIGURED" if redis_check == "not_configured" or (redis_check is None and not config.get("REDIS_URL"))
        else "FAIL/UNKNOWN"
    )
    if mode == "appliance":
        docker_proxy_active = any(
            item["status"].casefold().startswith("up")
            and ("proxy" in item["name"].casefold() or re.search(r":8080->80/tcp", item["ports"]))
            for item in active_docker
        )
        proxy_status = "PASS" if docker_proxy_active or services.get("com.conciergeai.proxy", "").startswith("active") else "FAIL/UNKNOWN"
    else:
        proxy_status = "N/A"
    if backend == "SQLite" and db_path is not None:
        database_has_ai_credentials = _sqlite_ai_credentials(db_path)
    else:
        database_has_ai_credentials = None
    ai_configured = any(
        config.get(key) == "configured"
        for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "COMPATIBLE_API_KEY")
    )
    if ai_configured or database_has_ai_credentials is True:
        ai_provider_status = "CONFIGURED; connection not probed"
    elif database_has_ai_credentials is False:
        ai_provider_status = "NOT CONFIGURED"
    else:
        ai_provider_status = "UNKNOWN; connection not probed"
    backup_directory = Path(config["CONCIERGE_BACKUP_DIR"]).expanduser() if config.get("CONCIERGE_BACKUP_DIR") else None
    if backup_directory is None and mode == "appliance":
        backup_directory = Path("/Library/Application Support/Concierge.AI/Backups") if sys.platform == "darwin" else Path("/var/backups/concierge")
    last_backup = _latest_backup(backup_directory)
    uptime = "unknown"
    uptime_pid = next(iter(service_pids), None)
    if uptime_pid is None and unmatched_manual:
        uptime_pid = unmatched_manual[0]["pid"]
    if uptime_pid is not None:
        uptime_result = _run(["ps", "-p", uptime_pid, "-o", "etime="])
        uptime_value = uptime_result.stdout.strip() if uptime_result and not uptime_result.returncode else ""
        if re.fullmatch(r"(?:\d+-)?\d{1,2}:\d{2}:\d{2}", uptime_value):
            uptime = uptime_value
    if port_conflict or identity_drift or restart_loop or container_unhealthy or service_failed or ready == "FAIL" or live == "FAIL" or not database_accessible or not state_readable or not state_writable or proxy_status == "FAIL/UNKNOWN":
        overall = "DEGRADED" if any((docker, manual, any(v.startswith(("active", "activating")) for v in services.values()), bool(port_owners))) else "FAILED"
    else:
        overall = "HEALTHY"
    bind = args.bind or config.get("CONCIERGE_DEV_BIND_HOST") or "127.0.0.1"
    if args.bind is None and mode == "docker-dev":
        port_binding = next((item["ports"] for item in active_docker if f":{port}->8080/tcp" in item["ports"]), "")
        match = re.search(r"(?:^|,\s*)([^,]+?):" + str(port) + r"->8080/tcp", port_binding)
        if match:
            bind = match.group(1).split(":", 1)[0]
    if container_mode and backend == "SQLite" and schema in {"unknown", "unavailable"}:
        schema = "unavailable in host diagnostics"
    active_containers = [
        item for item in active_docker
        if item.get("project") in {"concierge", _docker_dev_project(root)}
        or (mode == "appliance" and re.search(r":8080->80/tcp", item["ports"]))
        or (mode == "docker-dev" and f":{port}->8080/tcp" in item["ports"])
    ]
    container_name = ", ".join(item["name"] for item in active_containers) or "none detected"
    app_python = sys.version.split()[0]
    service_restart_loop = restart_loop
    return {
        "mode": mode,
        "root": str(root),
        "profile": profile,
        "version": identity_version,
        "commit": identity_commit,
        "build_date": str(manifest.get("build_date", "unknown")),
        "runtime": "Docker Compose" if active_docker else "Python/launchd" if mode == "appliance" and sys.platform == "darwin" else "Python/source" if unmatched_manual or mode == "source" else "unknown",
        "container": container_name,
        "python": app_python,
        "bind": bind if mode in {"source", "docker-dev", "appliance"} else "unknown",
        "port": port,
        "port_listening": port_listening,
        "port_owners": port_owners,
        "runtimes": runtimes,
        "services": services,
        "live": live,
        "ready": ready,
        "ready_reason": ready_reason,
        "ready_checks": ready_checks if isinstance(ready_checks, dict) else {},
        "state_directory": state_directory,
        "state_exists": state_exists,
        "state_readable": state_readable,
        "state_writable": state_writable,
        "database_accessible": database_accessible,
        "database": backend,
        "database_location": db_location,
        "schema_revision": schema,
        "last_deployment": manifest.get("updated_at", "unknown"),
        "last_backup": last_backup,
        "redis": redis_status,
        "proxy": proxy_status,
        "ai_provider": ai_provider_status,
        "uptime": uptime,
        "identity_drift": identity_drift,
        "restart_loop": service_restart_loop,
        "container_unhealthy": container_unhealthy,
        "overall": overall,
        "conflict": port_conflict,
    }


def render_status(data: dict[str, object]) -> str:
    rows = [
        "Concierge.AI",
        "------------------------------",
        f"Version:          {data['version']}",
        f"Commit:           {data['commit']}",
        f"Mode:             {data['mode']}",
        f"Runtime:          {data['runtime']}",
        f"Container:        {data['container']}",
        f"Address:          {data['bind']}",
        f"Port:             {data['port']}",
        f"Service:          {', '.join(name + '=' + str(status) for name, status in data['services'].items())}",
        f"Database:         {data['database']}",
        f"Database access:  {'PASS' if data['database_accessible'] else 'FAIL/UNKNOWN'}",
        f"Schema:           {data['schema_revision']}",
        f"State directory:  {data['state_directory']}",
        f"Last deployment:  {data['last_deployment']}",
        f"Live:             {data['live']}",
        f"Ready:            {data['ready']}",
        f"Overall:          {data['overall']}",
    ]
    return "\n".join(rows)


def _can_connect(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def render_doctor(data: dict[str, object]) -> str:
    rows = [
        "Concierge.AI Doctor",
        "===================",
        f"Application       : {data['version']} ({data['commit']})",
        f"Build date        : {data['build_date']}",
        f"Deployment mode   : {data['mode']}",
        f"Environment       : {data['profile']}",
        f"Runtime           : {data['runtime']} / Python {data['python']}",
        f"Bind              : {data['bind']}:{data['port']}",
        f"Exposure          : {'loopback-only' if data['bind'] in {'127.0.0.1', '::1', 'localhost'} else 'non-loopback bind; Internet reachability unknown'}",
        f"Port listening    : {'yes' if data['port_listening'] else 'no'}",
        f"Port owner        : {', '.join(data['port_owners']) or 'none detected'}",
        f"State directory   : {data['state_directory']}",
        f"State accessible  : {'yes' if data['state_readable'] and data['state_writable'] else 'no'}",
        f"Database          : {data['database']} ({data['database_location']})",
        f"Database access   : {'PASS' if data['database_accessible'] else 'FAIL/UNKNOWN'}",
        f"Redis             : {data['redis']}",
        f"Storage           : {'PASS' if data['state_readable'] and data['state_writable'] else 'FAIL/UNKNOWN'}",
        f"Proxy             : {data['proxy']}",
        f"Port {data['port']}          : {'PASS' if data['port_listening'] and not data['conflict'] else 'FAIL/UNKNOWN'}",
        f"AI provider       : {data['ai_provider']}",
        f"Schema revision   : {data['schema_revision']}",
        f"Uptime            : {data['uptime']}",
        f"Last backup       : {data['last_backup'].get('created_at', 'unknown')} (v{data['last_backup'].get('version', 'unknown')})",
        f"Last deployment   : {data['last_deployment']}",
        f"Live              : {data['live']}",
        f"Readiness         : {data['ready']}{(': ' + str(data['ready_reason'])) if data['ready_reason'] else ''}",
        "Services:",
    ]
    rows.extend(f"  {name}: {status}" for name, status in data["services"].items())
    rows.append("Detected runtimes:")
    runtime_list = data["runtimes"]
    if runtime_list:
        for runtime in runtime_list:
            rows.append(f"  {runtime['kind']}: {runtime.get('name', runtime.get('pid', 'runtime'))} - {runtime.get('status', 'detected')}; port {runtime.get('ports', 'unknown')}")
    else:
        rows.append("  none detected")
    if data["conflict"]:
        rows.append("WARNING: Multiple Concierge.AI runtimes are configured for the same host port.")
    if data["identity_drift"]:
        rows.append("WARNING: Running build identity does not match the installed deployment manifest; check for a stale or mismatched image.")
    if data["restart_loop"]:
        rows.append("WARNING: A service or container is restarting repeatedly; inspect its service logs before retrying.")
    elif data["container_unhealthy"]:
        rows.append("WARNING: Docker reports an unhealthy container; inspect readiness and container logs.")
    if data["proxy"] == "FAIL/UNKNOWN":
        rows.append("WARNING: The expected appliance proxy is not active; verify its service and local listener before routing traffic.")
    if data["ai_provider"].startswith("UNKNOWN"):
        rows.append("AI provider status could not be determined locally; inspect provider status in authenticated Admin diagnostics.")
    if data["ready_checks"]:
        rows.append("Readiness checks: " + ", ".join(f"{key}={value}" for key, value in data["ready_checks"].items()))
    rows.append(f"Overall status: {data['overall']}")
    if data["overall"] != "HEALTHY":
        recommendations: list[str] = []
        if data["conflict"]:
            recommendations.append("Choose one runtime for this port and state directory; stop or reconfigure the other only after confirming the intended owner.")
        if data["identity_drift"]:
            recommendations.append("Compare the running version and commit with the installed release, then rebuild or redeploy the intended artifact.")
        if data["restart_loop"]:
            recommendations.append("Inspect the listed service/container logs before retrying installation or update.")
        if data["ready"] != "PASS":
            reason = data["ready_reason"]
            if reason:
                recommendations.append(f"Resolve the readiness failure ({reason}) before routing traffic.")
            else:
                recommendations.append("Inspect application logs for the readiness failure before routing traffic.")
        if data["proxy"] == "FAIL/UNKNOWN":
            recommendations.append("Check the managed proxy service and its logs; do not start a second proxy on the same listener.")
        if not data["database_accessible"]:
            recommendations.append("Verify database reachability and persisted schema status; do not reset or replace the database.")
        if not data["state_readable"] or not data["state_writable"]:
            recommendations.append("Verify the state directory or Docker volume is present and accessible to the application user.")
        if data["live"] != "PASS":
            recommendations.append("Check whether the expected application process is running and review its sanitized service logs.")
        if not recommendations:
            recommendations.append("Review the service and port details above, then rerun `concierge doctor`.")
        rows.append("Prioritized recommendations:")
        rows.extend(f"  {index}. {recommendation}" for index, recommendation in enumerate(recommendations, start=1))
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "doctor"))
    parser.add_argument("--mode", default="auto")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--state-directory", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--database-schema-revision", default="unknown")
    parser.add_argument("--base-url")
    parser.add_argument("--bind")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    data = collect(args)
    print(render_status(data) if args.command == "status" else render_doctor(data))
    return 0 if data["overall"] == "HEALTHY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
