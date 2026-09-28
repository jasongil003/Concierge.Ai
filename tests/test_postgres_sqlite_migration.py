"""Integration proof for copying a legacy SQLite store into PostgreSQL."""

import os
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.database import configure_database, connect_database
from app.properties import PropertyRecord, PropertyStore
from scripts.migrate_sqlite_to_postgres import migrate_sqlite_to_postgres


POSTGRES_URL = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DATABASE_URL is required for PostgreSQL migration integration tests.")


def test_existing_sqlite_property_data_copies_into_migrated_postgres(tmp_path, monkeypatch):
    property_id = f"sqlite-migration-{uuid.uuid4().hex[:12]}"
    schema = f"sqlite_migration_{uuid.uuid4().hex[:12]}"
    source_path = tmp_path / "legacy-concierge.db"
    # The integration job exports DATABASE_URL for the entire pytest process.
    # Explicitly select SQLite while constructing the source database so the
    # fixture does not silently write into PostgreSQL instead.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    configure_database("")
    PropertyStore(source_path).upsert(PropertyRecord(property_id=property_id, hotel_name="Migrated Hotel", domain="migration.example.test"))
    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    postgres_url = make_url(POSTGRES_URL)
    if postgres_url.drivername in {"postgres", "postgresql"}:
        postgres_url = postgres_url.set(drivername="postgresql+psycopg")
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        migration_connection = engine.connect()
        try:
            migration_connection.execute(text(f'SET search_path TO "{schema}"'))
            migration_connection.commit()
            config = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
            config.attributes["connection"] = migration_connection
            command.upgrade(config, "head")
        finally:
            migration_connection.close()

        target_url = POSTGRES_URL
        monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema}")
        configure_database(
            target_url,
            pool_size=4,
            max_overflow=2,
            pool_timeout=2,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3, "options": f"-c search_path={schema} -c statement_timeout=3000"},
        )
        result = migrate_sqlite_to_postgres(source_path, target_url, batch_size=2)
        assert result["table_rows"]["properties"] == 1
        migrated = PropertyStore(tmp_path / "postgres-ignored.db").get(property_id)
        assert migrated is not None
        assert migrated.hotel_name == "Migrated Hotel"
        assert migrated.domain == "migration.example.test"
    finally:
        configure_database(POSTGRES_URL)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
