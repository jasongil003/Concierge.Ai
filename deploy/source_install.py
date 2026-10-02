#!/usr/bin/env python3
"""Small, idempotent helpers for installing a checked-out source tree."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values


PLACEHOLDER_SECRETS = {
    "",
    "change-me",
    "changeme",
    "default",
    "replace-me",
    "your-secret-here",
    "replace-with-a-random-value",
}


class InstallerError(RuntimeError):
    """An actionable source-installer failure."""


def detect_platform(
    system: str | None = None,
    *,
    os_release: Path = Path("/etc/os-release"),
    proc_version: Path = Path("/proc/version"),
    wsl_distro_name: str | None = None,
) -> tuple[str, str]:
    """Return (platform, display label), with WSL identified as a Linux path."""
    system = system or os.uname().sysname
    if system == "Darwin":
        version = ""
        sw_vers = shutil.which("sw_vers")
        if sw_vers:
            try:
                version = subprocess.check_output(
                    [sw_vers, "-productVersion"], text=True, stderr=subprocess.DEVNULL
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                pass
        return "macos", f"macOS{f' {version}' if version else ''}"
    if system != "Linux":
        raise InstallerError(f"Unsupported operating system: {system}. Supported platforms are Ubuntu/Linux and macOS.")

    release: dict[str, str] = {}
    try:
        for line in os_release.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
            if match:
                release[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    distro = wsl_distro_name or release.get("PRETTY_NAME") or release.get("NAME") or "Linux"
    try:
        is_wsl = bool(wsl_distro_name) or "microsoft" in proc_version.read_text(encoding="utf-8").casefold()
    except OSError:
        is_wsl = bool(wsl_distro_name)
    if is_wsl:
        try:
            wsl2 = "wsl2" in proc_version.read_text(encoding="utf-8").casefold()
        except OSError:
            wsl2 = False
        return "linux", f"{distro} under WSL{'2' if wsl2 else ''}"
    return "linux", distro


def _read_env(path: Path) -> dict[str, str]:
    parsed = dotenv_values(path)
    return {key: value for key, value in parsed.items() if key and value is not None}


def _sqlite_admin_count(root: Path, values: dict[str, str]) -> int:
    db_path = Path(values.get("DB_PATH", "state/concierge.db")).expanduser()
    if not db_path.is_absolute():
        db_path = root / db_path
    if not db_path.is_file():
        return 0
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
            table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_users'"
            ).fetchone()
            if not table:
                return 0
            return int(db.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0])
    except sqlite3.DatabaseError:
        # Leave corrupt or unfamiliar databases untouched; application startup
        # will report the underlying database error with its normal diagnostics.
        return 0


def _is_valid_encryption_secret(secret: str) -> bool:
    folded = secret.strip().casefold()
    return len(secret.strip()) >= 32 and folded not in PLACEHOLDER_SECRETS and "replace-with" not in folded


def _valid_admin_bootstrap(username: str, password: str, app_environment: str = "development") -> bool:
    # The exact built-in credentials are intentionally valid in every
    # deployment mode. Other account passwords still use the normal policy.
    if username.casefold() == "root" and password == "admin":
        return True
    return (
        len(password) >= 12
        and re.search(r"[a-z]", password) is not None
        and re.search(r"[A-Z]", password) is not None
        and re.search(r"\d", password) is not None
        and re.search(r"[^A-Za-z0-9]", password) is not None
        and password != "ChangeMe123!"
    )


def _generate_admin_bootstrap_password() -> str:
    while True:
        candidate = secrets.token_urlsafe(48)
        if _valid_admin_bootstrap("bootstrap", candidate):
            return candidate


def _write_env_updates(path: Path, updates: dict[str, str]) -> None:
    content = path.read_text(encoding="utf-8")
    replaced: set[str] = set()
    output: list[str] = []
    for line in content.splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        key = match.group(1) if match else None
        if key in updates:
            if key not in replaced:
                output.append(f"{key}={updates[key]}")
                replaced.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in replaced:
            output.append(f"{key}={value}")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            temporary.write("\n".join(output) + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def prepare_environment(root: Path) -> tuple[str, str, bool]:
    """Create local configuration, filling only missing/unsafe install values."""
    root = root.resolve()
    env_path = root / ".env"
    template_path = root / ".env.example"
    created = not env_path.exists()
    if created:
        if not template_path.is_file():
            raise InstallerError(".env.example is missing from this source checkout.")
        shutil.copyfile(template_path, env_path)

    values = _read_env(env_path)
    app_environment = values.get("APP_ENVIRONMENT", "development").strip().casefold()
    has_admin = _sqlite_admin_count(root, values) > 0
    updates: dict[str, str] = {}

    secret = values.get("CREDENTIAL_ENCRYPTION_SECRET", "").strip()
    secret_status = "preserved"
    if not _is_valid_encryption_secret(secret):
        updates["CREDENTIAL_ENCRYPTION_SECRET"] = secrets.token_urlsafe(48)
        secret_status = "generated"

    username = values.get("ADMIN_BOOTSTRAP_USERNAME", "").strip()
    password = values.get("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
    admin_status = "preserved"
    if created:
        updates["ADMIN_BOOTSTRAP_USERNAME"] = "root"
        updates["ADMIN_BOOTSTRAP_PASSWORD"] = "admin"
        admin_status = "default"
    elif not password:
        if has_admin:
            # This value is never used to modify an existing administrator.
            updates["ADMIN_BOOTSTRAP_PASSWORD"] = _generate_admin_bootstrap_password()
            admin_status = "existing"
        elif not username or username.casefold() in {"admin", "root"}:
            updates["ADMIN_BOOTSTRAP_USERNAME"] = "root"
            updates["ADMIN_BOOTSTRAP_PASSWORD"] = "admin"
            admin_status = "default"
        else:
            raise InstallerError(
                "ADMIN_BOOTSTRAP_PASSWORD is blank for a custom bootstrap username. Set a password of at least 12 characters in .env."
            )
    else:
        check_username = username or "admin"
        if not _valid_admin_bootstrap(check_username, password, app_environment):
            raise InstallerError(
                "ADMIN_BOOTSTRAP_PASSWORD is invalid. Use at least 12 characters; only the initial root/admin account may use the default."
            )

    if updates:
        _write_env_updates(env_path, updates)
    try:
        os.chmod(env_path, 0o600)
    except OSError as exc:
        raise InstallerError(f"Could not protect .env with mode 600: {exc}") from exc
    return secret_status, admin_status, has_admin


def initialize_application(root: Path, python: Path, runner: Callable = subprocess.run) -> tuple[str, bool]:
    """Run configured DB migrations and initialize app-owned SQLite/bootstrap schema."""
    root = root.resolve()
    env_path = root / ".env"
    values = _read_env(env_path)
    db_path = Path(values.get("DB_PATH", "state/concierge.db")).expanduser()
    if not db_path.is_absolute():
        db_path = root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_root = Path(values.get("UPLOAD_ROOT", str(db_path.parent / "uploads"))).expanduser()
    if not upload_root.is_absolute():
        upload_root = root / upload_root
    upload_root.mkdir(parents=True, exist_ok=True)

    child_env = os.environ.copy()
    child_env.update(values)
    database_url = values.get("DATABASE_URL", "").strip()
    before_admin = _sqlite_admin_count(root, values) > 0
    if database_url:
        if not database_url.casefold().startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
            raise InstallerError("DATABASE_URL must use PostgreSQL when configured for source installation.")
        runner(
            [str(python), "-m", "alembic", "upgrade", "head"],
            cwd=root,
            env=child_env,
            check=True,
        )
        database_kind = "postgresql"
    else:
        database_kind = "sqlite"

    admin_check = """
from dotenv import load_dotenv
load_dotenv(override=False)
from app.config import settings
from app.admin_auth import AdminAuthStore
store = AdminAuthStore(settings.db_path)
with store._connect() as db:
    print('source_admin_exists=yes' if db.execute('SELECT 1 FROM admin_users LIMIT 1').fetchone() else 'source_admin_exists=no')
"""
    admin_result = runner(
        [str(python), "-c", admin_check],
        cwd=root,
        env=child_env,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    before_admin = "source_admin_exists=yes" in (admin_result.stdout or "")

    startup_check = """
from dotenv import load_dotenv
load_dotenv(override=False)
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app, admin_auth
with TestClient(app) as client:
    for path in ('/health/live', '/health/ready', '/admin/login'):
        response = client.get(path)
        if response.status_code != 200:
            raise SystemExit(f'Application check failed for {path}: HTTP {response.status_code}.')
    if not %r:
        login = client.post('/api/admin/auth/login', json={
            'username': settings.admin_bootstrap_username,
            'password': settings.admin_bootstrap_password,
        })
        if login.status_code != 200:
            raise SystemExit('Fresh bootstrap administrator authentication failed.')
""" % before_admin
    runner(
        [str(python), "-c", startup_check],
        cwd=root,
        env=child_env,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    after_admin = _sqlite_admin_count(root, values) > 0 if database_kind == "sqlite" else True
    if not after_admin:
        raise InstallerError("Application startup completed without an administrator account.")
    return database_kind, before_admin


def optional_dependency_status(path: str | None = None) -> dict[str, bool]:
    from shutil import which

    return {name: which(name, path=path) is not None for name in ("node", "npm", "ollama")}


def validate_configuration(root: Path, python: Path, runner: Callable = subprocess.run) -> None:
    root = root.resolve()
    env_path = root / ".env"
    if not env_path.is_file():
        raise InstallerError(".env is missing. Run ./install.sh before ./start.sh.")
    values = _read_env(env_path)
    secret = values.get("CREDENTIAL_ENCRYPTION_SECRET", "")
    if not _is_valid_encryption_secret(secret):
        raise InstallerError("CREDENTIAL_ENCRYPTION_SECRET is missing or invalid. Run ./install.sh to configure it.")
    username = values.get("ADMIN_BOOTSTRAP_USERNAME", "root").strip()
    password = values.get("ADMIN_BOOTSTRAP_PASSWORD", "admin").strip()
    if not _valid_admin_bootstrap(username, password, values.get("APP_ENVIRONMENT", "development")):
        raise InstallerError("Administrator bootstrap configuration is invalid.")
    child_env = os.environ.copy()
    child_env.update(values)
    runner(
        [
            str(python), "-c",
            "from dotenv import load_dotenv; load_dotenv(override=False); "
            "from app.config import settings, validate_production_settings; "
            "validate_production_settings(settings)",
        ],
        cwd=root,
        env=child_env,
        check=True,
    )


def _command() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--root", type=Path, required=True)
    initialize = subparsers.add_parser("initialize")
    initialize.add_argument("--root", type=Path, required=True)
    initialize.add_argument("--python", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    validate.add_argument("--python", type=Path, required=True)
    subparsers.add_parser("optional-status")
    return parser


def main() -> int:
    args = _command().parse_args()
    try:
        if args.command == "prepare":
            secret, admin, existing_admin = prepare_environment(args.root)
            print(f"secret={secret}")
            print(f"admin={admin}")
            print(f"existing_admin={'yes' if existing_admin else 'no'}")
        elif args.command == "initialize":
            database, existing_admin = initialize_application(args.root, args.python)
            print(f"database={database}")
            print(f"existing_admin={'yes' if existing_admin else 'no'}")
        elif args.command == "validate":
            validate_configuration(args.root, args.python)
            print("configuration=valid")
        else:
            for name, present in optional_dependency_status().items():
                print(f"{name}={'present' if present else 'missing'}")
        return 0
    except (InstallerError, OSError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            raise SystemExit(exc.returncode or 1) from exc
        print(f"Installer error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
