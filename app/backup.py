"""Verified SQLite and PostgreSQL backup, verification, and restore commands."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import zipfile
from urllib.parse import unquote

from sqlalchemy.engine import make_url

from .config import settings


FORMAT_VERSION = 2
SQLITE_MEMBER = "database.sqlite"
POSTGRES_MEMBER = "database.dump"
# Backwards-compatible name used by the existing SQLite archive format.
DATABASE_MEMBER = SQLITE_MEMBER
MANIFEST_MEMBER = "manifest.json"
PG_TOOL_TIMEOUT_SECONDS = 1800
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 32 * 1024 * 1024 * 1024


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _postgres_environment(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Return libpq connection switches and environment without putting secrets in argv."""
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL backup requires a PostgreSQL DATABASE_URL.")
    environment = os.environ.copy()
    if parsed.host:
        environment["PGHOST"] = parsed.host
    if parsed.port:
        environment["PGPORT"] = str(parsed.port)
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    if parsed.database:
        environment["PGDATABASE"] = unquote(parsed.database)
    query = dict(parsed.query)
    for query_name, environment_name in {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "application_name": "PGAPPNAME",
        "connect_timeout": "PGCONNECT_TIMEOUT",
    }.items():
        if query.get(query_name):
            environment[environment_name] = str(query[query_name])
    return ["--no-password"], environment


def _run_postgres_tool(arguments: list[str], database_url: str, *, timeout: int = PG_TOOL_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    switches, environment = _postgres_environment(database_url)
    try:
        result = subprocess.run(
            arguments + switches,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("PostgreSQL backup tools (pg_dump and pg_restore) are required on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("PostgreSQL backup operation exceeded its configured time limit.") from exc
    if result.returncode:
        # pg_dump/pg_restore may echo connection details; never forward their output.
        raise RuntimeError(f"PostgreSQL backup tool failed with exit code {result.returncode}.")
    return result


def _pg_restore_target(database_url: str, dump_file: Path) -> None:
    _run_postgres_tool(
        ["pg_restore", "--list", str(dump_file)],
        database_url,
    )


def _assert_empty_postgres_database(database_url: str) -> None:
    import psycopg
    from psycopg import sql

    try:
        parsed = make_url(database_url)
        psycopg_url = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
        with psycopg.connect(psycopg_url, connect_timeout=5, autocommit=True) as connection:
            tables = connection.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname=current_schema() AND tablename <> 'alembic_version'"
            ).fetchall()
            count = 0
            for (table_name,) in tables:
                has_rows = connection.execute(
                    sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(sql.Identifier(table_name))
                ).fetchone()[0]
                count += int(has_rows)
                if count:
                    break
    except Exception as exc:
        raise RuntimeError("Could not validate the PostgreSQL restore target.") from exc
    if count:
        raise RuntimeError("PostgreSQL restore requires an empty target database; no changes were applied.")


def _pg_dump(database_url: str, destination: Path) -> None:
    switches, environment = _postgres_environment(database_url)
    try:
        result = subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(destination)] + switches,
            check=False,
            capture_output=True,
            text=True,
            timeout=PG_TOOL_TIMEOUT_SECONDS,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("PostgreSQL backup tools (pg_dump and pg_restore) are required on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("PostgreSQL backup operation exceeded its configured time limit.") from exc
    if result.returncode:
        raise RuntimeError(f"PostgreSQL backup tool failed with exit code {result.returncode}.")
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("pg_dump did not create a valid backup file.")


def create_backup(
    db_path: Path,
    upload_root: Path,
    destination: Path,
    *,
    database_url: str = "",
) -> dict[str, object]:
    db_path = db_path.resolve()
    upload_root = upload_root.resolve()
    destination = destination.resolve()
    postgres = bool(database_url and make_url(database_url).get_backend_name() == "postgresql")
    if not postgres and not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="concierge-backup-") as temporary:
        database_member = POSTGRES_MEMBER if postgres else SQLITE_MEMBER
        snapshot = Path(temporary) / database_member
        if postgres:
            _pg_dump(database_url, snapshot)
        else:
            with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise RuntimeError("SQLite backup integrity check failed.")
        members: dict[str, str] = {database_member: _digest_file(snapshot)}
        temporary_archive = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, database_member)
                if upload_root.is_dir():
                    for path in sorted(item for item in upload_root.rglob("*") if item.is_file()):
                        if path.is_symlink() or upload_root not in path.resolve().parents:
                            raise RuntimeError("Backup upload tree contains an unsafe symbolic link.")
                        member = "uploads/" + path.relative_to(upload_root).as_posix()
                        members[member] = _digest_file(path)
                        archive.write(path, member)
                manifest = {
                    "format_version": FORMAT_VERSION,
                    "database_type": "postgresql" if postgres else "sqlite",
                    "created_at": int(time.time()),
                    "database": database_member,
                    "files": members,
                }
                archive.writestr(MANIFEST_MEMBER, json.dumps(manifest, indent=2, sort_keys=True))
            os.replace(temporary_archive, destination)
        finally:
            temporary_archive.unlink(missing_ok=True)
    return {"path": str(destination), "files": len(members), "sha256": _digest_file(destination)}


def verify_backup(archive_path: Path, *, database_url: str = "") -> dict[str, object]:
    archive_path = archive_path.resolve()
    with tempfile.TemporaryDirectory(prefix="concierge-verify-") as temporary:
        with zipfile.ZipFile(archive_path) as archive:
            archive_names = archive.namelist()
            names = set(archive_names)
            if MANIFEST_MEMBER not in names or archive.getinfo(MANIFEST_MEMBER).file_size > 8 * 1024 * 1024:
                raise RuntimeError("Backup manifest is missing or exceeds the size limit.")
            manifest = json.loads(archive.read(MANIFEST_MEMBER))
            version = manifest.get("format_version")
            if version not in {1, FORMAT_VERSION}:
                raise RuntimeError("Unsupported backup format version.")
            files = manifest.get("files")
            database_member = manifest.get("database", DATABASE_MEMBER)
            database_type = manifest.get("database_type", "sqlite")
            if (
                not isinstance(files, dict)
                or database_member not in files
                or database_member not in {SQLITE_MEMBER, POSTGRES_MEMBER}
                or database_type not in {"sqlite", "postgresql"}
                or (database_type == "sqlite") != (database_member == SQLITE_MEMBER)
            ):
                raise RuntimeError("Backup manifest is invalid.")
            if len(names) != len(archive_names) or names != set(files) | {MANIFEST_MEMBER}:
                raise RuntimeError("Backup contains duplicate or unmanifested archive members.")
            total_bytes = 0
            snapshot = Path(temporary) / database_member
            for member, expected in files.items():
                path = Path(member)
                if path.is_absolute() or ".." in path.parts or member not in names:
                    raise RuntimeError("Backup contains an unsafe or missing member.")
                info = archive.getinfo(member)
                total_bytes += info.file_size
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES or total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                    raise RuntimeError("Backup exceeds the configured verification size limit.")
                digest = hashlib.sha256()
                with archive.open(member) as stream:
                    destination = snapshot.open("wb") if member == database_member else None
                    try:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                            if destination is not None:
                                destination.write(block)
                    finally:
                        if destination is not None:
                            destination.close()
                if digest.hexdigest() != expected:
                    raise RuntimeError(f"Backup checksum mismatch: {member}")
        if database_type == "sqlite":
            with closing(sqlite3.connect(snapshot)) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("SQLite backup integrity check failed.")
        else:
            if not database_url:
                raise RuntimeError("DATABASE_URL is required to validate a PostgreSQL backup archive.")
            _pg_restore_target(database_url, snapshot)
    return {
        "valid": True,
        "database_type": database_type,
        "files": len(files),
        "created_at": manifest.get("created_at"),
    }


def _safe_restore_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise RuntimeError("Refusing to restore uploads into a broad filesystem root.")
    return resolved


def restore_backup(
    archive_path: Path,
    db_path: Path,
    upload_root: Path,
    *,
    replace: bool = False,
    database_url: str = "",
) -> dict[str, object]:
    verification = verify_backup(archive_path, database_url=database_url)
    db_path = db_path.resolve()
    upload_root = _safe_restore_root(upload_root)
    postgres = verification["database_type"] == "postgresql"
    if postgres and not database_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL restore.")
    if not postgres and database_url and make_url(database_url).get_backend_name() == "postgresql":
        raise RuntimeError("The archive contains SQLite data but DATABASE_URL selects PostgreSQL.")
    if not postgres and (db_path.exists() or upload_root.exists()) and not replace:
        raise FileExistsError("Restore targets already exist; pass replace=True after stopping the application.")
    if postgres and upload_root.exists() and not replace:
        raise FileExistsError("Restore upload target already exists; pass replace=True after stopping the application.")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="concierge-restore-", dir=upload_root.parent) as temporary:
        stage = Path(temporary)
        manifest_member = DATABASE_MEMBER
        staged_uploads = stage / "uploads"
        with zipfile.ZipFile(archive_path.resolve()) as archive:
            manifest = json.loads(archive.read(MANIFEST_MEMBER))
            manifest_member = manifest.get("database", DATABASE_MEMBER)
            staged_db = stage / manifest_member
            with archive.open(manifest_member) as source, staged_db.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
            for member in archive.namelist():
                if not member.startswith("uploads/") or member.endswith("/"):
                    continue
                relative = Path(member).relative_to("uploads")
                target = (staged_uploads / relative).resolve()
                if staged_uploads.resolve() not in target.parents:
                    raise RuntimeError("Backup contains an unsafe upload path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        if postgres:
            _assert_empty_postgres_database(database_url)
            switches, environment = _postgres_environment(database_url)
            try:
                result = subprocess.run(
                    ["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner", "--no-acl", str(staged_db)] + switches,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=PG_TOOL_TIMEOUT_SECONDS,
                    env=environment,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("PostgreSQL backup tools (pg_dump and pg_restore) are required on this host.") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("PostgreSQL restore exceeded its configured time limit.") from exc
            if result.returncode:
                raise RuntimeError(f"PostgreSQL restore failed with exit code {result.returncode}; the transaction was rolled back.")
        else:
            if replace:
                db_path.unlink(missing_ok=True)
            os.replace(staged_db, db_path)
        if replace and upload_root.exists():
            shutil.rmtree(upload_root)
        if staged_uploads.exists():
            shutil.move(str(staged_uploads), str(upload_root))
        else:
            upload_root.mkdir(parents=True, exist_ok=True)
    return {**verification, "database": str(db_path), "uploads": str(upload_root)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Concierge.AI backup and restore")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("archive", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        result = create_backup(settings.db_path, settings.upload_root, args.archive, database_url=settings.database_url)
    elif args.command == "verify":
        result = verify_backup(args.archive, database_url=settings.database_url)
    else:
        result = restore_backup(
            args.archive,
            settings.db_path,
            settings.upload_root,
            replace=args.replace,
            database_url=settings.database_url,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
