"""Supported SQLite-safe backup, verification, and restore commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import zipfile

from .config import settings


FORMAT_VERSION = 1
DATABASE_MEMBER = "database.sqlite"
MANIFEST_MEMBER = "manifest.json"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup(db_path: Path, upload_root: Path, destination: Path) -> dict[str, object]:
    db_path = db_path.resolve()
    upload_root = upload_root.resolve()
    destination = destination.resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="concierge-backup-") as temporary:
        snapshot = Path(temporary) / DATABASE_MEMBER
        with sqlite3.connect(db_path) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError("SQLite backup integrity check failed.")
        members: dict[str, str] = {DATABASE_MEMBER: _digest(snapshot.read_bytes())}
        temporary_archive = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, DATABASE_MEMBER)
                if upload_root.is_dir():
                    for path in sorted(item for item in upload_root.rglob("*") if item.is_file()):
                        member = "uploads/" + path.relative_to(upload_root).as_posix()
                        data = path.read_bytes()
                        members[member] = _digest(data)
                        archive.writestr(member, data)
                manifest = {
                    "format_version": FORMAT_VERSION,
                    "created_at": int(time.time()),
                    "database": DATABASE_MEMBER,
                    "files": members,
                }
                archive.writestr(MANIFEST_MEMBER, json.dumps(manifest, indent=2, sort_keys=True))
            os.replace(temporary_archive, destination)
        finally:
            temporary_archive.unlink(missing_ok=True)
    return {"path": str(destination), "files": len(members), "sha256": _digest(destination.read_bytes())}


def verify_backup(archive_path: Path) -> dict[str, object]:
    archive_path = archive_path.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        if MANIFEST_MEMBER not in names:
            raise RuntimeError("Backup manifest is missing.")
        manifest = json.loads(archive.read(MANIFEST_MEMBER))
        if manifest.get("format_version") != FORMAT_VERSION:
            raise RuntimeError("Unsupported backup format version.")
        files = manifest.get("files")
        if not isinstance(files, dict) or DATABASE_MEMBER not in files:
            raise RuntimeError("Backup manifest is invalid.")
        for member, expected in files.items():
            path = Path(member)
            if path.is_absolute() or ".." in path.parts or member not in names:
                raise RuntimeError("Backup contains an unsafe or missing member.")
            if _digest(archive.read(member)) != expected:
                raise RuntimeError(f"Backup checksum mismatch: {member}")
        database = archive.read(DATABASE_MEMBER)
    with tempfile.TemporaryDirectory(prefix="concierge-verify-") as temporary:
        snapshot = Path(temporary) / DATABASE_MEMBER
        snapshot.write_bytes(database)
        with sqlite3.connect(snapshot) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup database integrity check failed.")
    return {"valid": True, "files": len(files), "created_at": manifest.get("created_at")}


def _safe_restore_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise RuntimeError("Refusing to restore uploads into a broad filesystem root.")
    return resolved


def restore_backup(archive_path: Path, db_path: Path, upload_root: Path, *, replace: bool = False) -> dict[str, object]:
    verification = verify_backup(archive_path)
    db_path = db_path.resolve()
    upload_root = _safe_restore_root(upload_root)
    if (db_path.exists() or upload_root.exists()) and not replace:
        raise FileExistsError("Restore targets already exist; pass replace=True after stopping the application.")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="concierge-restore-", dir=db_path.parent) as temporary:
        stage = Path(temporary)
        staged_db = stage / DATABASE_MEMBER
        staged_uploads = stage / "uploads"
        with zipfile.ZipFile(archive_path.resolve()) as archive:
            staged_db.write_bytes(archive.read(DATABASE_MEMBER))
            for member in archive.namelist():
                if not member.startswith("uploads/") or member.endswith("/"):
                    continue
                relative = Path(member).relative_to("uploads")
                target = (staged_uploads / relative).resolve()
                if staged_uploads.resolve() not in target.parents:
                    raise RuntimeError("Backup contains an unsafe upload path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
        if replace:
            db_path.unlink(missing_ok=True)
            if upload_root.exists():
                shutil.rmtree(upload_root)
        os.replace(staged_db, db_path)
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
        result = create_backup(settings.db_path, settings.upload_root, args.archive)
    elif args.command == "verify":
        result = verify_backup(args.archive)
    else:
        result = restore_backup(args.archive, settings.db_path, settings.upload_root, replace=args.replace)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
