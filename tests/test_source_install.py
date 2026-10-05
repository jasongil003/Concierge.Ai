from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from app.admin_auth import AdminAuthStore, hash_password
from deploy import source_install, source_service, source_venv


REPO_ROOT = Path(__file__).resolve().parents[1]


def _source_tree(tmp_path: Path) -> Path:
    root = tmp_path / "Concierge.Ai source"
    root.mkdir()
    (root / ".env.example").write_text(
        "DB_PATH=state/concierge.db\n"
        "UPLOAD_ROOT=state/uploads\n"
        "DATABASE_URL=\n"
        "APP_ENVIRONMENT=development\n"
        "ADMIN_BOOTSTRAP_USERNAME=root\n"
        "ADMIN_BOOTSTRAP_PASSWORD=admin\n"
        "CREDENTIAL_ENCRYPTION_SECRET=\n",
        encoding="utf-8",
    )
    return root


def test_fresh_configuration_creates_private_env_secret_and_root_bootstrap(tmp_path: Path):
    root = _source_tree(tmp_path)

    secret_status, admin_status, existing_admin = source_install.prepare_environment(root)

    values = dotenv_values(root / ".env")
    assert secret_status == "generated"
    assert admin_status == "default"
    assert existing_admin is False
    assert values["ADMIN_BOOTSTRAP_USERNAME"] == "root"
    assert values["ADMIN_BOOTSTRAP_PASSWORD"] == "admin"
    secret = values["CREDENTIAL_ENCRYPTION_SECRET"]
    assert isinstance(secret, str) and len(secret) >= 32
    assert (root / ".env").stat().st_mode & 0o777 == 0o600


def test_virtual_environment_creation_and_repeat_are_idempotent(tmp_path: Path):
    root = _source_tree(tmp_path)

    assert source_venv.ensure_venv(root) == "created"
    assert (root / ".venv" / "bin" / "python").is_file()
    result = subprocess.run(
        [str(root / ".venv" / "bin" / "python"), "-c", "import sys; print(sys.prefix)"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert str(root / ".venv") in result.stdout
    assert source_venv.ensure_venv(root) == "existing"
    assert source_venv.supported_python((3, 12)) is True
    assert source_venv.supported_python((3, 11)) is True
    assert source_venv.supported_python((3, 10)) is False
    assert source_venv.supported_python((3, 15)) is False


def test_installer_output_never_discloses_generated_secret(tmp_path: Path):
    root = _source_tree(tmp_path)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "deploy/source_install.py"), "prepare", "--root", str(root)],
        text=True,
        capture_output=True,
        check=True,
    )
    secret = dotenv_values(root / ".env")["CREDENTIAL_ENCRYPTION_SECRET"]
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert "secret=generated" in result.stdout


def test_valid_secret_and_existing_bootstrap_configuration_are_preserved(tmp_path: Path):
    root = _source_tree(tmp_path)
    existing_secret = "kept-encryption-secret-value-1234567890"
    (root / ".env").write_text(
        "DB_PATH=state/concierge.db\n"
        "UPLOAD_ROOT=state/uploads\n"
        "APP_ENVIRONMENT=development\n"
        "ADMIN_BOOTSTRAP_USERNAME=owner\n"
        "ADMIN_BOOTSTRAP_PASSWORD=OwnerPassword123!\n"
        f"CREDENTIAL_ENCRYPTION_SECRET={existing_secret}\n",
        encoding="utf-8",
    )

    secret_status, admin_status, _ = source_install.prepare_environment(root)

    values = dotenv_values(root / ".env")
    assert secret_status == "preserved"
    assert admin_status == "preserved"
    assert values["CREDENTIAL_ENCRYPTION_SECRET"] == existing_secret
    assert values["ADMIN_BOOTSTRAP_USERNAME"] == "owner"
    assert values["ADMIN_BOOTSTRAP_PASSWORD"] == "OwnerPassword123!"


def test_placeholder_encryption_secret_is_regenerated(tmp_path: Path):
    root = _source_tree(tmp_path)
    (root / ".env").write_text(
        "DB_PATH=state/concierge.db\n"
        "ADMIN_BOOTSTRAP_USERNAME=root\n"
        "ADMIN_BOOTSTRAP_PASSWORD=admin\n"
        "CREDENTIAL_ENCRYPTION_SECRET=short\n",
        encoding="utf-8",
    )

    secret_status, _, _ = source_install.prepare_environment(root)

    secret = dotenv_values(root / ".env")["CREDENTIAL_ENCRYPTION_SECRET"]
    assert secret_status == "generated"
    assert secret != "short"
    assert len(secret) >= 32


def test_existing_administrator_and_password_are_preserved_on_reinstall(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    root = _source_tree(tmp_path)
    source_install.prepare_environment(root)
    db_path = root / "state" / "concierge.db"
    store = AdminAuthStore(db_path)
    store.ensure_bootstrap_admin("owner", "OwnerPassword123!", "Existing Owner")
    with sqlite3.connect(db_path) as db:
        before_hash = db.execute("SELECT password_hash FROM admin_users WHERE normalized_username='owner'").fetchone()[0]
    secret_before = dotenv_values(root / ".env")["CREDENTIAL_ENCRYPTION_SECRET"]

    secret_status, admin_status, existing_admin = source_install.prepare_environment(root)
    store.ensure_bootstrap_admin("root", "admin")

    values = dotenv_values(root / ".env")
    with sqlite3.connect(db_path) as db:
        after_hash = db.execute("SELECT password_hash FROM admin_users WHERE normalized_username='owner'").fetchone()[0]
        root_account = db.execute("SELECT 1 FROM admin_users WHERE normalized_username='root'").fetchone()
    assert existing_admin is True
    assert secret_status == "preserved"
    assert admin_status == "preserved"
    assert values["CREDENTIAL_ENCRYPTION_SECRET"] == secret_before
    assert before_hash == after_hash
    assert root_account is None
    assert store.login("owner", "OwnerPassword123!", "127.0.0.1", "installer-test")[1].username == "owner"


def test_only_initial_root_admin_uses_the_builtin_weak_password(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = AdminAuthStore(tmp_path / "bootstrap.db")
    store.ensure_bootstrap_admin("root", "admin")

    _, principal = store.login("root", "admin", "127.0.0.1", "installer-test")

    assert principal.using_default_password is True
    assert principal.show_default_password_prompt is True
    assert principal.force_password_change is False
    store.dismiss_default_password_prompt(principal)
    _, dismissed_principal = store.login("root", "admin", "127.0.0.1", "installer-test")
    assert dismissed_principal.show_default_password_prompt is False
    assert dismissed_principal.using_default_password is True
    with pytest.raises(ValueError, match="12 characters"):
        hash_password("admin")
    with pytest.raises(ValueError, match="12 characters"):
        store.create_user(
            {
                "username": "ordinary-user",
                "display_name": "Ordinary User",
                "password": "admin",
                "role_id": "role-super-admin",
            },
            actor=None,
        )


def test_bootstrap_config_accepts_only_builtin_weak_password_in_every_mode():
    assert source_install._valid_admin_bootstrap("root", "admin", "development") is True
    assert source_install._valid_admin_bootstrap("root", "admin", "production") is True
    assert source_install._valid_admin_bootstrap("owner", "OwnerPassword123!", "production") is True
    assert source_install._valid_admin_bootstrap("owner", "admin", "production") is False


def test_platform_detection_handles_linux_wsl_macos_and_unsupported(tmp_path: Path):
    os_release = tmp_path / "os-release"
    proc_version = tmp_path / "version"
    os_release.write_text('NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 26.04 LTS"\n', encoding="utf-8")
    proc_version.write_text("Linux version 6.6.0-microsoft-standard-WSL2", encoding="utf-8")
    assert source_install.detect_platform("Linux", os_release=os_release, proc_version=proc_version) == (
        "linux",
        "Ubuntu 26.04 LTS under WSL2",
    )
    proc_version.write_text("Linux version 6.8.0", encoding="utf-8")
    assert source_install.detect_platform("Linux", os_release=os_release, proc_version=proc_version) == (
        "linux",
        "Ubuntu 26.04 LTS",
    )
    mac_platform, mac_label = source_install.detect_platform("Darwin")
    assert mac_platform == "macos"
    assert mac_label.startswith("macOS")
    with pytest.raises(source_install.InstallerError, match="Unsupported operating system"):
        source_install.detect_platform("Windows")


def test_sqlite_initializer_creates_directories_and_runs_app_bootstrap(tmp_path: Path):
    root = _source_tree(tmp_path)
    source_install.prepare_environment(root)
    commands: list[list[str]] = []

    def runner(command, **kwargs):
        commands.append(command)
        if "source_admin_exists" in command[-1]:
            return SimpleNamespace(stdout="source_admin_exists=no\n")
        if "TestClient" in command[-1]:
            db_path = root / "state" / "concierge.db"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE IF NOT EXISTS admin_users (username TEXT)")
                db.execute("INSERT INTO admin_users (username) VALUES ('root')")
            return SimpleNamespace(stdout="")
        raise AssertionError(command)

    database, existed = source_install.initialize_application(root, Path(sys.executable), runner=runner)

    assert database == "sqlite"
    assert existed is False
    assert not any("alembic" in command for command in commands)
    assert (root / "state" / "uploads").is_dir()


def test_postgresql_configuration_runs_alembic_before_application_initialization(tmp_path: Path):
    root = _source_tree(tmp_path)
    source_install.prepare_environment(root)
    env_path = root / ".env"
    env_path.write_text(
        env_path.read_text(encoding="utf-8").replace(
            "DATABASE_URL=", "DATABASE_URL=postgresql://example.invalid/concierge"
        ),
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def runner(command, **kwargs):
        commands.append(command)
        if "alembic" in command:
            assert kwargs["env"]["DATABASE_URL"].startswith("postgresql://")
            return SimpleNamespace(stdout="")
        if "source_admin_exists" in command[-1]:
            return SimpleNamespace(stdout="source_admin_exists=no\n")
        if "TestClient" in command[-1]:
            return SimpleNamespace(stdout="")
        raise AssertionError(command)

    database, existed = source_install.initialize_application(root, Path(sys.executable), runner=runner)

    assert database == "postgresql"
    assert existed is False
    assert "-m" in commands[0] and "alembic" in commands[0]
    assert any("TestClient" in command[-1] for command in commands)


def test_missing_node_and_ollama_are_reported_as_optional(tmp_path: Path):
    status = source_install.optional_dependency_status(path=str(tmp_path))
    assert status == {"node": False, "npm": False, "ollama": False}


def test_systemd_and_launchd_service_definitions_run_as_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "Concierge source tree"
    root.mkdir()
    unit = source_service._unit_text(root, "concierge-user", "staff")
    assert 'User=concierge-user' in unit
    assert 'Group=staff' in unit
    assert f"WorkingDirectory={root}" in unit
    assert f"EnvironmentFile={root}/.env" in unit
    assert f'ExecStart="{root}/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-proxy-headers' in unit
    assert 'Restart=always' in unit
    assert 'RestartSec=5' in unit
    assert 'TimeoutStopSec=45' in unit
    assert 'UMask=0077' in unit
    assert 'NoNewPrivileges=true' in unit

    monkeypatch.setattr(source_service, "_user_home", lambda user: tmp_path / "home")
    path, launch_agent = source_service._launch_agent(root, "concierge-user")
    assert path.parent == tmp_path / "home" / "Library" / "LaunchAgents"
    assert launch_agent["KeepAlive"] is True
    assert launch_agent["WorkingDirectory"] == str(root)
    assert "UserName" not in launch_agent


def test_systemd_path_directives_are_unquoted_and_escape_specifiers(tmp_path: Path):
    plain_root = tmp_path / "Concierge.Ai"
    plain_unit = source_service._unit_text(plain_root, "concierge-user", "staff")
    assert f"WorkingDirectory={plain_root}" in plain_unit
    assert f"EnvironmentFile={plain_root}/.env" in plain_unit

    spaced_root = tmp_path / "Concierge 100% ready"
    spaced_unit = source_service._unit_text(spaced_root, "concierge-user", "staff")
    assert f"WorkingDirectory={str(spaced_root).replace('%', '%%')}" in spaced_unit
    assert f"EnvironmentFile={str(spaced_root).replace('%', '%%')}/.env" in spaced_unit
    assert f'ExecStart="{str(spaced_root).replace("%", "%%")}/.venv/bin/python"' in spaced_unit


def test_systemd_environment_file_escapes_glob_characters(tmp_path: Path):
    root = tmp_path / r"Concierge [blue]*? 100% ready\checkout"
    unit = source_service._unit_text(root, "concierge-user", "staff")
    expected_path = str(root / ".env").replace("%", "%%")
    expected_path = "".join(f"\\{character}" if character in "\\*?[]" else character for character in expected_path)

    assert f"EnvironmentFile={expected_path}" in unit
    assert 'EnvironmentFile="' not in unit


@pytest.mark.parametrize("legacy_format", [False, True])
def test_systemd_service_ownership_and_reinstall_are_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_format: bool
):
    root = tmp_path / "Concierge source tree"
    root.mkdir()
    root = root.resolve()
    unit_path = tmp_path / "etc" / source_service.SERVICE_NAME
    unit_path.parent.mkdir()
    unit_text = source_service._unit_text(root, "concierge-user", "staff")
    if legacy_format:
        unit_text = unit_text.replace(
            f"WorkingDirectory={source_service._systemd_path_value(str(root))}",
            f"WorkingDirectory={source_service._quote_unit(str(root))}",
        )
    unit_path.write_text(unit_text, encoding="utf-8")
    monkeypatch.setattr(source_service, "_platform_mode", lambda _platform: "systemd")
    monkeypatch.setattr(source_service, "_unit_path", lambda _root: unit_path)

    assert source_service.service_owned(root, "linux") is True

    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        if args[0] == "install":
            Path(args[-1]).write_text(Path(args[-2]).read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(source_service, "_run", fake_run)
    for _ in range(2):
        source_service._install_systemd(root, "concierge-user", "staff", start=True, unattended=True)

    assert unit_path.read_text(encoding="utf-8") == source_service._unit_text(root, "concierge-user", "staff")
    assert [args[0] for args in calls] == ["install", "systemctl", "systemctl", "systemctl"] * 2
    assert source_service.service_owned(root, "linux") is True

    other_root = tmp_path / "another checkout"
    other_unit = source_service._unit_text(other_root, "concierge-user", "staff")
    unit_path.write_text(other_unit, encoding="utf-8")
    with pytest.raises(source_service.ServiceError, match="different Concierge.AI checkout"):
        source_service._install_systemd(root, "concierge-user", "staff", start=False, unattended=True)


def test_systemd_analyze_verifies_generated_unit_when_available(tmp_path: Path):
    import getpass
    import grp
    import shutil

    systemd_analyze = shutil.which("systemd-analyze")
    if not systemd_analyze:
        pytest.skip("systemd-analyze is not installed on this host")

    root = tmp_path / "Concierge 100% ready"
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    (root / ".env").write_text("APP_ENVIRONMENT=development\n", encoding="utf-8")
    group = grp.getgrgid(os.getgid()).gr_name
    unit_path = tmp_path / source_service.SERVICE_NAME
    unit_path.write_text(source_service._unit_text(root, getpass.getuser(), group), encoding="utf-8")

    result = subprocess.run([systemd_analyze, "verify", str(unit_path)], text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stdout + result.stderr


def test_fallback_service_install_and_health_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import getpass

    monkeypatch.setattr(source_service, "_platform_mode", lambda _platform: "fallback")
    started: list[Path] = []
    monkeypatch.setattr(source_service, "_fallback_start", lambda root: started.append(root))
    mode = source_service.install_service(tmp_path, "linux", getpass.getuser(), True, False)
    assert mode == "fallback"
    assert started == [tmp_path.resolve()]

    def fail_request(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(source_service.urllib.request, "urlopen", fail_request)
    healthy, message = source_service.check_health(timeout=0.1)
    assert healthy is False
    assert "/health/live" in message


def test_fallback_reinstall_restarts_existing_source_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import getpass

    calls: list[str] = []
    monkeypatch.setattr(source_service, "_platform_mode", lambda _platform: "fallback")
    monkeypatch.setattr(source_service, "_fallback_running", lambda _root: 12345)
    monkeypatch.setattr(source_service, "_fallback_stop", lambda _root: calls.append("stop"))
    monkeypatch.setattr(source_service, "_fallback_start", lambda _root: calls.append("start"))

    source_service.install_service(tmp_path, "linux", getpass.getuser(), True, False)

    assert calls == ["stop", "start"]


def test_service_restart_command_uses_platform_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[Path, str, bool]] = []
    monkeypatch.setattr(sys, "argv", [
        "source_service.py", "--root", str(tmp_path), "--platform", "linux", "restart"
    ])
    monkeypatch.setattr(
        source_service,
        "restart_service",
        lambda root, platform, unattended: calls.append((root, platform, unattended)),
    )

    assert source_service.main() == 0
    assert calls == [(tmp_path.resolve(), "linux", False)]


def test_launchd_restart_kickstarts_loaded_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(source_service, "_platform_mode", lambda _platform: "launchd")
    monkeypatch.setattr(source_service, "service_owned", lambda _root, _platform: True)
    monkeypatch.setattr(source_service, "_launchd_loaded", lambda _target: True)
    monkeypatch.setattr(source_service, "_run", lambda args, **_kwargs: calls.append(args))

    source_service.restart_service(tmp_path, "macos", unattended=False)

    assert calls == [["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{source_service.LAUNCHD_LABEL}"]]


@pytest.mark.parametrize(("platform", "mode"), [("linux", "systemd"), ("macos", "launchd")])
def test_start_without_an_installed_optional_service_uses_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, mode: str
):
    started: list[Path] = []
    monkeypatch.setattr(source_service, "_platform_mode", lambda _platform: mode)
    monkeypatch.setattr(source_service, "service_owned", lambda _root, _platform: False)
    monkeypatch.setattr(source_service, "_fallback_start", lambda root: started.append(root))

    source_service.start_service(tmp_path, platform, unattended=False)

    assert started == [tmp_path.resolve()]


def test_port_occupancy_and_install_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class OccupiedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def connect_ex(self, _address):
            return 0

    monkeypatch.setattr(source_service.socket, "socket", lambda *_args: OccupiedSocket())
    assert source_service.port_in_use() is True

    root = _source_tree(tmp_path)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "deploy/source_install.py"), "prepare", "--root", str(root / "missing")],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "missing" in result.stderr.lower() or "installer error" in result.stderr.lower()
