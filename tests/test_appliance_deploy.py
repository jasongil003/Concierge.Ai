from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.ai as ai_module
from app.config import settings


ROOT = Path(__file__).resolve().parents[1]
OPS_PATH = ROOT / "deploy" / "common" / "ops.py"
BOOT_TEST_PATH = ROOT / "deploy" / "common" / "boot_test.py"


def _load_ops_module():
    spec = importlib.util.spec_from_file_location("concierge_appliance_ops", OPS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("platform", ["linux-systemd", "macos-launchd"])
def test_recovery_ledger_bounds_restarts_and_shares_event_format(tmp_path: Path, monkeypatch, platform: str):
    ops = _load_ops_module()
    restarts: list[list[str]] = []
    monkeypatch.setattr(ops, "_healthy", lambda _url: False)
    monkeypatch.setattr(
        ops.subprocess,
        "run",
        lambda command, **_kwargs: (restarts.append(command) or SimpleNamespace(returncode=0)),
    )
    args = SimpleNamespace(
        state_file=str(tmp_path / "recovery-state.json"),
        event_log=str(tmp_path / "recovery-events.jsonl"),
        platform=platform,
        health_url="http://127.0.0.1:8080/health/ready",
        window_seconds=900,
        max_restarts=3,
        post_restart_wait=0,
        restart_command=["platform-restart"],
    )

    assert [ops.recover(args) for _ in range(6)] == [1, 1, 1, 2, 2, 2]
    assert len(restarts) == 3
    records = [json.loads(line) for line in Path(args.event_log).read_text().splitlines()]
    assert all(record["platform"] == platform for record in records)
    assert all({"timestamp", "platform", "state", "event"} <= record.keys() for record in records)
    assert any(record["state"] == "DEGRADED" for record in records)
    assert any(record["state"] == "RECOVERY" for record in records)
    assert sum(record["event"] == "restart_ceiling_reached" for record in records) == 1
    assert records[-1]["state"] == "CRITICAL"


def _run_boot_test(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BOOT_TEST_PATH), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("platform", ["linux-systemd", "macos-launchd"])
def test_boot_test_requires_new_boot_and_confirms_persistent_property(tmp_path: Path, platform: str):
    state_file = tmp_path / "boot-test.json"
    prepared = _run_boot_test(
        "prepare",
        "--state-file", str(state_file),
        "--platform", platform,
        "--version", "1.2.3",
        "--boot-id", "boot-before",
        "--property-count", "1",
        "--signature", "property-digest",
    )
    assert prepared.returncode == 0, prepared.stderr

    verified = _run_boot_test(
        "verify",
        "--state-file", str(state_file),
        "--boot-id", "boot-after",
        "--property-count", "1",
        "--signature", "property-digest",
    )
    assert verified.returncode == 0, verified.stderr
    record = json.loads(state_file.read_text())
    assert record["status"] == "passed"
    assert record["checks"] == {
        "machine_rebooted": True,
        "property_count_preserved": True,
        "property_configuration_preserved": True,
    }


def test_boot_test_rejects_a_changed_property_configuration(tmp_path: Path):
    state_file = tmp_path / "boot-test.json"
    prepared = _run_boot_test(
        "prepare", "--state-file", str(state_file), "--platform", "linux-systemd",
        "--version", "1.2.3", "--boot-id", "boot-before", "--property-count", "1",
        "--signature", "before",
    )
    assert prepared.returncode == 0, prepared.stderr

    verified = _run_boot_test(
        "verify", "--state-file", str(state_file), "--boot-id", "boot-after",
        "--property-count", "1", "--signature", "after",
    )
    assert verified.returncode == 1
    assert json.loads(state_file.read_text())["checks"]["property_configuration_preserved"] is False


def test_auto_routing_does_not_call_local_ai_when_appliance_disables_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ai_module,
        "settings",
        replace(settings, ai_provider_mode="auto", local_ai_enabled=False),
    )
    orchestrator = ai_module.AIOrchestrator()
    calls: list[str] = []

    async def forbidden_local_call(**_kwargs):
        calls.append("local")
        raise AssertionError("Disabled local AI must never be contacted.")

    monkeypatch.setattr(orchestrator.local, "chat", forbidden_local_call)
    with pytest.raises(RuntimeError, match="No configured AI provider"):
        asyncio.run(orchestrator.chat("How do I connect to Wi-Fi?", "Hotel", []))
    assert calls == []
