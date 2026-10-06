#!/usr/bin/env python3
"""Fail-closed appliance port/runtime preflight; this command is read-only."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time


def _run(command: list[str], timeout: float = 2) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _service_active(unit: str) -> bool:
    result = _run(["systemctl", "show", "--value", "--property=ActiveState", unit])
    return bool(result and result.returncode == 0 and result.stdout.strip() in {"active", "activating", "reloading"})


def _launchd_active(label: str) -> bool:
    result = _run(["launchctl", "print", f"system/{label}"])
    return bool(result and result.returncode == 0)


def _docker_on_port(port: int, expected_project: str) -> tuple[bool, bool]:
    result = _run([
        "docker", "ps", "--format",
        "{{.Label \"com.docker.compose.project\"}}\t{{.Names}}\t{{.Ports}}",
    ], timeout=3)
    if result is None or result.returncode:
        return False, False
    matched = []
    for line in result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        project, _name, ports = fields
        if any(f":{port}->" in entry for entry in ports.split(",")):
            matched.append(project)
    return bool(matched), bool(matched) and all(project == expected_project for project in matched)


def _listener(port: int) -> bool:
    for host in ("127.0.0.1", "::1"):
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                if probe.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def wait_for_port_free(port: int, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while _listener(port):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.25)
    return True


def _foreign_uvicorn_active() -> bool:
    result = _run(["ps", "-axo", "args="], timeout=2)
    if result is None or result.returncode:
        return False
    for command in result.stdout.splitlines():
        if "uvicorn" not in command or "app.main:app" not in command:
            continue
        if "/opt/concierge/current/" not in command:
            return True
    return False


def _macos_listener_is_appliance(port: int) -> bool:
    result = _run(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"])
    if result is None or result.returncode:
        return False
    pids = [pid.strip() for pid in result.stdout.splitlines() if pid.strip().isdigit()]
    if not pids:
        return False
    for pid in pids:
        process = _run(["ps", "-p", pid, "-o", "args="])
        command = process.stdout if process and process.returncode == 0 else ""
        proxy = port == 8080 and "/opt/concierge/current/deploy/common/loopback_proxy.py" in command
        app = port == 8081 and "/opt/concierge/current/" in command and "app.main:app" in command
        if not (proxy or app):
            return False
    return True


def preflight(port: int, *, mode: str = "appliance", project_name: str | None = None) -> tuple[bool, str]:
    if mode not in {"appliance", "docker-dev"}:
        return False, "unsupported deployment mode for port preflight"
    source_active = _service_active("concierge-ai.service")
    if mode == "appliance" and sys.platform == "darwin":
        source_active = source_active or _launchd_active("com.conciergeai.source")
    native_appliance_active = mode == "appliance" and sys.platform == "darwin" and _launchd_active("com.conciergeai.server")
    expected_project_name = "concierge" if mode == "appliance" else project_name or "concierge-dev"
    mapped, expected_project = _docker_on_port(port, expected_project_name)
    port_busy = _listener(port)
    if mode == "appliance" and (source_active or _foreign_uvicorn_active()):
        return False, "a source-mode service or manually launched source runtime is active; appliance install would create competing runtimes."
    if mapped and not expected_project:
        return False, "port is published by a different Docker Compose project."
    own_runtime = mapped and expected_project
    if mode == "appliance" and sys.platform == "darwin":
        own_runtime = own_runtime or native_appliance_active and _macos_listener_is_appliance(port)
    if port_busy and not own_runtime:
        return False, f"port {port} is occupied by an unidentified or different runtime."
    return True, "port and runtime preflight passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("appliance", "docker-dev", "port-free"))
    parser.add_argument("--port", type=int)
    parser.add_argument("--project-name")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()
    port = args.port or (8081 if args.command == "docker-dev" else 8080)
    if args.command == "port-free":
        if wait_for_port_free(port, args.timeout):
            print(f"Port {port} is free.")
            return 0
        print(
            f"Port {port} remained occupied after the stop request. No process was terminated by this check.",
            file=sys.stderr,
        )
        return 1
    ok, reason = preflight(port, mode=args.command, project_name=args.project_name)
    if ok:
        print(f"Preflight passed: {reason}.")
        return 0
    print(
        f"Preflight failed: {reason} No service, database, or configuration was changed. "
        "Run `concierge doctor`, identify the owner, and resolve the conflict intentionally.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
