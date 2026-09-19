import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionRecord:
    session_id: str
    property_id: str
    client_id: str
    gateway_context: dict[str, Any]
    authenticated: bool
    created_at: int
    last_seen_at: int


class SessionStore:
    def __init__(self, path: Path, ttl_minutes: int = 30) -> None:
        self.path = path
        self.ttl_seconds = ttl_minutes * 60
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    gateway_context TEXT NOT NULL,
                    authenticated INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                )
                """
            )

    def create(
        self,
        property_id: str,
        client_id: str,
        gateway_context: dict[str, Any] | None = None,
    ) -> SessionRecord:
        now = int(time.time())
        session = SessionRecord(
            session_id=uuid.uuid4().hex,
            property_id=property_id,
            client_id=client_id,
            gateway_context=gateway_context or {},
            authenticated=False,
            created_at=now,
            last_seen_at=now,
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO sessions
                (session_id, property_id, client_id, gateway_context, authenticated, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.property_id,
                    session.client_id,
                    json.dumps(session.gateway_context),
                    0,
                    session.created_at,
                    session.last_seen_at,
                ),
            )
        return session

    def get(self, session_id: str) -> SessionRecord | None:
        self.cleanup_expired()
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            now = int(time.time())
            db.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
                (now, session_id),
            )
        return SessionRecord(
            session_id=row["session_id"],
            property_id=row["property_id"],
            client_id=row["client_id"],
            gateway_context=json.loads(row["gateway_context"]),
            authenticated=bool(row["authenticated"]),
            created_at=row["created_at"],
            last_seen_at=now,
        )

    def mark_authenticated(self, session_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE sessions SET authenticated = 1, last_seen_at = ? WHERE session_id = ?",
                (int(time.time()), session_id),
            )

    def cleanup_expired(self) -> int:
        cutoff = int(time.time()) - self.ttl_seconds
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM sessions WHERE last_seen_at < ?",
                (cutoff,),
            )
            return cursor.rowcount
