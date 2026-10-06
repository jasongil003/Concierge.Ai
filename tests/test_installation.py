from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import sys

from dotenv import dotenv_values
import pytest

from app.admin_auth import AdminAuthStore, AuthenticationError
from deploy import source_install


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_env_example(root: Path, secret: str = "") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".env.example").write_text(
        "APP_NAME=Concierge.Ai\n"
        "DB_PATH=state/concierge.db\n"
        "UPLOAD_ROOT=state/uploads\n"
        "ADMIN_BOOTSTRAP_USERNAME=root\n"
        "ADMIN_BOOTSTRAP_PASSWORD=admin\n"
        f"CREDENTIAL_ENCRYPTION_SECRET={secret}\n",
        encoding="utf-8",
    )


def test_fresh_environment_uses_secure_generation_and_hides_secret(
    tmp_path: Path, monkeypatch, capsys
):
    _write_env_example(tmp_path)
    calls: list[int] = []
    token_urlsafe = source_install.secrets.token_urlsafe

    def tracked_token_urlsafe(length: int) -> str:
        calls.append(length)
        return token_urlsafe(length)

    monkeypatch.setattr(source_install.secrets, "token_urlsafe", tracked_token_urlsafe)
    monkeypatch.setattr(
        sys,
        "argv",
        ["source_install.py", "prepare", "--root", str(tmp_path)],
    )
    assert source_install.main() == 0
    output = capsys.readouterr().out
    values = dotenv_values(tmp_path / ".env")
    secret = values["CREDENTIAL_ENCRYPTION_SECRET"]

    assert calls == [48]
    assert len(secret) >= 32
    assert values["ADMIN_BOOTSTRAP_USERNAME"] == "root"
    assert values["ADMIN_BOOTSTRAP_PASSWORD"] == "admin"
    assert "secret=generated" in output
    assert secret not in output
    if os.name != "nt":
        assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600


def test_invalid_secret_is_replaced_and_valid_secret_and_custom_settings_are_preserved(
    tmp_path: Path,
):
    _write_env_example(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_NAME=Locally Customized\n"
        "ADMIN_BOOTSTRAP_USERNAME=root\n"
        "ADMIN_BOOTSTRAP_PASSWORD=admin\n"
        "CREDENTIAL_ENCRYPTION_SECRET=replace-me\n",
        encoding="utf-8",
    )
    source_install.prepare_environment(tmp_path)
    generated = dotenv_values(env_file)["CREDENTIAL_ENCRYPTION_SECRET"]
    assert len(generated) >= 32
    assert generated != "replace-me"

    source_install.prepare_environment(tmp_path)
    values = dotenv_values(env_file)
    assert values["CREDENTIAL_ENCRYPTION_SECRET"] == generated
    assert values["APP_NAME"] == "Locally Customized"
    assert values["ADMIN_BOOTSTRAP_USERNAME"] == "root"
    assert values["ADMIN_BOOTSTRAP_PASSWORD"] == "admin"


def test_installation_rerun_preserves_encryption_key_database_and_admin_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Exercise a normal source install in its temporary root, not the pytest
    # process profile inherited by the installer subprocess.
    for variable in ("APP_ENVIRONMENT", "CONCIERGE_TESTING", "DB_PATH", "STATE_DIRECTORY", "UPLOAD_ROOT"):
        monkeypatch.delenv(variable, raising=False)
    (tmp_path / "app").symlink_to(PROJECT_ROOT / "app", target_is_directory=True)
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "source_install.py").symlink_to(
        PROJECT_ROOT / "deploy" / "source_install.py"
    )
    shutil.copyfile(PROJECT_ROOT / ".env.example", tmp_path / ".env.example")

    source_install.prepare_environment(tmp_path)
    database_kind, existing_admin = source_install.initialize_application(tmp_path, Path(sys.executable))
    assert database_kind == "sqlite"
    assert existing_admin is False

    db_path = tmp_path / "state" / "concierge.db"
    secret_before = dotenv_values(tmp_path / ".env")["CREDENTIAL_ENCRYPTION_SECRET"]
    auth = AdminAuthStore(db_path)
    _, root = auth.login("root", "admin", "127.0.0.1", "installer-test")
    auth.change_password(root, "admin", "Secure-Installer-Password-123!")
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS install_test_marker (value TEXT NOT NULL)")
        db.execute("INSERT INTO install_test_marker(value) VALUES ('preserve-me')")

    source_install.prepare_environment(tmp_path)
    database_kind, existing_admin = source_install.initialize_application(tmp_path, Path(sys.executable))
    assert database_kind == "sqlite"
    assert existing_admin is True
    assert dotenv_values(tmp_path / ".env")["CREDENTIAL_ENCRYPTION_SECRET"] == secret_before
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT value FROM install_test_marker").fetchall() == [("preserve-me",)]

    auth_after_rerun = AdminAuthStore(db_path)
    with pytest.raises(AuthenticationError):
        auth_after_rerun.login("root", "admin", "127.0.0.1", "installer-test")
    _, principal = auth_after_rerun.login(
        "root", "Secure-Installer-Password-123!", "127.0.0.1", "installer-test"
    )
    assert principal.using_default_password is False
    assert auth_after_rerun.get_user(principal.user_id)["using_default_password"] is False
