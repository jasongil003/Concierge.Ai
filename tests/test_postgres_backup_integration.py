"""End-to-end pg_dump/pg_restore drill into a newly created clean database."""

import os
from pathlib import Path
import uuid

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from app.backup import create_backup, restore_backup, verify_backup
from app.database import configure_database, connect_database
from app.properties import PropertyRecord, PropertyStore


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not os.getenv("PG_DUMP_AVAILABLE"),
    reason="Set DATABASE_URL and PG_DUMP_AVAILABLE to run PostgreSQL backup/restore integration.",
)


def test_postgres_backup_restores_expected_records_to_clean_database(tmp_path: Path):
    parsed = make_url(DATABASE_URL)
    target_database = f"restore_{uuid.uuid4().hex[:12]}"
    maintenance_url = parsed.set(drivername="postgresql").set(database="postgres").render_as_string(hide_password=False)
    target_url = parsed.set(database=target_database).render_as_string(hide_password=False)
    target_psycopg_url = parsed.set(drivername="postgresql").set(database=target_database).render_as_string(hide_password=False)
    property_id = f"backup-drill-{uuid.uuid4().hex[:12]}"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    expected_upload = uploads / "evidence.txt"
    expected_upload.write_text("Restore drill evidence", encoding="utf-8")
    archive = tmp_path / "concierge-postgres-backup.zip"
    configure_database(DATABASE_URL, pool_size=4, max_overflow=2, pool_timeout=2, pool_pre_ping=True)
    PropertyStore(tmp_path / "postgres-ignored.db").upsert(
        PropertyRecord(property_id=property_id, hotel_name="Restore Drill Property", domain="restore.example.test")
    )
    try:
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database)))
        created = create_backup(tmp_path / "unused.sqlite", uploads, archive, database_url=DATABASE_URL)
        assert created["files"] == 2
        assert verify_backup(archive, database_url=DATABASE_URL)["valid"] is True
        restored_uploads = tmp_path / "restored-uploads"
        restore_backup(
            archive,
            tmp_path / "unused.sqlite",
            restored_uploads,
            database_url=target_url,
        )
        with psycopg.connect(target_psycopg_url) as connection:
            row = connection.execute(
                "SELECT hotel_name,domain FROM properties WHERE property_id=%s",
                (property_id,),
            ).fetchone()
        assert row == ("Restore Drill Property", "restore.example.test")
        assert (restored_uploads / "evidence.txt").read_text(encoding="utf-8") == "Restore Drill evidence"
    finally:
        with connect_database(tmp_path / "postgres-ignored.db") as connection:
            connection.execute("DELETE FROM properties WHERE property_id=?", (property_id,))
        with psycopg.connect(maintenance_url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target_database)))
