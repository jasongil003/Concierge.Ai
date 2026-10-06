#!/usr/bin/env python3
"""Cross-platform process lock for install and update operations."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


def run_locked(lock_path: Path, command: list[str]) -> int:
    if not command:
        raise ValueError("A command is required after --.")
    lock_path = lock_path.expanduser().resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            try:
                metadata = json.loads(lock.read())
            except (json.JSONDecodeError, OSError):
                metadata = {}
            pid = metadata.get("pid", "unknown")
            started = metadata.get("started_at", "unknown")
            print(
                f"Another Concierge.AI deployment operation is running. PID: {pid}. Started: {started}.",
                file=sys.stderr,
            )
            return 2
        metadata = {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps(metadata, sort_keys=True) + "\n")
        lock.flush()
        os.fsync(lock.fileno())
        environment = {**os.environ, "CONCIERGE_OPERATION_LOCK_HELD": "1"}
        try:
            return subprocess.run(
                command,
                check=False,
                env=environment,
                pass_fds=(lock.fileno(),),
            ).returncode
        finally:
            lock.seek(0)
            lock.truncate()
            lock.flush()
            os.fsync(lock.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--lock", type=Path, required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    return run_locked(args.lock, command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Deployment lock error: {exc}", file=sys.stderr)
        raise SystemExit(1)
