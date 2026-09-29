import sqlite3
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


def test_backup_verify_and_actual_restore(tmp_path: Path):
    db_path = tmp_path / "live" / "concierge.db"
    upload_root = tmp_path / "live" / "uploads"
    archive = tmp_path / "backups" / "hotel-backup.zip"
    property_store = PropertyStore(db_path)
    property_store.upsert(
        PropertyRecord(
            property_id="hotel-a",
            hotel_name="Hotel A",
            domain="hotel-a.example.test",
            guardrails={"guest_access_hosts": ["guest.hotel-a.example.test"], "allowed_cidrs": ["10.20.0.0/16"]},
            app_settings={"deployment": {"guest_access_enabled": True, "public_base_url": "https://hotel-a.example.test"}},
            ai_settings={"default_provider": "local", "routing_mode": "fixed", "local_only": True},
            design_published={"branding": {"hotelName": "Hotel A"}, "theme": {"accent": "#123456"}},
        )
    )
    hospitality = HospitalityStore(db_path)
    service = hospitality.upsert_service("hotel-a", {"name": "Extra towels"})
    hospitality.create_service_request("hotel-a", {"service_id": service["service_id"], "description": "Two towels"})
    restaurant = hospitality.create_restaurant("hotel-a", {"name": "Backup Dining"})
    menu = hospitality.create_menu("hotel-a", restaurant["restaurant_id"], {"name": "Backup Dinner", "meal_period": "dinner"})
    item = hospitality.create_menu_item("hotel-a", menu["menu_id"], {"name": "Backup Pasta", "price": "PHP 500"})
    promotion = hospitality.create_promotion("hotel-a", restaurant["restaurant_id"], {"title": "Backup Special", "description": "Test promotion"})
    auth = AdminAuthStore(db_path)
    auth.ensure_bootstrap_admin("root", "BackupRootPassword123!")
    staff = auth.create_user(
        {
            "username": "backup.staff",
            "display_name": "Backup Staff",
            "password": "BackupStaffPassword123!",
            "property_id": "hotel-a",
            "role_id": "role-restaurant-staff",
            "restaurant_ids": [restaurant["restaurant_id"]],
        },
        actor=None,
    )
    operations = OperationsStore(db_path)
    operations.save_network_access_settings(
        {"management_access_enabled": True, "management_allowed_cidrs": ["10.10.0.0/16"], "management_trusted_proxy_ranges": []}
    )
    providers = AIProviderStore(db_path)
    providers.save_connection("hotel-a", "openai", {"enabled": True})
    providers.save_credential("hotel-a", "openai", "api_key", "encrypted-after-backup")
    upload = upload_root / "hotel-a" / "knowledge" / "welcome.txt"
    upload.parent.mkdir(parents=True)
    upload.write_text("Hotel A private knowledge", encoding="utf-8")

    created = create_backup(db_path, upload_root, archive)
    assert created["files"] == 2
    assert verify_backup(archive)["valid"] is True

    changed = property_store.get("hotel-a")
    changed.hotel_name = "Changed After Backup"
    property_store.upsert(changed)
    db_path.unlink()
    upload.unlink()
    restore_backup(archive, db_path, upload_root, replace=True)

    restored_properties = PropertyStore(db_path)
    restored_property = restored_properties.get("hotel-a")
    assert restored_property.hotel_name == "Hotel A"
    assert restored_property.domain == "hotel-a.example.test"
    assert restored_property.guardrails["guest_access_hosts"] == ["guest.hotel-a.example.test"]
    assert restored_property.app_settings["deployment"]["public_base_url"] == "https://hotel-a.example.test"
    assert restored_property.design_published["theme"]["accent"] == "#123456"
    overview = HospitalityStore(db_path).overview("hotel-a")
    assert overview["service_requests"][0]["description"] == "Two towels"
    assert any(item["name"] == "Backup Dining" for item in overview["restaurants"])
    restored_hospitality = HospitalityStore(db_path)
    restored_menu = restored_hospitality.restaurant_menus("hotel-a", restaurant["restaurant_id"])[0]
    assert restored_menu["menu_id"] == menu["menu_id"]
    assert restored_menu["items"][0]["item_id"] == item["item_id"]
    assert restored_hospitality.restaurant_promotions("hotel-a", restaurant["restaurant_id"])[0]["promotion_id"] == promotion["promotion_id"]
    restored_auth = AdminAuthStore(db_path)
    restored_staff = restored_auth.get_user(staff["id"])
    assert restored_staff["role_slug"] == "restaurant-staff"
    assert restored_staff["restaurant_ids"] == [restaurant["restaurant_id"]]
    assert OperationsStore(db_path).get_network_access_settings({})["management_allowed_cidrs"] == ["10.10.0.0/16"]
    with pytest.raises(GuestHostnameConflict):
        restored_properties.upsert(PropertyRecord(property_id="collision", hotel_name="Collision", domain="GUEST.HOTEL-A.EXAMPLE.TEST."))
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
    restore_commands = [argv for argv in argv_seen if argv[0] == "pg_restore"]
    assert len(restore_commands) == 3
    assert sum("--list" in argv for argv in restore_commands) == 2
    assert sum("--exit-on-error" in argv for argv in restore_commands) == 1
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
