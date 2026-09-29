from __future__ import annotations

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


MIGRATION = importlib.import_module(
    "migrations.versions.20260929_0005_timestamped_knowledge_conflicts_and_floor_maps"
)


def _upgrade(connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        MIGRATION.upgrade()


def test_ordering_migration_backfills_existing_sqlite_rows_and_repeats_safely(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'existing-ordering.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE km_items (item_id TEXT PRIMARY KEY, property_id TEXT NOT NULL, created_at INTEGER NOT NULL)")
        )
        connection.execute(
            text(
                """CREATE TABLE km_conflicts (
                    conflict_id TEXT PRIMARY KEY, property_id TEXT NOT NULL,
                    item_a TEXT NOT NULL, item_b TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open', note TEXT NOT NULL DEFAULT '',
                    resolved_by TEXT, resolved_at INTEGER)"""
            )
        )
        connection.execute(
            text(
                """CREATE TABLE floor_maps (
                    map_id TEXT PRIMARY KEY, property_id TEXT NOT NULL, floor_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL, content_type TEXT NOT NULL,
                    storage_path TEXT NOT NULL, width REAL, height REAL, created_at INTEGER NOT NULL)"""
            )
        )
        connection.execute(
            text("INSERT INTO km_items(item_id,property_id,created_at) VALUES ('old-item','hotel-a',100),('new-item','hotel-a',200)")
        )
        connection.execute(
            text(
                "INSERT INTO km_conflicts(conflict_id,property_id,item_a,item_b) "
                "VALUES ('legacy-conflict','hotel-a','old-item','new-item')"
            )
        )
        connection.execute(
            text(
                """INSERT INTO floor_maps
                (map_id,property_id,floor_id,original_filename,content_type,storage_path,width,height,created_at)
                VALUES ('map-z','hotel-a','floor-a','old.png','image/png','/old.png',1,1,300),
                       ('map-a','hotel-a','floor-a','new.png','image/png','/new.png',1,1,300)"""
            )
        )

        _upgrade(connection)
        _upgrade(connection)

        conflict = connection.execute(
            text("SELECT created_at,created_at_us FROM km_conflicts WHERE conflict_id='legacy-conflict'")
        ).one()
        assert tuple(conflict) == (200, 200_000_000)
        maps = connection.execute(
            text("SELECT map_id,created_at_us FROM floor_maps ORDER BY created_at_us DESC,map_id ASC")
        ).all()
        assert [tuple(row) for row in maps] == [("map-a", 300_000_000), ("map-z", 300_000_000)]
        conflict_columns = {row["name"] for row in connection.exec_driver_sql("PRAGMA table_info(km_conflicts)").mappings()}
        map_columns = {row["name"] for row in connection.exec_driver_sql("PRAGMA table_info(floor_maps)").mappings()}
        assert {"created_at", "created_at_us"} <= conflict_columns
        assert "created_at_us" in map_columns
        assert connection.execute(text("SELECT COUNT(*) FROM km_conflicts")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM floor_maps")).scalar_one() == 2
    engine.dispose()


def test_ordering_migration_accepts_a_fresh_sqlite_store_schema(tmp_path):
    from app.knowledge_management import KnowledgeStore
    from app.zones import ZoneStore

    database = tmp_path / "fresh-ordering.db"
    KnowledgeStore(database, tmp_path / "uploads")
    ZoneStore(database)
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        _upgrade(connection)
        _upgrade(connection)
        conflict_columns = {row["name"] for row in connection.exec_driver_sql("PRAGMA table_info(km_conflicts)").mappings()}
        map_columns = {row["name"] for row in connection.exec_driver_sql("PRAGMA table_info(floor_maps)").mappings()}
        assert {"created_at", "created_at_us"} <= conflict_columns
        assert "created_at_us" in map_columns
        assert connection.execute(text("SELECT COUNT(*) FROM km_conflicts")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM floor_maps")).scalar_one() == 0
    engine.dispose()


def test_sqlite_store_startup_adds_ordering_columns_to_existing_tables(tmp_path):
    import sqlite3

    from app.knowledge_management import KnowledgeStore
    from app.zones import ZoneStore

    database = tmp_path / "store-startup-ordering.db"
    KnowledgeStore(database, tmp_path / "uploads")
    ZoneStore(database)
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE km_conflicts DROP COLUMN created_at_us")
        connection.execute("ALTER TABLE km_conflicts DROP COLUMN created_at")
        connection.execute("ALTER TABLE floor_maps DROP COLUMN created_at_us")
        connection.execute(
            "INSERT INTO km_items (item_id,property_id,category,title,content,created_by,modified_by,created_at,updated_at) "
            "VALUES ('old-a','hotel-a','Other','A','a','admin','admin',100,100),"
            "('old-b','hotel-a','Other','B','b','admin','admin',200,200)"
        )
        connection.execute(
            "INSERT INTO km_conflicts (conflict_id,property_id,item_a,item_b) "
            "VALUES ('legacy','hotel-a','old-a','old-b')"
        )
        connection.execute(
            "INSERT INTO floor_maps (map_id,property_id,floor_id,original_filename,content_type,storage_path,created_at) "
            "VALUES ('map-old','hotel-a','floor-a','old.png','image/png','/old.png',300)"
        )

    KnowledgeStore(database, tmp_path / "uploads")
    ZoneStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT created_at,created_at_us FROM km_conflicts WHERE conflict_id='legacy'").fetchone() == (200, 200_000_000)
        assert connection.execute("SELECT created_at_us FROM floor_maps WHERE map_id='map-old'").fetchone() == (300_000_000,)
