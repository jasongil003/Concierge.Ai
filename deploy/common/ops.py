#!/usr/bin/env python3
"""Shared on-host recovery ledger and bounded restart policy."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _event(log_path: Path, platform: str, state: str, event: str, **details: Any) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": platform,
        "state": state,
        "event": event,
        **details,
    }
    with log_path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {"attempts": [], "state": "NORMAL"}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(path)


def _healthy(url: str, timeout: float = 4) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def recover(args: argparse.Namespace) -> int:
    state_path = Path(args.state_file)
    log_path = Path(args.event_log)
    lock_path = state_path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = _read_state(state_path)
        now = int(time.time())
        attempts: list[int] = []
        recorded_attempts = state.get("attempts", [])
        if isinstance(recorded_attempts, list):
            for item in recorded_attempts:
                try:
                    timestamp = int(item)
                except (TypeError, ValueError):
                    continue
                if 0 <= now - timestamp < args.window_seconds:
                    attempts.append(timestamp)
        if _healthy(args.health_url):
            if state.get("state") != "NORMAL" or state.get("last_result") != "healthy":
                _event(log_path, args.platform, "NORMAL", "health_restored", prior_state=state.get("state", "NORMAL"))
            _write_state(state_path, {"attempts": attempts, "state": "NORMAL", "last_result": "healthy"})
            return 0

        if len(attempts) >= args.max_restarts:
            if state.get("state") != "CRITICAL" or state.get("last_result") != "restart_ceiling_reached":
                _event(
                    log_path,
                    args.platform,
                    "CRITICAL",
                    "restart_ceiling_reached",
                    attempts=len(attempts),
                    window_seconds=args.window_seconds,
                )
            _write_state(state_path, {"attempts": attempts, "state": "CRITICAL", "last_result": "restart_ceiling_reached"})
            return 2

        _event(log_path, args.platform, "DEGRADED", "readiness_failed", attempts=len(attempts))
        _event(log_path, args.platform, "RECOVERY", "restart_attempt", attempt=len(attempts) + 1, maximum=args.max_restarts)
        result = subprocess.run(args.restart_command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        attempts.append(now)
        deadline = time.monotonic() + args.post_restart_wait
        while time.monotonic() < deadline:
            if _healthy(args.health_url):
                _event(log_path, args.platform, "NORMAL", "restart_recovered", attempt=len(attempts))
                _write_state(state_path, {"attempts": attempts, "state": "NORMAL", "last_result": "healthy"})
                return 0
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        state_name = "CRITICAL" if len(attempts) >= args.max_restarts else "DEGRADED"
        _event(log_path, args.platform, state_name, "restart_failed", attempt=len(attempts), command_exit=result.returncode)
        _write_state(state_path, {"attempts": attempts, "state": state_name, "last_result": "unhealthy"})
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    recovery = subparsers.add_parser("recover")
    recovery.add_argument("--platform", required=True)
    recovery.add_argument("--health-url", default="http://127.0.0.1:8080/health/ready")
    recovery.add_argument("--event-log", required=True)
    recovery.add_argument("--state-file", required=True)
    recovery.add_argument("--max-restarts", type=int, default=3)
    recovery.add_argument("--window-seconds", type=int, default=900)
    recovery.add_argument("--post-restart-wait", type=int, default=45)
    recovery.add_argument("restart_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "recover":
        if args.restart_command and args.restart_command[0] == "--":
            args.restart_command = args.restart_command[1:]
        if not args.restart_command:
            parser.error("recover requires a platform restart command after --")
        return recover(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
