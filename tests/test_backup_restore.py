import sqlite3
from pathlib import Path

from app.ai_providers import AIProviderStore
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
