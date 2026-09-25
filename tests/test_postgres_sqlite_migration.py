"""Integration proof for copying a legacy SQLite store into PostgreSQL."""

import os
import uuid

import pytest

from app.database import configure_database, connect_database
from app.properties import PropertyRecord, PropertyStore
from scripts.migrate_sqlite_to_postgres import migrate_sqlite_to_postgres


POSTGRES_URL = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DATABASE_URL is required for PostgreSQL migration integration tests.")


def test_existing_sqlite_property_data_copies_into_migrated_postgres(tmp_path):
    property_id = f"sqlite-migration-{uuid.uuid4().hex[:12]}"
    source_path = tmp_path / "legacy-concierge.db"
    PropertyStore(source_path).upsert(PropertyRecord(property_id=property_id, hotel_name="Migrated Hotel", domain="migration.example.test"))
    configure_database(POSTGRES_URL, pool_size=4, max_overflow=2, pool_timeout=2, pool_pre_ping=True)
    try:
        result = migrate_sqlite_to_postgres(source_path, POSTGRES_URL, batch_size=2)
        assert result["table_rows"]["properties"] == 1
        migrated = PropertyStore(tmp_path / "postgres-ignored.db").get(property_id)
        assert migrated is not None
        assert migrated.hotel_name == "Migrated Hotel"
        assert migrated.domain == "migration.example.test"
    finally:
        with connect_database(tmp_path / "postgres-ignored.db") as db:
            db.execute("DELETE FROM properties WHERE property_id=?", (property_id,))
