"""Copy an existing SQLite installation into an empty migrated PostgreSQL DB.

The target must already have `alembic upgrade head` applied. The copy is one
PostgreSQL transaction. Primary keys and identity sequence positions are kept;
conflicting target rows cause a rollback.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
from typing import Any

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


IGNORED_SQLITE_TABLES = {"sqlite_sequence", "alembic_version"}
BASELINE_TARGET_TABLES = {"alembic_version"}
VOLATILE_SYSTEM_COLUMNS = {"created_at", "updated_at", "applied_at"}


def _ordered_tables(source: sqlite3.Connection, tables: list[str]) -> list[str]:
    dependencies: dict[str, set[str]] = {table: set() for table in tables}
    for table in tables:
        for row in source.execute(f'PRAGMA foreign_key_list("{table.replace(chr(34), chr(34) * 2)}")'):
            parent = str(row[2])
            if parent in dependencies:
                dependencies[table].add(parent)
    result: list[str] = []
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(table: str) -> None:
        if table in complete:
            return
        if table in visiting:
            raise RuntimeError("SQLite schema contains a cyclic foreign-key dependency; migration stopped safely.")
        visiting.add(table)
        for parent in sorted(dependencies[table]):
            visit(parent)
        visiting.remove(table)
        complete.add(table)
        result.append(table)

    for name in sorted(tables):
        visit(name)
    return result


def migrate_sqlite_to_postgres(source_path: Path, database_url: str, *, batch_size: int = 500) -> dict[str, Any]:
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError("SQLite source database does not exist.")
    if make_url(database_url).get_backend_name() != "postgresql":
        raise ValueError("The destination DATABASE_URL must use PostgreSQL.")
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000.")

    sqlite_uri = f"file:{source_path.as_posix()}?mode=ro"
    copied: dict[str, int] = {}
    with sqlite3.connect(sqlite_uri, uri=True) as source:
        source.row_factory = sqlite3.Row
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("SQLite source failed its integrity check; migration stopped.")
        table_names = [
            str(row[0])
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if str(row[0]) not in IGNORED_SQLITE_TABLES
        ]
        order = _ordered_tables(source, table_names)

        parsed = make_url(database_url)
        psycopg_url = parsed.set(drivername="postgresql").render_as_string(hide_password=False)
        try:
            with psycopg.connect(psycopg_url, connect_timeout=5) as target:
                with target.transaction():
                    target_tables = {
                        row[0]
                        for row in target.execute(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema=current_schema() AND table_type='BASE TABLE'"
                        )
                    }
                    if not set(table_names).issubset(target_tables):
                        missing = sorted(set(table_names) - target_tables)
                        raise RuntimeError("PostgreSQL schema is missing migrated tables: " + ", ".join(missing))

                    for table in table_names:
                        if table in BASELINE_TARGET_TABLES:
                            continue
                        count = target.execute(
                            sql.SQL("SELECT count(*) FROM {} ").format(sql.Identifier(table))
                        ).fetchone()[0]
                        if count:
                            # Baseline role/config seed rows from Alembic may be
                            # kept only when the matching SQLite row is identical.
                            if table not in {"admin_roles", "admin_role_permissions", "admin_schema_migrations"}:
                                raise RuntimeError("PostgreSQL target is not empty; migration stopped before copying data.")

                    for table in order:
                        source_columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34) * 2)}")')]
                        target_columns = {
                            row[0]
                            for row in target.execute(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema=current_schema() AND table_name=%s",
                                (table,),
                            )
                        }
                        if not set(source_columns).issubset(target_columns):
                            missing = sorted(set(source_columns) - target_columns)
                            raise RuntimeError(f"PostgreSQL table {table} is missing source columns: " + ", ".join(missing))
                        info = list(source.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34) * 2)}")'))
                        primary_key = [row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])]
                        select_query = sql.SQL("SELECT {} FROM {}").format(
                            sql.SQL(",").join(map(sql.Identifier, source_columns)),
                            sql.Identifier(table),
                        ).as_string(target)
                        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                            sql.Identifier(table),
                            sql.SQL(",").join(map(sql.Identifier, source_columns)),
                            sql.SQL(",").join(sql.Placeholder() for _ in source_columns),
                        )
                        imported = 0
                        source_cursor = source.execute(select_query)
                        while batch := source_cursor.fetchmany(batch_size):
                            values = [tuple(row[column] for column in source_columns) for row in batch]
                            for value in values:
                                target.execute(insert_query, value)
                            imported += len(values)

                            # ON CONFLICT is allowed only for an identical built-in
                            # seed record. Validate keys and values after each batch.
                            if primary_key and table in {"admin_roles", "admin_role_permissions", "admin_schema_migrations"}:
                                key_positions = [source_columns.index(column) for column in primary_key]
                                for value in values:
                                    where = sql.SQL(" AND ").join(
                                        sql.SQL("{}=%s").format(sql.Identifier(column)) for column in primary_key
                                    )
                                    existing = target.execute(
                                        sql.SQL("SELECT {} FROM {} WHERE ").format(
                                            sql.SQL(",").join(map(sql.Identifier, source_columns)),
                                            sql.Identifier(table),
                                        ) + where,
                                        tuple(value[position] for position in key_positions),
                                    ).fetchone()
                                    if existing is None:
                                        raise RuntimeError(f"Could not verify migrated baseline row in {table}.")
                                    mismatches = [
                                        column for column, source_value, target_value in zip(source_columns, value, existing)
                                        if column not in VOLATILE_SYSTEM_COLUMNS and source_value != target_value
                                    ]
                                    if mismatches:
                                        raise RuntimeError(f"Conflicting baseline row in {table}; no source rows were committed.")
                        copied[table] = imported

                        identity_columns = [
                            row[0]
                            for row in target.execute(
                                "SELECT column_name FROM information_schema.columns "
                                "WHERE table_schema=current_schema() AND table_name=%s AND is_identity='YES'",
                                (table,),
                            )
                        ]
                        for column in identity_columns:
                            maximum = target.execute(
                                sql.SQL("SELECT MAX({}) FROM {}").format(sql.Identifier(column), sql.Identifier(table))
                            ).fetchone()[0]
                            if maximum is not None:
                                target.execute(
                                    "SELECT setval(pg_get_serial_sequence(%s,%s),%s,true)",
                                    (table, column, maximum),
                                )
        except psycopg.Error as exc:
            # Driver diagnostics can contain endpoint and role data; emit no raw DSN.
            raise RuntimeError("PostgreSQL migration failed and the transaction was rolled back.") from exc
    return {"tables": len(copied), "rows": sum(copied.values()), "table_rows": copied}


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy an existing Concierge.AI SQLite database to migrated PostgreSQL.")
    parser.add_argument("sqlite_database", type=Path)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required and must point to the migrated empty PostgreSQL database.")
    print(migrate_sqlite_to_postgres(args.sqlite_database, database_url, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
