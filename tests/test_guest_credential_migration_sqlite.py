from __future__ import annotations

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


MIGRATION = importlib.import_module(
    "migrations.versions.20260928_0004_unique_guest_credentials"
)


def _create_sessions_table(connection) -> None:
    connection.execute(
        text(
            """CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                property_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                gateway_context TEXT NOT NULL,
                authenticated INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                guest_token_hash TEXT,
                guest_context_hash TEXT,
                guest_token_expires_at BIGINT,
                guest_token_revoked_at BIGINT,
                antlabs_session_id TEXT
            )"""
        )
    )


def _upgrade(connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        MIGRATION.upgrade()


def test_unique_guest_credentials_migration_is_safe_and_repeatable_on_sqlite(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing-guest-sessions.db'}")
    duplicate_hash = "a" * 64
    context_hash = "b" * 64
    with engine.begin() as connection:
        _create_sessions_table(connection)
        for session_id, client_id, token_hash, revoked_at in (
            ("duplicate-one", "guest-one", duplicate_hash, None),
            ("duplicate-two", "guest-two", duplicate_hash, 123),
            ("unique", "guest-three", "c" * 64, None),
            ("no-credential", "guest-four", None, None),
        ):
            connection.execute(
                text(
                    """INSERT INTO sessions
                    (session_id,property_id,client_id,gateway_context,authenticated,created_at,last_seen_at,
                    guest_token_hash,guest_context_hash,guest_token_expires_at,guest_token_revoked_at,antlabs_session_id)
                    VALUES (:session_id,'hotel-a',:client_id,'{}',0,10,20,:token_hash,:context_hash,900,:revoked_at,'gateway-session')"""
                ),
                {
                    "session_id": session_id,
                    "client_id": client_id,
                    "token_hash": token_hash,
                    "context_hash": context_hash if token_hash else None,
                    "revoked_at": revoked_at,
                },
            )

        _upgrade(connection)
        _upgrade(connection)

        rows = connection.execute(
            text(
                "SELECT session_id,property_id,client_id,created_at,last_seen_at,guest_token_hash,"
                "guest_context_hash,guest_token_expires_at,guest_token_revoked_at,antlabs_session_id "
                "FROM sessions ORDER BY session_id"
            )
        ).mappings().all()
        assert len(rows) == 4
        duplicates = [row for row in rows if row["session_id"].startswith("duplicate-")]
        assert all(row["guest_token_hash"] is None for row in duplicates)
        assert all(row["guest_context_hash"] is None for row in duplicates)
        assert all(row["guest_token_expires_at"] is None for row in duplicates)
        assert {row["guest_token_revoked_at"] for row in duplicates} == {0, 123}
        assert all(
            (row["property_id"], row["created_at"], row["last_seen_at"], row["antlabs_session_id"])
            == ("hotel-a", 10, 20, "gateway-session")
            for row in rows
        )
        unique = next(row for row in rows if row["session_id"] == "unique")
        assert unique["guest_token_hash"] == "c" * 64
        assert unique["guest_context_hash"] == context_hash
        assert unique["guest_token_expires_at"] == 900

        indexes = connection.exec_driver_sql("PRAGMA index_list('sessions')").mappings().all()
        unique_index = next(index for index in indexes if index["name"] == "uq_sessions_guest_token_hash")
        assert unique_index["unique"] == 1
        assert unique_index["partial"] == 1
    engine.dispose()


def test_unique_guest_credentials_migration_accepts_a_clean_sqlite_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'clean-guest-sessions.db'}")
    with engine.begin() as connection:
        _create_sessions_table(connection)
        _upgrade(connection)
        _upgrade(connection)
        assert connection.execute(text("SELECT COUNT(*) FROM sessions")).scalar_one() == 0
        indexes = connection.exec_driver_sql("PRAGMA index_list('sessions')").mappings().all()
        assert any(index["name"] == "uq_sessions_guest_token_hash" for index in indexes)
    engine.dispose()
