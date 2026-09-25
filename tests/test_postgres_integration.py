"""Service integration tests enabled by DATABASE_URL in CI/staging."""

import os
import sqlite3
import uuid

import pytest
from sqlalchemy import text

from app.database import (
    CURRENT_SCHEMA_REVISION,
    _postgres_engine,
    configure_database,
    connect_database,
    pool_configuration,
    verify_schema_current,
)


POSTGRES_URL = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="DATABASE_URL is required for PostgreSQL integration tests.")


def _configure() -> None:
    configure_database(
        POSTGRES_URL,
        pool_size=4,
        max_overflow=2,
        pool_timeout=2,
        pool_recycle=60,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )


def test_current_alembic_revision_and_bounded_connection_pool():
    _configure()
    verify_schema_current()
    engine = _postgres_engine()
    assert engine.pool.size() == 4
    assert pool_configuration() == {
        "pool_size": 4,
        "max_overflow": 2,
        "pool_timeout": 2.0,
        "pool_recycle": 60,
        "pool_pre_ping": True,
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == CURRENT_SCHEMA_REVISION
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_legacy_store_adapter_upsert_and_row_mapping(tmp_path):
    _configure()
    from app.properties import PropertyRecord, PropertyStore

    store = PropertyStore(tmp_path / "postgres-path-is-ignored.db")
    property_id = f"pg-adapter-{uuid.uuid4().hex[:10]}"
    record = PropertyRecord(property_id=property_id, hotel_name="Adapter Integration", domain="example.test")
    try:
        store.upsert(record)
        fetched = store.get(property_id)
        assert fetched is not None
        assert fetched.hotel_name == "Adapter Integration"
        assert fetched.domain == "example.test"
        # A second upsert exercises PostgreSQL ON CONFLICT handling.
        fetched.hotel_name = "Adapter Integration Updated"
        store.upsert(fetched)
        assert store.get(property_id).hotel_name == "Adapter Integration Updated"
    finally:
        with connect_database(tmp_path / "postgres-path-is-ignored.db") as db:
            db.execute("DELETE FROM properties WHERE property_id=?", (property_id,))


def test_failed_transaction_rolls_back_all_prior_writes(tmp_path):
    _configure()
    engine = _postgres_engine()
    table = f"adapter_tx_{uuid.uuid4().hex[:18]}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, value TEXT NOT NULL)'))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            with connect_database(tmp_path / "postgres-path-is-ignored.db") as db:
                db.execute(f"INSERT INTO {table}(id,value) VALUES (?,?)", (1, "rollback me"))
                db.execute("INSERT INTO table_that_does_not_exist(id) VALUES (?)", (1,))
        with engine.connect() as connection:
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        assert count == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table}"'))


def test_service_request_query_uses_high_volume_composite_index():
    _configure()
    engine = _postgres_engine()
    property_id = f"explain-{uuid.uuid4().hex[:12]}"
    rows = [
        {
            "request_id": f"explain-{uuid.uuid4().hex}",
            "property_id": property_id if index < 20 else f"other-{index % 1000}",
            "request_type": "housekeeping",
            "description": "Synthetic plan fixture",
            "created_at": index,
            "updated_at": index,
        }
        for index in range(10000)
    ]
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO service_requests "
                    "(request_id,property_id,request_type,description,created_at,updated_at) "
                    "VALUES (:request_id,:property_id,:request_type,:description,:created_at,:updated_at)"
                ),
                rows,
            )
            connection.execute(text("ANALYZE service_requests"))
            plan = connection.execute(
                text(
                    "EXPLAIN SELECT request_id FROM service_requests "
                    "WHERE property_id=:property_id AND status='new' "
                    "ORDER BY created_at DESC LIMIT 10"
                ),
                {"property_id": property_id},
            ).scalars().all()
        assert any("idx_service_requests_property_status_created" in line for line in plan), "\n".join(plan)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM service_requests WHERE property_id=:property_id"), {"property_id": property_id})
