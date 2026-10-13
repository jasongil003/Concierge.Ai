"""Recovery fixtures must not seed the application's database credentials."""

import subprocess

import pytest

from scripts import failure_recovery_smoke as recovery


@pytest.fixture
def captured_recovery_environments(monkeypatch):
    launches = []
    integrations = []
    migrations = []
    ports = iter((55001, 55002, 55003))
    monkeypatch.setattr(recovery, "_unused_port", lambda: next(ports))
    monkeypatch.setattr(recovery, "_docker", lambda *args: "")
    monkeypatch.setattr(recovery, "_published_port", lambda container, internal: "55001" if internal == "5432/tcp" else "55002")
    monkeypatch.setattr(recovery, "_wait_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(recovery, "_wait_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(recovery, "_launch_api", lambda env, *args: launches.append(dict(env)) or object())
    monkeypatch.setattr(recovery, "_stop_api", lambda *args: None)
    monkeypatch.setattr(recovery, "_login", lambda *args: (object(), {}))
    monkeypatch.setattr(recovery, "_json_request", lambda *args, **kwargs: (200, {"status": "ok"}))
    monkeypatch.setattr(recovery, "_verify_config", lambda *args: None)

    def fake_run(command, **kwargs):
        if "pytest" in command:
            integrations.append(dict(kwargs["env"]))
        if "upgrade" in command:
            migrations.append(dict(kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, stdout="8 passed\n", stderr="")

    monkeypatch.setattr(recovery.subprocess, "run", fake_run)
    monkeypatch.delenv("ADMIN_BOOTSTRAP_USERNAME", raising=False)
    recovery.main()
    assert launches and len(integrations) == 1
    return launches[0], integrations[0], migrations


def test_recovery_bootstrap_identity_matches_its_admin_login(captured_recovery_environments):
    runtime, integration, _ = captured_recovery_environments
    assert runtime.get("ADMIN_BOOTSTRAP_USERNAME") == "admin"
    assert integration.get("ADMIN_BOOTSTRAP_USERNAME") == "admin"


def test_pytest_bootstrap_and_rate_limits_are_isolated_from_recovery_runtime(captured_recovery_environments):
    runtime, integration, migrations = captured_recovery_environments
    assert integration["DATABASE_URL"] != runtime["DATABASE_URL"], "Pytest changes its bootstrap password and must never seed the live recovery database"
    assert integration["REDIS_URL"] != runtime["REDIS_URL"]
    assert integration["REDIS_TEST_URL"] != runtime["REDIS_URL"]
    assert {entry["DATABASE_URL"] for entry in migrations} == {runtime["DATABASE_URL"], integration["DATABASE_URL"]}
