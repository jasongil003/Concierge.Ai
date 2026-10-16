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
        "CREDENTIAL_ENCRYPTION_SECRET=\n"
        "CONCIERGE_BACKUP_ENCRYPTION_KEY=\n",
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
    assert len(values["CONCIERGE_BACKUP_ENCRYPTION_KEY"]) == 64
    assert all(char in "0123456789abcdef" for char in values["CONCIERGE_BACKUP_ENCRYPTION_KEY"])
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
    backup_key = dotenv_values(root / ".env")["CONCIERGE_BACKUP_ENCRYPTION_KEY"]
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert backup_key not in result.stdout + result.stderr
    assert "secret=generated" in result.stdout


def test_valid_secret_and_existing_bootstrap_configuration_are_preserved(tmp_path: Path):
    root = _source_tree(tmp_path)
    existing_secret = "kept-encryption-secret-value-1234567890"
    existing_backup_key = "de" * 32
    (root / ".env").write_text(
        "DB_PATH=state/concierge.db\n"
        "UPLOAD_ROOT=state/uploads\n"
        "APP_ENVIRONMENT=development\n"
        "ADMIN_BOOTSTRAP_USERNAME=owner\n"
        "ADMIN_BOOTSTRAP_PASSWORD=OwnerPassword123!\n"
        f"CREDENTIAL_ENCRYPTION_SECRET={existing_secret}\n"
        f"CONCIERGE_BACKUP_ENCRYPTION_KEY={existing_backup_key}\n",
        encoding="utf-8",
    )

    secret_status, admin_status, _ = source_install.prepare_environment(root)

    values = dotenv_values(root / ".env")
    assert secret_status == "preserved"
    assert admin_status == "preserved"
    assert values["CREDENTIAL_ENCRYPTION_SECRET"] == existing_secret
    assert values["CONCIERGE_BACKUP_ENCRYPTION_KEY"] == existing_backup_key
    assert v