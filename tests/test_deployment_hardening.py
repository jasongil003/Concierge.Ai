from __future__ import annotations

import asyncio
import json
import io
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.error
import zipfile

import pytest

from app import build_info, database
from app.backup import create_backup, verify_backup
from app.properties import PropertyRecord, PropertyStore
from deploy.common import deployment_manifest, diagnostics, operation_lock, preflight, update_decision
from deploy import source_service


ROOT = Path(__file__).resolve().parents[1]


def test_version_endpoint_reports_only_safe_build_identity(monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.main as main_module

    monkeypatch.setenv("CONCIERGE_VERSION", "0.9.2")
    monkeypatch.setenv("CONCIERGE_COMMIT", "a1b2c3d4")
    monkeypatch.setenv("CONCIERGE_BUILD_DATE", "2026-10-06T01:02:03Z")
    monkeypatch.setenv("CONCIERGE_DEPLOYMENT_MODE", "docker-dev")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_SECRET", "private-build-secret")
    monkeypatch.setenv("METRICS_TOKEN", "private-metrics-token")
    monkeypatch.setattr(main_module, "BUILD_IDENTITY", {
        "version": "0.9.2", "commit": "a1b2c3d4", "build_date": "2026-10-06T01:02:03Z",
        "deployment_mode": "docker-dev", "profile": "development", "runtime": "python",
        "python_version": sys.version.split()[0],
    })

    with TestClient(app) as client:
        response = client.get("/health/version")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.9.2"}
    assert set(response.json()) == {"status", "version"}
    assert "private-build-secret" not in response.text
    assert "private-metrics-token" not in response.text


def test_build_identity_rejects_untrusted_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_VERSION", "version\nCREDENTIAL=leak")
    monkeypatch.setenv("CONCIERGE_COMMIT", "postgresql://user:password@host")
    monkeypatch.setenv("CONCIERGE_BUILD_DATE", "password=do-not-print")
    monkeypatch.setattr(build_info, "_git_value", lambda *_args: None)
    monkeypatch.setattr(build_info, "_git_timestamp", lambda: None)

    identity = build_info.build_identity()

    assert identity["version"] == "0.0.0+source"
    assert identity["commit"] == "unknown"
    assert identity["build_date"] == "unknown"
    assert "password" not in json.dumps(identity)


@pytest.mark.parametrize(
    ("filename", "value", "expected"),
    [
        ("RELEASE_BUILD_DATE", "2026-10-06T03:15:32Z", "2026-10-06T03:15:32Z"),
        ("RELEASE_BUILD_DATE", "2026-02-30T03:15:32Z", None),
        ("RELEASE_BUILD_DATE", "a1b2c3d4", None),
        ("RELEASE_COMMIT", "2026-10-06T03:15:32Z", None),
        ("RELEASE_VERSION", "2026-10-06T03:15:32Z", None),
    ],
)
def test_release_file_uses_field_specific_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename, value, expected):
    app_dir = tmp_path / "release" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / filename).write_text(value, encoding="utf-8")
    monkeypatch.setattr(build_info, "__file__", str(app_dir / "build_info.py"))

    assert build_info._release_file(filename) == expected

    if filename == "RELEASE_BUILD_DATE":
        monkeypatch.setattr(build_info, "_git_timestamp", lambda: None)
        monkeypatch.delenv("CONCIERGE_BUILD_DATE", raising=False)
        identity = build_info.build_identity()
        assert identity["build_date"] == (expected or "unknown")


def test_release_file_uses_commit_validator_for_commit_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app_dir = tmp_path / "release" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "RELEASE_COMMIT").write_text("a1b2c3d4", encoding="utf-8")
    monkeypatch.setattr(build_info, "__file__", str(app_dir / "build_info.py"))
    assert build_info._release_file("RELEASE_COMMIT") == "a1b2c3d4"


def test_guest_chat_rate_limit_cannot_be_multiplied_by_new_sessions(monkeypatch: pytest.MonkeyPatch):
    network_counts: dict[str, int] = {}
    seen_keys: list[str] = []

    async def allow(key: str, limit: int, seconds: int) -> bool:
        seen_keys.append(key)
        if key.startswith("guest-chat:"):
            return True
        network_counts[key] = network_counts.get(key, 0) + 1
        return network_counts[key] <= limit

    import app.main as main_module

    monkeypatch.setattr(main_module, "_rate_limit_allowed", allow)
    results = [
        asyncio.run(main_module._guest_chat_rate_limited(f"session-{index}", "property-a", "192.0.2.15"))
        for index in range(121)
    ]

    assert results[:120] == [False] * 120
    assert results[120] is True
    assert all("192.0.2.15" not in key for key in seen_keys)


def test_unresolved_guest_chat_rate_limit_is_property_scoped(monkeypatch: pytest.MonkeyPatch):
    bucket_counts: dict[str, int] = {}
    seen_client_keys: set[str] = set()

    async def allow(key: str, limit: int, _seconds: int) -> bool:
        if key.startswith("guest-chat:"):
            return True
        seen_client_keys.add(key)
        bucket_counts[key] = bucket_counts.get(key, 0) + 1
        return bucket_counts[key] <= limit

    import app.main as main_module

    monkeypatch.setattr(main_module, "_rate_limit_allowed", allow)
    unresolved = [
        asyncio.run(main_module._guest_chat_rate_limited(f"unresolved-{index}", "property-a", ""))
        for index in range(121)
    ]
    other_property = asyncio.run(main_module._guest_chat_rate_limited("other-property", "property-b", ""))

    assert unresolved[:120] == [False] * 120
    assert unresolved[120] is True
    assert other_property is False
    assert len(seen_client_keys) == 2
    assert all("unresolved-client" not in key for key in seen_client_keys)


def test_guest_client_ip_resolution_trusts_only_valid_forwarded_chains():
    from app.guardrails import NetworkGuard

    guard = NetworkGuard()
    config = {"trusted_proxy_ranges": ["192.0.2.0/24"]}

    trusted_ip, trusted = guard.client_ip(
        "192.0.2.10", {"x-forwarded-for": "198.51.100.8, 192.0.2.20"}, config
    )
    malformed_ip, malformed_trusted = guard.client_ip(
        "192.0.2.10", {"x-forwarded-for": "198.51.100.8, not-an-ip"}, config
    )
    untrusted_ip, untrusted = guard.client_ip(
        "203.0.113.10", {"x-forwarded-for": "198.51.100.8"}, config
    )

    assert (trusted_ip, trusted) == ("198.51.100.8", True)
    assert (malformed_ip, malformed_trusted) == ("", True)
    assert (untrusted_ip, untrusted) == ("203.0.113.10", False)


def test_sqlite_legacy_schema_upgrade_preserves_rows_and_records_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "_configured_url", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "legacy.db"
    store = PropertyStore(path)
    store.upsert(PropertyRecord(property_id="legacy-property", hotel_name="Legacy Hotel"))
    with sqlite3.connect(path) as connection:
        connection.execute(f"DROP TABLE IF EXISTS {database.SQLITE_SCHEMA_METADATA_TABLE}")
        connection.execute("ALTER TABLE properties DROP COLUMN brand_assets")

    database.verify_schema_current(path)
    assert database.sqlite_schema_revision(path) is None
    upgraded = PropertyStore(path)
    assert upgraded.get("legacy-property").hotel_name == "Legacy Hotel"
    with sqlite3.connect(path) as connection:
        assert "brand_assets" in {row[1] for row in connection.execute("PRAGMA table_info(properties)")}
    database.stamp_sqlite_schema_current(path)
    assert database.sqlite_schema_revision(path) == database.CURRENT_SCHEMA_REVISION
    database.database_ready(path)


def test_sqlite_newer_schema_is_rejected_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "_configured_url", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "newer.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"CREATE TABLE {database.SQLITE_SCHEMA_METADATA_TABLE} (id INTEGER PRIMARY KEY, revision TEXT NOT NULL)"
        )
        connection.execute(
            f"INSERT INTO {database.SQLITE_SCHEMA_METADATA_TABLE} VALUES (1, '20990101_0001')"
        )
    with pytest.raises(RuntimeError, match="newer than this application build"):
        database.verify_schema_current(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            f"SELECT revision FROM {database.SQLITE_SCHEMA_METADATA_TABLE} WHERE id=1"
        ).fetchone()[0] == "20990101_0001"


def test_sqlite_older_marked_schema_is_not_silently_stamped_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "_configured_url", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "older.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"CREATE TABLE {database.SQLITE_SCHEMA_METADATA_TABLE} (id INTEGER PRIMARY KEY, revision TEXT NOT NULL)"
        )
        connection.execute(
            f"INSERT INTO {database.SQLITE_SCHEMA_METADATA_TABLE} VALUES (1, '20250901_0001')"
        )

    with pytest.raises(RuntimeError, match="older than this application build"):
        database.verify_schema_current(path)

    assert database.sqlite_schema_revision(path) == "20250901_0001"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='properties'").fetchone() is None


def test_readiness_requires_schema_marker_after_legacy_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "_configured_url", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "unmarked.db"
    PropertyStore(path)
    with pytest.raises(RuntimeError, match="Database migration required"):
        database.database_ready(path)
    database.stamp_sqlite_schema_current(path)
    database.database_ready(path)


def test_readonly_schema_checks_support_database_paths_with_spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "_configured_url", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = tmp_path / "folder with spaces" / "concierge database.sqlite"
    PropertyStore(path)
    database.stamp_sqlite_schema_current(path)

    assert database.sqlite_schema_revision(path) == database.CURRENT_SCHEMA_REVISION
    database.database_ready(path)


def test_doctor_redacts_config_secrets_and_groups_expected_appliance_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "concierge.env"
    state = tmp_path / "state"
    state.mkdir()
    config.write_text(
        "APP_ENVIRONMENT=production\n"
        "DATABASE_URL=postgresql://private-user:private-password@db.example.test/concierge\n"
        "CREDENTIAL_ENCRYPTION_SECRET=private-encryption-secret\n"
        "METRICS_TOKEN=private-metrics-token\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        mode="appliance", root=tmp_path, config=config, state_directory=state, manifest=None,
        base_url="http://127.0.0.1:8080", bind="127.0.0.1", port=8080,
    )
    monkeypatch.setattr(diagnostics, "_docker_runtimes", lambda: [
        {"name": "concierge-concierge-1", "status": "Up (healthy)", "ports": "8080/tcp"},
        {"name": "concierge-proxy-1", "status": "Up", "ports": "127.0.0.1:8080->80/tcp"},
    ])
    monkeypatch.setattr(diagnostics, "_service_state", lambda command: (
        "active/running; restarts=0" if command[2] == "concierge.service" else "not installed"
    ))
    monkeypatch.setattr(diagnostics, "_manual_runtimes", lambda: [])
    monkeypatch.setattr(diagnostics, "_request", lambda url, timeout=3: (
        (200, {"status": "ok", "checks": {"database": "healthy", "storage": "healthy"}}, None)
        if url.endswith("/health/ready") else
        (200, {"status": "ok"}, None)
        if url.endswith("/health/live") else
        (200, {"version": "0.9.2", "commit": "a1b2c3d4", "build_date": "unknown", "schema_revision": "20261005_0001"}, None)
    ))
    monkeypatch.setattr(diagnostics, "_port_owner", lambda _port: ["docker-proxy (pid 123)"])
    monkeypatch.setattr(diagnostics, "_can_connect", lambda _port: True)

    data = diagnostics.collect(args)
    rendered = diagnostics.render_doctor(data)

    assert data["overall"] == "HEALTHY"
    assert data["conflict"] is False
    assert data["database"] == "PostgreSQL"
    assert data["database_location"] == "remote/configured; credentials hidden"
    assert data["schema_revision"] == "unknown"
    assert len(data["runtimes"]) == 1
    assert "private-password" not in rendered
    assert "private-encryption-secret" not in rendered
    assert "private-metrics-token" not in rendered
    assert "postgresql://" not in rendered
    assert "Internet reachability unknown" not in rendered


def test_docker_dev_doctor_reports_its_volume_and_host_diagnostics_python_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = diagnostics._docker_dev_project(tmp_path)
    args = SimpleNamespace(
        mode="docker-dev", root=tmp_path, config=None, state_directory=None, manifest=None,
        base_url="http://127.0.0.1:8081", bind=None, port=None,
    )
    monkeypatch.setattr(diagnostics, "_docker_runtimes", lambda: [
        {"name": "concierge-dev-web-1", "status": "Up (healthy)", "ports": "127.0.0.1:8081->8080/tcp", "project": project},
    ])
    monkeypatch.setattr(diagnostics, "_service_state", lambda _command: "not installed")
    monkeypatch.setattr(diagnostics, "_manual_runtimes", lambda: [])
    monkeypatch.setattr(diagnostics, "_docker_volume_exists", lambda _name: True)
    monkeypatch.setattr(diagnostics, "_request", lambda url, timeout=3: (
        (200, {"status": "ok", "checks": {"database": "healthy", "storage": "healthy"}}, None)
        if url.endswith("/health/ready") else
        (200, {"status": "ok"}, None) if url.endswith("/health/live") else
        (200, {"status": "ok", "version": "0.9.2"}, None)
    ))
    monkeypatch.setattr(diagnostics, "_port_owner", lambda _port: ["docker-proxy (pid 123)"])
    monkeypatch.setattr(diagnostics, "_can_connect", lambda _port: True)

    data = diagnostics.collect(args)
    rendered = diagnostics.render_doctor(data)

    assert data["overall"] == "HEALTHY"
    assert data["container"] == "concierge-dev-web-1"
    assert data["python"] == sys.version.split()[0]
    assert data["database_location"].startswith("/state/concierge.db in Docker volume")
    assert "127.0.0.1:8081" in rendered


def test_diagnostics_sanitize_untrusted_health_error_details(monkeypatch: pytest.MonkeyPatch):
    error = urllib.error.HTTPError(
        "http://127.0.0.1/health/ready", 503, "Unavailable", {}, io.BytesIO(b'{"detail":"private-password=do-not-display"}')
    )
    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))

    status, body, reason = diagnostics._request("http://127.0.0.1:8080/health/ready")

    assert status == 503
    assert body is None
    assert reason == "request failed"
    assert "private-password" not in str(reason)


def test_deployment_manifest_is_atomic_sanitized_and_preserves_install_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "release"
    (root / "app").mkdir(parents=True)
    (root / "app" / "database.py").write_text('CURRENT_SCHEMA_REVISION = "20261005_0001"\n', encoding="utf-8")
    (root / "RELEASE_VERSION").write_text("1.2.3\n", encoding="utf-8")
    (root / "RELEASE_COMMIT").write_text("a1b2c3d4\n", encoding="utf-8")
    (root / "RELEASE_BUILD_DATE").write_text("2026-10-06T03:15:32Z\n", encoding="utf-8")
    (root / "RELEASE_MINIMUM_SCHEMA_REVISION").write_text("20260926_0001\n", encoding="utf-8")
    (root / "RELEASE_MAXIMUM_SCHEMA_REVISION").write_text("20261005_0001\n", encoding="utf-8")
    monkeypatch.delenv("CONCIERGE_BUILD_DATE", raising=False)
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_SECRET", "manifest-must-not-have-this")
    manifest_path = tmp_path / "state" / "deployment.json"

    first = deployment_manifest.write_manifest(manifest_path, root, "appliance")
    second = deployment_manifest.write_manifest(manifest_path, root, "appliance")

    assert first["installed_at"] == second["installed_at"]
    assert second["version"] == "1.2.3"
    assert second["commit"] == "a1b2c3d4"
    assert second["schema_revision"] == "20261005_0001"
    assert second["minimum_schema_revision"] == "20260926_0001"
    assert second["maximum_schema_revision"] == "20261005_0001"
    assert second["build_date"] == "2026-10-06T03:15:32Z"
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert "manifest-must-not-have-this" not in manifest_path.read_text(encoding="utf-8")
    assert list(manifest_path.parent.glob("*.tmp")) == []


def test_local_schema_revision_command_sanitizes_database_failures(monkeypatch, capsys):
    from deploy.common import schema_revision

    def fail(_path):
        raise RuntimeError("postgresql://user:private-test-value@database/concierge")

    monkeypatch.setattr(database, "persisted_schema_revision", fail)
    assert schema_revision.main() == 1
    captured = capsys.readouterr()
    assert captured.out == "unavailable\n"
    assert "private-test-value" not in captured.out + captured.err


def test_update_lock_refuses_parallel_operation_and_recovers_stale_metadata(tmp_path: Path):
    lock_path = tmp_path / "deployment.lock"
    lock_script = ROOT / "deploy" / "common" / "operation_lock.py"
    first = subprocess.Popen(
        [sys.executable, str(lock_script), "run", "--lock", str(lock_path), "--", sys.executable, "-c", "import time; time.sleep(1.2)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            if json.loads(lock_path.read_text(encoding="utf-8")).get("pid"):
                break
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(0.02)
    result = subprocess.run(
        [sys.executable, str(lock_script), "run", "--lock", str(lock_path), "--", sys.executable, "-c", "raise SystemExit(77)"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "Another Concierge.AI deployment operation is running" in result.stderr
    assert "PID:" in result.stderr and "Started:" in result.stderr
    assert first.wait(timeout=5) == 0
    first.communicate(timeout=1)

    lock_path.write_text('{"pid":99999999,"started_at":"stale"}\n', encoding="utf-8")
    assert operation_lock.run_locked(lock_path, [sys.executable, "-c", "pass"]) == 0
    assert lock_path.read_text(encoding="utf-8") == ""


def test_appliance_preflight_blocks_source_and_unidentified_port_owner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(preflight, "_service_active", lambda unit: unit == "concierge-ai.service")
    monkeypatch.setattr(preflight, "_docker_on_port", lambda _port, _project: (False, False))
    monkeypatch.setattr(preflight, "_listener", lambda _port: False)
    monkeypatch.setattr(preflight, "_foreign_uvicorn_active", lambda: False)
    ok, reason = preflight.preflight(8080)
    assert ok is False
    assert "source-mode service" in reason or "source-mode" in reason

    monkeypatch.setattr(preflight, "_service_active", lambda _unit: False)
    monkeypatch.setattr(preflight, "_listener", lambda _port: True)
    ok, reason = preflight.preflight(8080)
    assert ok is False
    assert "occupied" in reason


def test_appliance_preflight_accepts_its_own_compose_project(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(preflight, "_service_active", lambda unit: unit == "concierge.service")
    monkeypatch.setattr(preflight, "_docker_on_port", lambda _port, _project: (True, True))
    monkeypatch.setattr(preflight, "_listener", lambda _port: True)
    monkeypatch.setattr(preflight, "_foreign_uvicorn_active", lambda: False)

    ok, reason = preflight.preflight(8080)

    assert ok is True
    assert reason == "port and runtime preflight passed"


def test_stop_waits_for_listener_to_close_and_times_out_without_terminating_it(monkeypatch: pytest.MonkeyPatch):
    states = iter((True, True, False))
    monkeypatch.setattr(preflight, "_listener", lambda _port: next(states))
    monkeypatch.setattr(preflight.time, "sleep", lambda _seconds: None)
    assert preflight.wait_for_port_free(8080, timeout=1) is True

    monkeypatch.setattr(preflight, "_listener", lambda _port: True)
    assert preflight.wait_for_port_free(8080, timeout=0) is False


def test_active_appliance_supervisor_does_not_hide_an_unrelated_port_owner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(preflight, "_service_active", lambda unit: unit == "concierge.service")
    monkeypatch.setattr(preflight, "_docker_on_port", lambda _port, _project: (False, False))
    monkeypatch.setattr(preflight, "_listener", lambda _port: True)
    monkeypatch.setattr(preflight, "_foreign_uvicorn_active", lambda: False)

    ok, reason = preflight.preflight(8080)

    assert ok is False
    assert "occupied" in reason


def test_docker_dev_preflight_requires_its_own_port_and_project(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(preflight, "_service_active", lambda _unit: False)
    monkeypatch.setattr(preflight, "_docker_on_port", lambda _port, project: (True, project == "concierge-dev"))
    monkeypatch.setattr(preflight, "_listener", lambda _port: True)

    assert preflight.preflight(8081, mode="docker-dev") == (True, "port and runtime preflight passed")
    monkeypatch.setattr(preflight, "_docker_on_port", lambda _port, _project: (True, False))
    ok, reason = preflight.preflight(8081, mode="docker-dev")
    assert ok is False
    assert "different Docker Compose project" in reason


def test_docker_compose_wrapper_selects_isolated_projects_and_build_identity():
    script = ROOT / "deploy" / "docker-compose.sh"
    assert script.stat().st_mode & 0o111
    content = script.read_text(encoding="utf-8")
    assert 'project_name="concierge-dev-$project_suffix"' in content
    assert "project_name=concierge" in content
    assert "preflight.py" in content
    assert "CONCIERGE_COMMIT" in content


def test_macos_launch_daemons_run_preflight_before_binding_ports():
    server = (ROOT / "deploy/macos/com.conciergeai.server.plist").read_text(encoding="utf-8")
    proxy = (ROOT / "deploy/macos/com.conciergeai.proxy.plist").read_text(encoding="utf-8")
    app_wrapper = (ROOT / "deploy/common/run-app.sh").read_text(encoding="utf-8")
    proxy_wrapper = (ROOT / "deploy/macos/run-proxy.sh").read_text(encoding="utf-8")

    assert "preflight.py appliance" in app_wrapper
    assert "run-proxy.sh" in proxy
    assert "preflight.py" in proxy_wrapper
    assert "8080" in proxy_wrapper
    assert "run-app.sh" in server


def test_docker_compose_wrapper_passes_mode_project_and_build_identity(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-args.txt"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$CAPTURE_DOCKER_ARGS\"\n"
        "printf 'version=%s commit=%s date=%s\\n' \"$CONCIERGE_VERSION\" \"$CONCIERGE_COMMIT\" \"$CONCIERGE_BUILD_DATE\" >> \"$CAPTURE_DOCKER_ARGS\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "CAPTURE_DOCKER_ARGS": str(capture),
        "CONCIERGE_VERSION": "0.9.2",
        "CONCIERGE_COMMIT": "a1b2c3d4",
        "CONCIERGE_BUILD_DATE": "2026-10-06T01:02:03Z",
    }

    subprocess.run(["bash", str(ROOT / "deploy/docker-compose.sh"), "dev", "config", "--quiet"], env=environment, check=True)

    output = capture.read_text(encoding="utf-8")
    assert "concierge-dev-" in output
    assert "docker-compose.dev.yml" in output
    assert "version=0.9.2 commit=a1b2c3d4 date=2026-10-06T01:02:03Z" in output


def test_docker_compose_wrapper_sanitizes_dirty_describe_version(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured = tmp_path / "build-identity.txt"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s %s %s\\n' \"$CONCIERGE_VERSION\" \"$CONCIERGE_COMMIT\" \"$CONCIERGE_BUILD_DATE\" > \"$CAPTURE_BUILD_IDENTITY\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    git = fake_bin / "git"
    git.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in *describe*) printf '94b2cbd-dirty\\n' ;; *rev-parse*) printf '94b2cbd32260\\n' ;; *) exit 2 ;; esac\n",
        encoding="utf-8",
    )
    git.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "CAPTURE_BUILD_IDENTITY": str(captured),
    }
    for key in ("CONCIERGE_VERSION", "CONCIERGE_COMMIT", "CONCIERGE_BUILD_DATE"):
        environment.pop(key, None)

    result = subprocess.run(
        ["bash", str(ROOT / "deploy/docker-compose.sh"), "dev", "config", "--quiet"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    version, commit, build_date = captured.read_text(encoding="utf-8").split()
    assert version == "local"
    assert commit == "94b2cbd32260"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", build_date)


def test_source_port_preflight_refuses_docker_owned_port_and_allows_own_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(source_service, "port_in_use", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(source_service, "_listening_pids", lambda *_args: ["4321"])
    monkeypatch.setattr(source_service, "_expected_service_pids", lambda *_args: set())
    with pytest.raises(source_service.ServiceError, match="Port 8080 is already occupied"):
        source_service.assert_source_port_available(tmp_path, "linux")

    monkeypatch.setattr(source_service, "_expected_service_pids", lambda *_args: {"4321"})
    assert source_service.assert_source_port_available(tmp_path, "linux") is None
    with pytest.raises(source_service.ServiceError, match="Port 8080 is already occupied"):
        source_service.assert_source_port_available(tmp_path, "linux", allow_current_service=False)


def test_appliance_installers_refuse_to_replace_an_existing_release():
    linux = (ROOT / "deploy/linux/install.sh").read_text(encoding="utf-8")
    macos = (ROOT / "deploy/macos/install.sh").read_text(encoding="utf-8")

    assert 'if [ -e /opt/concierge/current ] || [ -L /opt/concierge/current ]; then' in linux
    assert "Use 'sudo concierge update' to upgrade" in linux
    assert 'if [ -e "$APP_ROOT/current" ] || [ -L "$APP_ROOT/current" ]; then' in macos
    assert "Use 'sudo concierge update' to upgrade" in macos


def test_appliance_update_and_maintenance_operations_share_one_lock():
    script = (ROOT / "deploy/common/concierge.sh").read_text(encoding="utf-8")
    assert 'update|backup|internal-backup|internal-health|internal-maintenance)' in script


def test_update_cli_reports_distinct_candidate_and_recovery_states():
    script = (ROOT / "deploy/common/concierge.sh").read_text(encoding="utf-8")
    runtime = (ROOT / "deploy/common/runtime.sh").read_text(encoding="utf-8")
    for message in (
        "backup creation",
        "backup verification",
        "migration failed",
        "candidate startup",
        "readiness validation",
        "Previous release pointer restored",
        "previous release cannot read the current database schema",
        "previous release started successfully and passed readiness. Application rollback: SUCCESS.",
        "Operator recovery required",
    ):
        assert message in script
    assert "Could not download stable release" in runtime
    assert "SHA-256 verification failed" in runtime


def test_backup_includes_verifiable_secret_free_build_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_VERSION", "0.9.2")
    monkeypatch.setenv("CONCIERGE_COMMIT", "a1b2c3d4")
    monkeypatch.setenv("CONCIERGE_DEPLOYMENT_MODE", "appliance")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_SECRET", "backup-does-not-record-secrets")
    monkeypatch.setattr(__import__("app.backup", fromlist=["BUILD_IDENTITY"]), "BUILD_IDENTITY", {
        "version": "0.9.2", "commit": "a1b2c3d4", "deployment_mode": "appliance",
    })
    database_path = tmp_path / "backup.db"
    PropertyStore(database_path).upsert(PropertyRecord(property_id="backup-property", hotel_name="Backup Hotel"))
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    archive_path = tmp_path / "backup.zip"

    created = create_backup(database_path, upload_root, archive_path)
    verification = verify_backup(archive_path)

    assert created["files"] == 1
    assert verification["valid"] is True
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["concierge"] == {
        "version": "0.9.2",
        "commit": "a1b2c3d4",
        "deployment_mode": "appliance",
        "schema_revision": database.CURRENT_SCHEMA_REVISION,
        "minimum_schema_revision": database.CURRENT_SCHEMA_REVISION,
        "maximum_schema_revision": database.CURRENT_SCHEMA_REVISION,
        "build_date": "unknown",
    }
    assert "backup-does-not-record-secrets" not in json.dumps(manifest)


@pytest.mark.parametrize(
    ("pointer_restored", "service_started", "health_passed", "expected"),
    [
        (False, False, False, "pointer_restore_failed"),
        (True, False, False, "previous_release_start_failed"),
        (True, True, False, "previous_release_unhealthy"),
        (True, True, True, "rollback_success"),
    ],
)
def test_rollback_decision_reports_exact_recovery_state(pointer_restored, service_started, health_passed, expected):
    assert update_decision.rollback_decision(
        pointer_restored=pointer_restored, service_started=service_started, health_passed=health_passed
    ) == expected


def test_rollback_decision_does_not_start_incompatible_previous_release():
    assert update_decision.rollback_decision(
        pointer_restored=True,
        service_started=False,
        health_passed=False,
        previous_schema_compatible=False,
    ) == "operator_recovery_required_schema_incompatible"


@pytest.mark.parametrize(
    ("docker", "services", "manual", "in_container", "expected"),
    [
        ([{"ports": "127.0.0.1:8081->8080/tcp"}], {}, [], False, "docker-dev"),
        ([{"ports": "127.0.0.1:8080->80/tcp"}], {}, [], False, "appliance"),
        ([], {"concierge-ai.service": "active/running"}, [], False, "source"),
        ([], {}, [], True, "appliance"),
    ],
)
def test_deployment_mode_detection(docker, services, manual, in_container, expected, tmp_path: Path):
    assert diagnostics.detect_mode(
        root=tmp_path, docker=docker, services=services, manual=manual, in_container=in_container
    ) == expected


def test_port_owner_detection_prints_only_pid_and_process_name(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_run(command, timeout=2):
        calls.append(command)
        if command[0] == "lsof":
            return SimpleNamespace(returncode=0, stdout="123\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="docker-proxy\n", stderr="")

    monkeypatch.setattr(diagnostics, "_run", fake_run)

    owner = diagnostics._port_owner(8080)

    assert owner == ["docker-proxy (pid 123)"]
    assert calls[0][0] == "lsof"
    assert all("args" not in command for command in calls)


def test_doctor_marks_simultaneous_source_and_docker_runtime_as_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state"
    state.mkdir()
    args = SimpleNamespace(
        mode="appliance", root=tmp_path, config=None, state_directory=state, manifest=None,
        base_url="http://127.0.0.1:8080", bind="127.0.0.1", port=8080,
    )
    monkeypatch.setattr(diagnostics, "_docker_runtimes", lambda: [
        {"name": "concierge-concierge-1", "status": "Up", "ports": "127.0.0.1:8080->80/tcp"},
    ])
    monkeypatch.setattr(diagnostics, "_service_state", lambda command: (
        "active/running; restarts=5" if command[2] == "concierge-ai.service" or "com.conciergeai.source" in command[2] else "not installed"
    ))
    monkeypatch.setattr(diagnostics, "_manual_runtimes", lambda: [])
    monkeypatch.setattr(diagnostics, "_request", lambda url, timeout=3: (
        (200, {"status": "ok"}, None) if url.endswith("/health/live") else
        (503, None, "Database is not ready.") if url.endswith("/health/ready") else
        (200, {"version": "0.9.2", "commit": "abc123", "schema_revision": "20261005_0001"}, None)
    ))
    monkeypatch.setattr(diagnostics, "_port_owner", lambda _port: ["docker-proxy (pid 123)"])
    monkeypatch.setattr(diagnostics, "_can_connect", lambda _port: True)

    data = diagnostics.collect(args)
    rendered = diagnostics.render_doctor(data)

    assert data["conflict"] is True
    assert "Multiple Concierge.AI runtimes are configured" in rendered
