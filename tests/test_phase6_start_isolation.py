"""Idempotent Phase6 start must free static endpoints before one-off jobs."""

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_phase6_start_stops_only_app_and_proxy_before_running_maintenance(tmp_path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "docker-calls.jsonl"
    fake_docker = binaries / "docker"
    fake_docker.write_text("#!/usr/bin/env python3\n" + r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ["PHASE6_COMMAND_LOG"], "a") as output:
    output.write(json.dumps(args) + "\n")
if args[:2] == ["context", "show"]:
    print("test-local")
elif args[:2] == ["context", "inspect"]:
    print("unix:///test/docker.sock")
elif args[:2] == ["volume", "inspect"]:
    sys.exit(1)
elif "ps" in args and "--quiet" in args:
    print("existing-synthetic-app")
elif "redis-cli" in args and "ping" in args:
    print("PONG")
''')
    fake_docker.chmod(0o755)
    temporary_root = tmp_path / "runtime"
    temporary_root.mkdir()
    env = {**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}", "TMPDIR": str(temporary_root), "PHASE6_COMMAND_LOG": str(log)}
    env.pop("DOCKER_HOST", None)
    result = subprocess.run(["bash", str(ROOT / "scripts/phase6/acceptance.sh"), "start"], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    compose_calls = [args for args in calls if args[0] == "compose"]
    first_job = next(index for index, args in enumerate(compose_calls) if "run" in args)
    stops = [(index, args[args.index("stop") + 1:]) for index, args in enumerate(compose_calls) if "stop" in args]
    assert stops and stops[0][0] < first_job, "Live static application endpoint must be released before a migration/seed job starts"
    assert set(stops[0][1]) == {"concierge", "proxy"}
    assert all("--project-name" in args and args[args.index("--project-name") + 1].startswith("concierge-phase6-") for args in compose_calls)
