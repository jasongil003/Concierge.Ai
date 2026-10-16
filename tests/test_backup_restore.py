import hashlib
import json
import sqlite3
import traceback
from pathlib import Path
import subprocess
import zipfile

import pytest

from app.ai_providers import AIProviderStore
from app import backup
from app.admin_auth import AdminAuthStore
from app.backup import create_backup, restore_backup, verify_backup
from app.hospitality import HospitalityStore
from app.operations import OperationsStore
from app.guardrails import GuestHostnameConflict
from app.properties import PropertyRecord, PropertyStore
from app.system_diagnostics import last_backup


TEST_BACKUP_KEY = "a1" * 32


def test_backup_archive_requires_key_is_not_plaintext_and_authenticates_before_restore(tmp_path: Path):
    source_db = tmp_path / "source.db"
    source_uploads = tmp_path / "uploads"
    source_uploads.mkdir()
    PropertyStore(source_db).upsert(PropertyRecord(property_id="encrypted", hotel_name="Encrypted Backup"))
    (source_uploads / "private.txt").write_text("synthetic upload payload", encoding="utf-8")
    archive = tmp_path / "backup.zip.enc"

    with pytest.raises(RuntimeError, match="CONCIERGE_BACKUP_ENCRYPTION_KEY"):
        create_backup(source_db, source_uploads, archive)
    created = create_backup(source_db, source_uploads, archive, backup_key=TEST_BACKUP_KEY)
    encrypted_bytes = archive.read_bytes()
    assert created["encrypted"] is True
    assert encrypted_bytes.startswith(backup.ENCRYPTED_BACKUP_MAGIC)
    assert not zipfile.is_zipfile(archive)
    assert b"synthetic upload payload" not in encrypted_bytes
    with pytest.raises(RuntimeError, match="CONCIERGE_BACKUP_ENCRYPTION_KEY"):
        verify_backup(archive)
    with pytest.raises(RuntimeError, match="authentication failed"):
        verify_backup(archive, backup_key="ff" * 32)

    target_db = tmp_path / "restore" / "restored.db"
    target_uploads = tmp_path / "restore" / "uploads"
    tampered = tmp_path / "tampered.zip.enc"
    corrupted = bytearray(encrypted_bytes)
    corrupted[-1] ^= 1
    tampered.write_bytes(corrupted)
    with pytest.raises(RuntimeError, match="authentication failed"):
        restore_backup(tampered, target_db, target_uploads, backup_key=TEST_BACKUP_KEY)
    assert not target_db.exists()
    assert not target_uploads.exists()

    restored = restore_backup(archive, target_db, target_uploads, backup_key=TEST_BACKUP_KEY)
    assert restored["encrypted"] is True
    assert PropertyStore(target_db).get("encrypted").hotel_name == "Encrypted Backup"
    assert (target_uploads / "private.txt").read_text(encoding="utf-8") == "synthetic upload payload"


def test_legacy_plaintext_backup_requires_explicit_operator_option(tmp_path: Path):
    source_db = tmp_path / "source.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    PropertyStore(source_db).upsert(PropertyRecord(property_id="legacy", hotel_name="Legacy Backup"))
    encrypted = tmp_path / "encrypted.zip.enc"
    create_backup(source_db, uploads, encrypted, backup_key=TEST_BACKUP_KEY)
    with backup._plaintext_backup_archive(
        encrypted, backup_key=TEST_BACKUP_KEY, allow_legacy_unencrypted=False
    ) as (plain_archive, _encrypted):
        legacy = tmp_path / "legacy.zip"
        legacy.write_bytes(plain_archive.read_bytes())

    with pytest.raises(RuntimeError, match="Plaintext legacy backups are disabled"):
        verify_backup(legacy)
    assert verify_backup(legacy, allow_legacy_unencrypted=True)["encrypted"] is False


def test_backup_diagnostics_recognize_encrypted_archive_without_reading_plaintext(tmp_path: Path):
    source_db = tmp_path / "source.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    PropertyStore(source_db).upsert(PropertyRecord(property_id="diagnostics", hotel_name="Synthetic"))
    create_backup(source_db, uploads, tmp_path / "backups" / "concierge-test.zip.enc", backup_key=TEST_BACKUP_KEY)

    result = last_backup(tmp_path / "backups")

    assert result["status"] == "encrypted"
    assert result["version"] == "unknown"


def test_backup_verify_and_actual_restore(tmp_path: Path):
    db_path = tmp_path / "live" / "concierge.db"
    uplo