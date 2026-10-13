"""Recovery fixtures must not seed the application's database credentials."""

import os
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
    monkeypatch.setenv("CONCIERGE_SYNTHETIC_HOST_SECRET_SENTINEL", "synthetic-host-secret-for-isolation-test")
    host_sensitive_names = {
        name for name in os.environ
        if any(marker in name.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))
    } - {"ADMIN_BOOTSTRAP_PASSWORD", "CREDENTIAL_ENCRYPTION_SECRET", "METRICS_TOKEN"}
    recovery.main()
    assert launches and len(integrations) == 1
    runtime, integration = launches[0], integrations[0]
    return {
        "runtime_bootstrap_identity_matches": runtime.get("ADMIN_BOOTSTRAP_USERNAME") == "admin",
        "integration_bootstrap_identity_matches": integration.get("ADMIN_BOOTSTRAP_USERNAME") == "admin",
        "integration_database_isolated": integration.get("DATABASE_URL") != runtime.get("DATABASE_URL"),
        "integration_redis_isolated": integration.get("REDIS_URL") != runtime.get("REDIS_URL"),
        "integration_rate_limiter_isolated": integration.get("REDIS_TEST_URL") != runtime.get("REDIS_URL"),
        "migrations_cover_both_isolated_databases": {entry.get("DATABASE_URL") for entry in migrations}
        == {runtime.get("DATABASE_URL"), integration.get("DATABASE_URL")},
        "host_sensitive_environment_excluded": all(
            host_sensitive_names.isdisjoint(environment)
            for environment in (*launches, *integrations, *migrations)
        ),
    }


def test_recovery_bootstrap_identity_matches_its_admin_login(captured_recovery_environments):
    assert captured_recovery_environments["runtime_bootstrap_identity_matches"]
    assert captured_recovery_environments["integration_bootstrap_identity_matches"]


def test_pytest_bootstrap_and_rate_limits_are_isolated_from_recovery_runtime(captured_recovery_environments):
    assert captured_recovery_environments["integration_database_isolated"]
    assert captured_recovery_environments["integration_redis_isolated"]
    assert captured_recovery_environments["integration_rate_limiter_isolated"]
    assert captured_recovery_environments["migrations_cover_both_isolated_databases"]


def test_recovery_children_do_not_receive_host_credentials(captured_recovery_environments):
    assert captured_recovery_environments["host_sensitive_environment_excluded"]
