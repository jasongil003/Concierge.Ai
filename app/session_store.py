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
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS authentication_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    latency_ms INTEGER,
                    error TEXT,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_state (
                    session_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    human_takeover INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                );
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

    def record_authentication(self, session_id: str, property_id: str, success: bool) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO authentication_attempts VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex, property_id, session_id, 1 if success else 0, int(time.time())),
            )

    def record_message(
        self,
        session_id: str,
        property_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO conversation_messages VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, property_id, session_id, role, content[:8000], provider, model, latency_ms, error, int(time.time())),
            )

    def metrics(self, property_id: str) -> dict[str, Any]:
        now = int(time.time())
        day_start = now - (now % 86400)
        active_cutoff = now - self.ttl_seconds
        with self._connect() as db:
            active_guests = db.execute(
                "SELECT COUNT(DISTINCT client_id) FROM sessions WHERE property_id=? AND last_seen_at>=?",
                (property_id, active_cutoff),
            ).fetchone()[0]
            ai_requests = db.execute(
                "SELECT COUNT(*) FROM conversation_messages WHERE property_id=? AND role='assistant' AND provider IS NOT NULL AND created_at>=?",
                (property_id, day_start),
            ).fetchone()[0]
            auth = db.execute(
                "SELECT COUNT(*) AS total, SUM(success) AS successes FROM authentication_attempts WHERE property_id=? AND created_at>=?",
                (property_id, day_start),
            ).fetchone()
        total = int(auth["total"] or 0)
        successes = int(auth["successes"] or 0)
        return {
            "active_guests": active_guests,
            "ai_requests_today": ai_requests,
            "auth_attempts_today": total,
            "auth_success_rate": round(successes * 100 / total, 1) if total else None,
        }

    def conversations(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT s.session_id,s.client_id,s.authenticated,s.created_at,s.last_seen_at,
                COALESCE(cs.status,'open') AS status,COALESCE(cs.human_takeover,0) AS human_takeover,
                COUNT(m.message_id) AS message_count,MAX(m.created_at) AS last_message_at
                FROM sessions s LEFT JOIN conversation_messages m ON m.session_id=s.session_id
                LEFT JOIN conversation_state cs ON cs.session_id=s.session_id
                WHERE s.property_id=? GROUP BY s.session_id ORDER BY COALESCE(MAX(m.created_at),s.created_at) DESC""",
                (property_id,),
            ).fetchall()
            result = []
            for row in rows:
                messages = db.execute(
                    "SELECT message_id,role,content,provider,model,latency_ms,error,created_at FROM conversation_messages WHERE property_id=? AND session_id=? ORDER BY created_at,message_id",
                    (property_id, row["session_id"]),
                ).fetchall()
                result.append({**dict(row), "authenticated": bool(row["authenticated"]), "human_takeover": bool(row["human_takeover"]), "messages": [dict(item) for item in messages]})
        return result

    def set_conversation_state(self, session_id: str, property_id: str, status: str, human_takeover: bool) -> dict[str, Any]:
        if status not in {"open", "closed", "escalated"}:
            raise ValueError("Invalid conversation status.")
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone():
                raise KeyError("Conversation not found.")
            db.execute(
                """INSERT INTO conversation_state(session_id,property_id,status,human_takeover,updated_at) VALUES(?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET status=excluded.status,human_takeover=excluded.human_takeover,updated_at=excluded.updated_at""",
                (session_id, property_id, status, 1 if human_takeover else 0, int(time.time())),
            )
        return {"session_id": session_id, "property_id": property_id, "status": status, "human_takeover": human_takeover}

    def staff_messages(self, session_id: str, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT message_id,content,created_at FROM conversation_messages WHERE session_id=? AND property_id=? AND role='staff' ORDER BY created_at,message_id",
                (session_id, property_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def conversation_state(self, session_id: str, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM conversation_state WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone()
        return {"status": row["status"], "human_takeover": bool(row["human_takeover"])} if row else {"status": "open", "human_takeover": False}
