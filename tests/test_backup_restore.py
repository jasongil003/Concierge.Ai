import sqlite3
from pathlib import Path
import subprocess
import zipfile

from app.ai_providers import AIProviderStore
from app import backup
from app.backup import create_backup, restore_backup, verify_backup
from app.hospitality import HospitalityStore
from app.properties import PropertyRecord, PropertyStore


def test_backup_verify_and_actual_restore(tmp_path: Path):
    db_path = tmp_path / "live" / "concierge.db"
    upload_root = tmp_path / "live" / "uploads"
    archive = tmp_path / "backups" / "hotel-backup.zip"
    property_store = PropertyStore(db_path)
    property_store.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    hospitality = HospitalityStore(db_path)
    service = hospitality.upsert_service("hotel-a", {"name": "Extra towels"})
    hospitality.create_service_request("hotel-a", {"service_id": service["service_id"], "description": "Two towels"})
    providers = AIProviderStore(db_path)
    providers.save_connection("hotel-a", "openai", {"enabled": True})
    providers.save_credential("hotel-a", "openai", "api_key", "encrypted-after-backup")
    upload = upload_root / "hotel-a" / "knowledge" / "welcome.txt"
    upload.parent.mkdir(parents=True)
    upload.write_text("Hotel A private knowledge", encoding="utf-8")

    created = create_backup(db_path, upload_root, archive)
    assert created["files"] == 2
    assert verify_backup(archive)["valid"] is True

    db_path.unlink()
    upload.unlink()
    restore_backup(archive, db_path, upload_root, replace=True)

    assert PropertyStore(db_path).get("hotel-a").hotel_name == "Hotel A"
    assert HospitalityStore(db_path).overview("hotel-a")["service_requests"][0]["description"] == "Two towels"
    assert AIProviderStore(db_path).credentials_for("hotel-a", "openai")["api_key"] == "encrypted-after-backup"
    assert upload.read_text(encoding="utf-8") == "Hotel A private knowledge"
    with sqlite3.connect(db_path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_postgres_backup_archive_uses_secret_free_argv_and_restores_to_empty_target(tmp_path, monkeypatch):
    database_url = "postgresql+psycopg://backup-user:unit%40test@127.0.0.1:5432/concierge?sslmode=disable"
    upload_root = tmp_path / "source-uploads"
    upload_root.mkdir()
    (upload_root / "source.txt").write_text("verified source", encoding="utf-8")
    archive = tmp_path / "postgres-backup.zip"
    argv_seen = []
    env_seen = []

    def fake_run(argv, *, env, **_kwargs):
        argv_seen.append(list(argv))
        env_seen.append(env)
        if argv[0] == "pg_dump":
            dump_path = Path(argv[argv.index("--file") + 1])
            dump_path.write_bytes(b"custom-format-dump-test")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    monkeypatch.setattr(backup, "_assert_empty_postgres_database", lambda _url: None)
    made = create_backup(tmp_path / "unused.sqlite", upload_root, archive, database_url=database_url)
    assert made["files"] == 2
    verified = verify_backup(archive, database_url=database_url)
    assert verified["valid"] is True
    assert verified["database_type"] == "postgresql"
    with zipfile.ZipFile(archive) as saved:
        manifest = __import__("json").loads(saved.read("manifest.json"))
        assert manifest["database"] == "database.dump"
        assert saved.read("database.dump") == b"custom-format-dump-test"

    restored_uploads = tmp_path / "restored-uploads"
    restore_backup(
        archive,
        tmp_path / "unused.sqlite",
        restored_uploads,
        database_url=database_url,
    )
    assert (restored_uploads / "source.txt").read_text(encoding="utf-8") == "verified source"
    assert len([argv for argv in argv_seen if argv[0] == "pg_restore"]) == 2
    assert all("unit@test" not in " ".join(argv) for argv in argv_seen)
    assert all(env["PGPASSWORD"] == "unit@test" for env in env_seen)


def test_postgres_restore_refuses_a_nonempty_target_without_applying_dump(tmp_path, monkeypatch):
    database_url = "postgresql+psycopg://backup-user:unit-test@127.0.0.1:5432/concierge"
    upload_root = tmp_path / "source-uploads"
    upload_root.mkdir()
    archive = tmp_path / "postgres-backup.zip"

    def fake_run(argv, **_kwargs):
        if argv[0] == "pg_dump":
            Path(argv[argv.index("--file") + 1]).write_bytes(b"custom-format-dump-test")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    made = create_backup(tmp_path / "unused.sqlite", upload_root, archive, database_url=database_url)
    assert made["files"] == 1
    monkeypatch.setattr(
        backup,
        "_assert_empty_postgres_database",
        lambda _url: (_ for _ in ()).throw(RuntimeError("PostgreSQL restore requires an empty target database; no changes were applied.")),
    )
    try:
        restore_backup(
            archive,
            tmp_path / "unused.sqlite",
            tmp_path / "restored-uploads",
            database_url=database_url,
        )
    except RuntimeError as exc:
        assert "empty target database" in str(exc)
    else:
        raise AssertionError("PostgreSQL restore accepted a nonempty target database.")
