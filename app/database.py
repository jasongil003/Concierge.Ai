"""Database runtime shared by the existing stores.

SQLite remains a lightweight development backend. PostgreSQL connections use a
bounded SQLAlchemy pool and a narrow DB-API compatibility adapter while store
queries are migrated to repository methods in stages.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, CursorResult, Engine
from sqlalchemy.exc import SQLAlchemyError

from . import metrics


CURRENT_SCHEMA_REVISION = "20260926_0002"
_migration_schema_mode: ContextVar[bool] = ContextVar("migration_schema_mode", default=False)
_migration_connection: ContextVar[Connection | None] = ContextVar("migration_connection", default=None)
_engine: Engine | None = None
_configured_url: str | None = None
_engine_options: dict[str, Any] = {}


def configure_database(url: str, **engine_options: Any) -> None:
    """Configure the shared PostgreSQL engine before stores are constructed."""
    global _engine, _configured_url, _engine_options
    normalized = str(url or "").strip()
    if normalized == _configured_url and engine_options == _engine_options:
        return
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _configured_url = normalized
    _engine_options = dict(engine_options)


def database_url_configured() -> bool:
    return bool(_configured_url or __import__("os").getenv("DATABASE_URL", "").strip())


def pool_configuration() -> dict[str, Any]:
    """Return configured finite pool limits for diagnostics and integration checks."""
    return {
        "pool_size": int(_engine_options.get("pool_size", 20)),
        "max_overflow": int(_engine_options.get("max_overflow", 10)),
        "pool_timeout": float(_engine_options.get("pool_timeout", 5)),
        "pool_recycle": int(_engine_options.get("pool_recycle", 1800)),
        "pool_pre_ping": bool(_engine_options.get("pool_pre_ping", True)),
    }


def _postgres_engine() -> Engine:
    global _engine
    import os

    url = _configured_url or os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL connections.")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError("DATABASE_URL must use PostgreSQL with the psycopg 3 driver.")
    if _engine is None:
        options = {
            "pool_size": 20,
            "max_overflow": 10,
            "pool_timeout": 5,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
            "pool_use_lifo": True,
            "connect_args": {"connect_timeout": 5, "options": "-c statement_timeout=5000 -c idle_in_transaction_session_timeout=10000"},
        }
        options.update(_engine_options)
        _engine = create_engine(url, **options)

        def _pool_snapshot() -> None:
            pool = _engine.pool
            metrics.DATABASE_POOL_CAPACITY.set(pool.size() + int(_engine_options.get("max_overflow", 10)))
            metrics.DATABASE_POOL_OVERFLOW.set(max(0, pool.overflow()))

        @event.listens_for(_engine, "checkout")
        def _on_checkout(_dbapi_connection, _connection_record, _connection_proxy):
            metrics.DATABASE_POOL_CHECKED_OUT.inc()
            _pool_snapshot()

        @event.listens_for(_engine, "checkin")
        def _on_checkin(_dbapi_connection, _connection_record):
            metrics.DATABASE_POOL_CHECKED_OUT.dec()
            _pool_snapshot()

    return _engine


class _CompatRow:
    def __init__(self, keys: Sequence[str], values: Sequence[Any]) -> None:
        self._keys = tuple(keys)
        self._values = tuple(values)
        self._mapping = dict(zip(self._keys, self._values))

    def __getitem__(self, key: str | int) -> Any:
        return self._values[key] if isinstance(key, int) else self._mapping[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> tuple[str, ...]:
        return self._keys


class _CompatResult:
    def __init__(self, result: CursorResult[Any] | None, connection: Connection, inserted: bool = False) -> None:
        self._result = result
        self._connection = connection
        self._inserted = inserted

    @property
    def rowcount(self) -> int:
        return int(self._result.rowcount or 0) if self._result is not None else 0

    @property
    def lastrowid(self) -> int | None:
        if not self._inserted:
            return None
        try:
            value = self._connection.execute(text("SELECT LASTVAL()")).scalar_one_or_none()
            return int(value) if value is not None else None
        except SQLAlchemyError as exc:
            raise sqlite3.DatabaseError("The last inserted row ID could not be read.") from exc

    def _row(self, row) -> _CompatRow | None:
        if row is None:
            return None
        keys = self._result.keys() if self._result is not None else ()
        return _CompatRow(keys, row)

    def fetchone(self) -> _CompatRow | None:
        if self._result is None:
            return None
        return self._row(self._result.fetchone())

    def fetchall(self) -> list[_CompatRow]:
        if self._result is None:
            return []
        return [self._row(row) for row in self._result.fetchall()]

    def __iter__(self) -> Iterator[_CompatRow]:
        if self._result is None:
            return iter(())
        return (self._row(row) for row in self._result)


def _qmark_to_named(sql: str, params: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    """Translate SQLite positional markers without rewriting quoted question marks."""
    out: list[str] = []
    in_single = in_double = False
    index = 0
    i = 0
    while i < len(sql):
        char = sql[i]
        if char == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.extend((char, sql[i + 1]))
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            if in_double and i + 1 < len(sql) and sql[i + 1] == '"':
                out.extend((char, sql[i + 1]))
                i += 2
                continue
            in_double = not in_double
        if char == "?" and not in_single and not in_double:
            if index >= len(params):
                raise ValueError("SQL parameter count does not match positional markers.")
            key = f"p{index}"
            out.append(f":{key}")
            index += 1
        else:
            out.append(char)
        i += 1
    if index != len(params):
        raise ValueError("SQL parameter count does not match positional markers.")
    return "".join(out), {f"p{idx}": value for idx, value in enumerate(params)}


def _translate_sql(sql: str, params: Any = None) -> tuple[str, Any]:
    statement = sql.strip()
    if re.match(r"^PRAGMA\s+(foreign_keys|journal_mode|busy_timeout)\b", statement, re.I):
        return "", params
    pragma = re.match(r"^PRAGMA\s+table_info\((\w+)\)", statement, re.I)
    if pragma:
        return (
            "SELECT ordinal_position - 1 AS cid, column_name AS name "
            "FROM information_schema.columns WHERE table_schema=current_schema() "
            "AND table_name=:table_name ORDER BY ordinal_position",
            {"table_name": pragma.group(1)},
        )
    if "sqlite_master" in statement.lower():
        statement = re.sub(
            r"sqlite_master\s+WHERE\s+type\s*=\s*'table'\s+AND\s+name\s*=\s*\?",
            "information_schema.tables WHERE table_schema=current_schema() AND table_name=?",
            statement,
            flags=re.I,
        )
    if re.match(r"^INSERT\s+OR\s+IGNORE\s+INTO\b", statement, re.I):
        statement = re.sub(r"^INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", statement, flags=re.I)
        statement = statement.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    statement = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
        statement,
        flags=re.I,
    )
    if re.match(r"^BEGIN\s+IMMEDIATE\s*$", statement, re.I):
        return "BEGIN", params
    if params is None:
        return statement, None
    if isinstance(params, Mapping):
        return statement, dict(params)
    return _qmark_to_named(statement, tuple(params))


class PostgresCompatConnection:
    """A short lived, pooled transaction with the legacy sqlite row API."""

    def __init__(self, connection: Connection, owns_connection: bool = True) -> None:
        self._connection = connection
        self._owns_connection = owns_connection
        self._closed = False

    def execute(self, sql: str, params: Any = None) -> _CompatResult:
        if re.match(r"^\s*BEGIN\s+IMMEDIATE\s*$", sql, re.I):
            if not self._connection.in_transaction():
                self._connection.begin()
            return _CompatResult(None, self._connection)
        statement, bound = _translate_sql(sql, params)
        if not statement:
            return _CompatResult(None, self._connection)
        if not _migration_schema_mode.get() and re.match(r"^(CREATE|ALTER|DROP)\s+", statement, re.I):
            # Production schema changes are applied by Alembic before the API starts.
            return _CompatResult(None, self._connection)
        try:
            result = self._connection.execute(text(statement), bound) if bound is not None else self._connection.execute(text(statement))
            return _CompatResult(result, self._connection, bool(re.match(r"^INSERT\b", statement, re.I)))
        except SQLAlchemyError as exc:
            metrics.DATABASE_ERRORS.labels("query").inc()
            if "IntegrityError" in exc.__class__.__name__:
                raise sqlite3.IntegrityError("Database constraint rejected the operation.") from exc
            raise sqlite3.DatabaseError("Database operation failed.") from exc

    def executemany(self, sql: str, parameters: Sequence[Sequence[Any]]) -> _CompatResult:
        if not parameters:
            return _CompatResult(None, self._connection)
        statement = sql
        all_params = []
        for values in parameters:
            statement, bound = _translate_sql(sql, values)
            all_params.append(bound)
        if not _migration_schema_mode.get() and re.match(r"^(CREATE|ALTER|DROP)\s+", statement, re.I):
            return _CompatResult(None, self._connection)
        try:
            result = self._connection.execute(text(statement), all_params)
            return _CompatResult(result, self._connection)
        except SQLAlchemyError as exc:
            metrics.DATABASE_ERRORS.labels("batch").inc()
            if "IntegrityError" in exc.__class__.__name__:
                raise sqlite3.IntegrityError("Database constraint rejected the operation.") from exc
            raise sqlite3.DatabaseError("Database operation failed.") from exc

    def executescript(self, sql: str) -> None:
        for statement in _split_statements(sql):
            self.execute(statement)

    def commit(self) -> None:
        if self._owns_connection and self._connection.in_transaction():
            self._connection.commit()

    def rollback(self) -> None:
        if self._owns_connection and self._connection.in_transaction():
            self._connection.rollback()

    def close(self) -> None:
        if not self._closed and self._owns_connection:
            self._connection.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
        return False


def _split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = in_double = False
    i = 0
    while i < len(sql):
        char = sql[i]
        if char == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                current.extend((char, sql[i + 1]))
                i += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            if in_double and i + 1 < len(sql) and sql[i + 1] == '"':
                current.extend((char, sql[i + 1]))
                i += 2
                continue
            in_double = not in_double
        if char == ";" and not in_single and not in_double:
            item = "".join(current).strip()
            if item:
                statements.append(item)
            current = []
        else:
            current.append(char)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def connect_database(path: str | Path, timeout: float = 30) -> Any:
    """Return a SQLite connection or a pooled PostgreSQL transaction wrapper."""
    migration_connection = _migration_connection.get()
    if migration_connection is not None:
        return PostgresCompatConnection(migration_connection, owns_connection=False)
    if database_url_configured():
        try:
            return PostgresCompatConnection(_postgres_engine().connect())
        except SQLAlchemyError as exc:
            metrics.DATABASE_ERRORS.labels("connection_acquire").inc()
            raise sqlite3.DatabaseError("A database connection is temporarily unavailable.") from exc
    connection = sqlite3.connect(path, timeout=timeout)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def migration_schema_mode():
    token = _migration_schema_mode.set(True)
    try:
        yield
    finally:
        _migration_schema_mode.reset(token)


@contextmanager
def bind_migration_connection(connection: Connection):
    """Route legacy store schema declarations into Alembic's one transaction."""
    token = _migration_connection.set(connection)
    try:
        yield
    finally:
        _migration_connection.reset(token)


def verify_schema_current() -> None:
    if not database_url_configured():
        return
    with _postgres_engine().connect() as connection:
        try:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise RuntimeError("PostgreSQL schema is not migrated; run `alembic upgrade head` before starting the API.") from exc
    if revision != CURRENT_SCHEMA_REVISION:
        raise RuntimeError("PostgreSQL schema revision is not current; run `alembic upgrade head` before starting the API.")


def database_ready() -> None:
    if database_url_configured():
        with _postgres_engine().connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    else:
        raise RuntimeError("PostgreSQL is not configured for this deployment.")


def dispose_database() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
