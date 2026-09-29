"""Service integration tests enabled by DATABASE_URL in CI/staging."""

import os
import sqlite3
import subprocess
import sys
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database import (
    CURRENT_SCHEMA_REVISION,
    _postgres_engine,
    configure_database,
    connect_database,
    pool_configuration,
    table_columns,
    table_exists,
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


def test_postgres_schema_inspection_bootstrap_and_assignment_validation(tmp_path):
    _configure()
    from app.admin_auth import AdminAuthStore
    from app.hospitality import HospitalityStore
    from app.properties import PropertyRecord, PropertyStore

    property_id = f"pg-auth-{uuid.uuid4().hex[:12]}"
    property_store = PropertyStore(tmp_path / "postgres-path-is-ignored.db")
    hospitality = HospitalityStore(tmp_path / "postgres-path-is-ignored.db")
    auth = AdminAuthStore(tmp_path / "postgres-path-is-ignored.db")
    property_store.upsert(PropertyRecord(property_id=property_id, hotel_name="Postgres Auth Fixture", domain=f"{property_id}.example.test"))
    department = hospitality.upsert_department(property_id, {"name": "Integration Department"})
    restaurant = hospitality.create_restaurant(property_id, {"name": "Integration Restaurant"})
    username = f"pg-bootstrap-{uuid.uuid4().hex[:10]}"
    password = f"Postgres-Test-{uuid.uuid4().hex[:12]}A!"

    try:
        auth.ensure_bootstrap_admin(username, password, "Postgres Bootstrap Test")
        _, principal = auth.login(username, password, "127.0.0.1", "postgres integration")
        assert principal.role_slug == "super-admin"

        with connect_database(tmp_path / "postgres-path-is-ignored.db") as db:
            assert table_exists(db, "departments")
            assert table_exists(db, "restaurants")
            assert table_columns(db, "departments") >= {"department_id", "property_id", "name"}

        assert auth._department_belongs(property_id, department["department_id"])
        assert not auth._department_belongs("another-property", department["department_id"])
        manager = auth.create_user(
            {
                "username": f"pg-restaurant-{uuid.uuid4().hex[:10]}",
                "display_name": "Postgres Restaurant Manager",
                "password": "Restaurant-Manager-123!",
                "role_id": "role-restaurant-manager",
                "property_id": property_id,
                "restaurant_ids": [restaurant["restaurant_id"]],
            },
            principal,
        )
        assert manager["restaurant_ids"] == [restaurant["restaurant_id"]]
        with pytest.raises(PermissionError, match="user's property"):
            auth.create_user(
                {
                    "username": f"pg-invalid-assignment-{uuid.uuid4().hex[:10]}",
                    "display_name": "Invalid Restaurant Assignment",
                    "password": "Restaurant-Manager-123!",
                    "role_id": "role-restaurant-manager",
                    "property_id": property_id,
                    "restaurant_ids": [f"restaurant-from-another-property-{uuid.uuid4().hex[:8]}"],
                },
                principal,
            )
    finally:
        with connect_database(tmp_path / "postgres-path-is-ignored.db") as db:
            db.execute("DELETE FROM admin_users WHERE username LIKE ?", (f"pg-restaurant-%",))
            db.execute("DELETE FROM admin_users WHERE username=?", (username,))
            db.execute("DELETE FROM restaurants WHERE property_id=?", (property_id,))
            db.execute("DELETE FROM departments WHERE property_id=?", (property_id,))
            db.execute("DELETE FROM properties WHERE property_id=?", (property_id,))


def test_fresh_postgres_schema_starts_application(tmp_path):
    _configure()
    verify_schema_current()
    completed = subprocess.run(
        [sys.executable, "-c", "from app.main import app; assert app is not None"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_guest_credential_migration_upgrades_schema_at_0003_with_duplicate_rows():
    _configure()
    engine = _postgres_engine()
    schema = f"guest_migration_{uuid.uuid4().hex[:12]}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection = engine.connect()
    try:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        config = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "20260928_0003")
        connection.execute(text("DROP INDEX IF EXISTS uq_sessions_guest_token_hash"))
        connection.commit()
        now = 1_798_560_000
        duplicate_hash = "a" * 64
        with connection.begin():
            for suffix in ("one", "two"):
                connection.execute(
                    text(
                        "INSERT INTO sessions(session_id,property_id,client_id,gateway_context,authenticated,created_at,last_seen_at,"
                        "guest_token_hash,guest_context_hash,guest_token_expires_at) "
                        "VALUES (:session_id,:property_id,:client_id,'{}',0,:created_at,:last_seen_at,:token,:context,:expires)"
                    ),
                    {
                        "session_id": f"session-{suffix}",
                        "property_id": "migration-property",
                        "client_id": f"client-{suffix}",
                        "created_at": now,
                        "last_seen_at": now,
                        "token": duplicate_hash,
                        "context": "b" * 64,
                        "expires": now + 300,
                    },
                )
        command.upgrade(config, "20260928_0004")
        rows = connection.execute(
            text("SELECT guest_token_hash,guest_context_hash,guest_token_expires_at,guest_token_revoked_at FROM sessions")
        ).mappings().all()
        assert len(rows) == 2
        assert all(row["guest_token_hash"] is None for row in rows)
        assert all(row["guest_context_hash"] is None for row in rows)
        assert all(row["guest_token_expires_at"] is None for row in rows)
        assert all(row["guest_token_revoked_at"] == 0 for row in rows)
    finally:
        connection.execute(text("SET search_path TO public"))
        connection.commit()
        connection.close()
        with engine.begin() as cleanup:
            cleanup.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


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


def test_postgres_guest_zones_knowledge_conflicts_and_service_request_replay(tmp_path):
    """Exercise legacy store queries that must remain portable to PostgreSQL."""
    _configure()
    from app.hospitality import HospitalityStore
    from app.knowledge_management import KnowledgeStore
    from app.properties import PropertyRecord, PropertyStore
    from app.zones import ZoneStore

    property_id = f"pg-guest-path-{uuid.uuid4().hex[:12]}"
    db_path = tmp_path / "postgres-path-is-ignored.db"
    properties = PropertyStore(db_path)
    hospitality = HospitalityStore(db_path)
    zones = ZoneStore(db_path)
    knowledge = KnowledgeStore(db_path, tmp_path / "uploads")
    properties.upsert(PropertyRecord(property_id=property_id, hotel_name="Postgres Guest Path"))
    client_request_id = f"guest-{uuid.uuid4().hex}"
    payload = {
        "stay_id": f"stay-{uuid.uuid4().hex}",
        "description": "Please bring extra towels.",
        "client_request_id": client_request_id,
    }

    try:
        assert zones.overview(property_id, guest=True)["maps"] == []
        assert knowledge.conflicts(property_id) == []
        created = hospitality.create_service_request(property_id, payload)
        replayed = hospitality.create_service_request(property_id, payload)
        assert replayed["request_id"] == created["request_id"]
        assert replayed["idempotent_replay"] is True
    finally:
        with connect_database(db_path) as db:
            db.execute("DELETE FROM service_requests WHERE property_id=?", (property_id,))
            db.execute("DELETE FROM properties WHERE property_id=?", (property_id,))
