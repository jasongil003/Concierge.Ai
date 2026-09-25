import json
import hashlib
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
    network_status: str = "active"
    network_failure_at: int | None = None


class SessionStore:
    def __init__(self, path: Path, ttl_minutes: int = 30) -> None:
        self.path = path
        self.ttl_seconds = ttl_minutes * 60
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
                    last_seen_at INTEGER NOT NULL,
                    network_status TEXT NOT NULL DEFAULT 'active',
                    network_failure_at INTEGER
                )
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}
            if "network_status" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN network_status TEXT NOT NULL DEFAULT 'active'")
            if "network_failure_at" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN network_failure_at INTEGER")
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
                    created_at INTEGER NOT NULL,
                    sender_user_id TEXT
                );
                CREATE TABLE IF NOT EXISTS conversation_state (
                    session_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    human_takeover INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'ai_active',
                    department_type TEXT,
                    department_id TEXT,
                    restaurant_id TEXT,
                    assigned_user_id TEXT,
                    assigned_at INTEGER,
                    escalation_reason TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS conversation_retention (
                    property_id TEXT PRIMARY KEY,
                    retention_days INTEGER NOT NULL DEFAULT 30,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS gateway_assertion_nonces (
                    nonce_hash TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gateway_nonces_expiry ON gateway_assertion_nonces(expires_at);
                CREATE TABLE IF NOT EXISTS conversation_audit_events (
                    event_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    restaurant_id TEXT,
                    conversation_id TEXT NOT NULL,
                    actor_user_id TEXT,
                    action TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_audit_property_time
                    ON conversation_audit_events(property_id,created_at DESC);
                """
            )
            for name, definition in (
                ("sender_user_id", "TEXT"),
            ):
                self._ensure_column(db, "conversation_messages", name, definition)
            for name, definition in (
                ("state", "TEXT NOT NULL DEFAULT 'ai_active'"),
                ("department_type", "TEXT"),
                ("department_id", "TEXT"),
                ("restaurant_id", "TEXT"),
                ("assigned_user_id", "TEXT"),
                ("assigned_at", "INTEGER"),
                ("escalation_reason", "TEXT NOT NULL DEFAULT ''"),
            ):
                self._ensure_column(db, "conversation_state", name, definition)
            db.execute(
                """UPDATE conversation_state SET state=CASE
                WHEN human_takeover=1 THEN 'human_active'
                WHEN status='escalated' THEN 'waiting_for_staff'
                WHEN status='closed' THEN 'resolved'
                ELSE 'ai_active' END
                WHERE state='ai_active'"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_conversation_state_queue ON conversation_state(property_id,restaurant_id,state,assigned_user_id)")

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, name: str, definition: str) -> None:
        allowed_definitions = {
            "conversation_messages": {"sender_user_id": "TEXT"},
            "conversation_state": {
                "state": "TEXT NOT NULL DEFAULT 'ai_active'",
                "department_type": "TEXT",
                "department_id": "TEXT",
                "restaurant_id": "TEXT",
                "assigned_user_id": "TEXT",
                "assigned_at": "INTEGER",
                "escalation_reason": "TEXT NOT NULL DEFAULT ''",
            },
        }
        if allowed_definitions.get(table, {}).get(name) != definition:
            raise ValueError("Unsupported schema column migration.")
        # Identifiers and DDL are selected from the fixed migration map above.
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}  # nosec B608
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")  # nosec B608

    def consume_gateway_nonce(self, property_id: str, nonce: str, now: int | None = None) -> bool:
        """Atomically reserve a signed gateway nonce; only the hash is persisted."""
        moment = int(now if now is not None else time.time())
        nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM gateway_assertion_nonces WHERE expires_at <= ?", (moment,))
            try:
                db.execute(
                    "INSERT INTO gateway_assertion_nonces(nonce_hash,property_id,created_at,expires_at) VALUES(?,?,?,?)",
                    (nonce_hash, property_id, moment, moment + 600),
                )
            except sqlite3.IntegrityError:
                return False
        return True

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
                (session_id, property_id, client_id, gateway_context, authenticated, created_at, last_seen_at, network_status, network_failure_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', NULL)
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
            network_status=row["network_status"],
            network_failure_at=row["network_failure_at"],
        )

    def peek(self, session_id: str) -> SessionRecord | None:
        self.cleanup_expired()
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_id=row["session_id"], property_id=row["property_id"], client_id=row["client_id"],
            gateway_context=json.loads(row["gateway_context"]), authenticated=bool(row["authenticated"]),
            created_at=row["created_at"], last_seen_at=row["last_seen_at"],
            network_status=row["network_status"], network_failure_at=row["network_failure_at"],
        )

    def mark_network_status(self, session_id: str, status: str) -> None:
        if status not in {"active", "suspended"}:
            raise ValueError("Invalid network session status.")
        with self._connect() as db:
            db.execute(
                "UPDATE sessions SET network_status=?,network_failure_at=? WHERE session_id=?",
                (status, int(time.time()) if status == "suspended" else None, session_id),
            )

    def delete(self, session_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))

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
        sender_user_id: str | None = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO conversation_messages
                (message_id,property_id,session_id,role,content,provider,model,latency_ms,error,created_at,sender_user_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (uuid.uuid4().hex, property_id, session_id, role, content[:8000], provider, model, latency_ms, error, int(time.time()), sender_user_id),
            )

    def record_ai_message_if_active(
        self,
        session_id: str,
        property_id: str,
        content: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
    ) -> bool:
        """Persist an AI reply only if no human/resolved state won the race."""
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = db.execute(
                "SELECT state FROM conversation_state WHERE session_id=? AND property_id=?",
                (session_id, property_id),
            ).fetchone()
            if state and state["state"] in {"human_active", "resolved"}:
                return False
            db.execute(
                """INSERT INTO conversation_messages
                (message_id,property_id,session_id,role,content,provider,model,latency_ms,error,created_at,sender_user_id)
                VALUES(?,?,?,'assistant',?,?,?,?,?, ?,NULL)""",
                (uuid.uuid4().hex, property_id, session_id, content[:8000], provider, model, latency_ms, error, now),
            )
        return True

    def recent_messages(self, session_id: str, property_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT role,content FROM conversation_messages
                WHERE session_id=? AND property_id=? AND role IN ('guest','assistant')
                ORDER BY created_at DESC,message_id DESC LIMIT ?""",
                (session_id, property_id, max(1, min(limit, 20))),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

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

    def operational_metrics(self, property_id: str, days: int = 7) -> dict[str, Any]:
        cutoff = int(time.time()) - max(1, min(days, 90)) * 86400
        with self._connect() as db:
            rows = db.execute(
                """SELECT provider,model,COUNT(*) AS requests,
                COALESCE(AVG(latency_ms),0) AS average_latency_ms,
                SUM(CASE WHEN error IS NOT NULL AND error!='' THEN 1 ELSE 0 END) AS errors
                FROM conversation_messages
                WHERE property_id=? AND role='assistant' AND created_at>=?
                GROUP BY provider,model ORDER BY requests DESC""",
                (property_id, cutoff),
            ).fetchall()
            activity = db.execute(
                """SELECT session_id,role,provider,model,latency_ms,error,created_at
                FROM conversation_messages WHERE property_id=? ORDER BY created_at DESC LIMIT 12""",
                (property_id,),
            ).fetchall()
        providers = [dict(row) for row in rows]
        return {
            "days": days,
            "requests": sum(int(row["requests"] or 0) for row in rows),
            "errors": sum(int(row["errors"] or 0) for row in rows),
            "average_latency_ms": round(
                sum(float(row["average_latency_ms"] or 0) * int(row["requests"] or 0) for row in rows)
                / max(1, sum(int(row["requests"] or 0) for row in rows))
            ),
            "providers": providers,
            "recent_activity": [dict(row) for row in activity],
        }

    def sessions(self, property_id: str) -> list[dict[str, Any]]:
        now = int(time.time())
        active_cutoff = now - self.ttl_seconds
        with self._connect() as db:
            rows = db.execute(
                """SELECT s.session_id,s.property_id,s.authenticated,s.created_at,s.last_seen_at,
                COALESCE(cs.status,'open') AS interaction_status,
                COALESCE(cs.human_takeover,0) AS human_takeover,
                COUNT(m.message_id) AS message_count,
                MAX(CASE WHEN m.role='assistant' THEN m.provider END) AS last_provider
                FROM sessions s
                LEFT JOIN conversation_state cs ON cs.session_id=s.session_id AND cs.property_id=s.property_id
                LEFT JOIN conversation_messages m ON m.session_id=s.session_id AND m.property_id=s.property_id
                WHERE s.property_id=? GROUP BY s.session_id ORDER BY s.last_seen_at DESC""",
                (property_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "authenticated": bool(row["authenticated"]),
                "human_takeover": bool(row["human_takeover"]),
                "session_status": "active" if int(row["last_seen_at"]) >= active_cutoff else "expired",
            }
            for row in rows
        ]

    def retention(self, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT retention_days,updated_at FROM conversation_retention WHERE property_id=?",
                (property_id,),
            ).fetchone()
        return {"retention_days": int(row["retention_days"]) if row else 30, "updated_at": row["updated_at"] if row else None}

    def set_retention(self, property_id: str, retention_days: int) -> dict[str, Any]:
        if retention_days < 1 or retention_days > 365:
            raise ValueError("Conversation retention must be between 1 and 365 days.")
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """INSERT INTO conversation_retention(property_id,retention_days,updated_at) VALUES(?,?,?)
                ON CONFLICT(property_id) DO UPDATE SET retention_days=excluded.retention_days,updated_at=excluded.updated_at""",
                (property_id, retention_days, now),
            )
        return {"retention_days": retention_days, "updated_at": now}

    def purge_expired_conversations(self, property_id: str) -> int:
        retention_days = self.retention(property_id)["retention_days"]
        cutoff = int(time.time()) - retention_days * 86400
        with self._connect() as db:
            session_ids = [
                row[0]
                for row in db.execute(
                    "SELECT session_id FROM sessions WHERE property_id=? AND last_seen_at<?",
                    (property_id, cutoff),
                ).fetchall()
            ]
            if not session_ids:
                return 0
            placeholders = ",".join("?" for _ in session_ids)
            params = (property_id, *session_ids)
            db.execute(f"DELETE FROM conversation_messages WHERE property_id=? AND session_id IN ({placeholders})", params)  # nosec B608
            db.execute(f"DELETE FROM conversation_state WHERE property_id=? AND session_id IN ({placeholders})", params)  # nosec B608
        return len(session_ids)

    def conversations(self, property_id: str, restaurant_ids: set[str] | None = None) -> list[dict[str, Any]]:
        self.purge_expired_conversations(property_id)
        if restaurant_ids is not None and not restaurant_ids:
            return []
        restaurant_clause = ""
        restaurant_params: tuple[Any, ...] = ()
        if restaurant_ids is not None:
            ordered_ids = sorted(restaurant_ids)
            restaurant_clause = f"AND cs.restaurant_id IN ({','.join('?' for _ in ordered_ids)})"  # nosec B608
            restaurant_params = tuple(ordered_ids)
        query = (
            """SELECT s.session_id,s.client_id,s.authenticated,s.created_at,s.last_seen_at,
                COALESCE(cs.status,'open') AS status,COALESCE(cs.human_takeover,0) AS human_takeover,
                COALESCE(cs.state,'ai_active') AS state,cs.department_type,cs.department_id,cs.restaurant_id,
                cs.assigned_user_id,cs.assigned_at,cs.escalation_reason,
                COUNT(m.message_id) AS message_count,MAX(m.created_at) AS last_message_at
                FROM sessions s LEFT JOIN conversation_messages m ON m.session_id=s.session_id AND m.property_id=s.property_id
                LEFT JOIN conversation_state cs ON cs.session_id=s.session_id AND cs.property_id=s.property_id
                WHERE s.property_id=? """
            + restaurant_clause
            + " GROUP BY s.session_id ORDER BY COALESCE(MAX(m.created_at),s.created_at) DESC"
        )
        with self._connect() as db:
            # The optional clause consists only of generated placeholders; all restaurant IDs are bound values.
            rows = db.execute(query, (property_id, *restaurant_params)).fetchall()  # nosec B608
            result = []
            for row in rows:
                messages = db.execute(
                    "SELECT message_id,role,content,provider,model,latency_ms,error,created_at FROM conversation_messages WHERE property_id=? AND session_id=? ORDER BY created_at,message_id",
                    (property_id, row["session_id"]),
                ).fetchall()
                result.append({**dict(row), "authenticated": bool(row["authenticated"]), "human_takeover": bool(row["human_takeover"]), "messages": [dict(item) for item in messages]})
        return result

    def set_conversation_state(
        self,
        session_id: str,
        property_id: str,
        status: str,
        human_takeover: bool,
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"open", "closed", "escalated"}:
            raise ValueError("Invalid conversation status.")
        next_state = "human_active" if human_takeover else {"open": "ai_active", "closed": "resolved", "escalated": "waiting_for_staff"}[status]
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone():
                raise KeyError("Conversation not found.")
            db.execute(
                """INSERT INTO conversation_state
                (session_id,property_id,status,human_takeover,updated_at,state)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET status=excluded.status,human_takeover=excluded.human_takeover,
                updated_at=excluded.updated_at,state=excluded.state,
                assigned_user_id=CASE WHEN excluded.human_takeover=0 THEN NULL ELSE conversation_state.assigned_user_id END,
                assigned_at=CASE WHEN excluded.human_takeover=0 THEN NULL ELSE conversation_state.assigned_at END""",
                (session_id, property_id, status, 1 if human_takeover else 0, int(time.time()), next_state),
            )
            row = db.execute("SELECT restaurant_id FROM conversation_state WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone()
            self._record_conversation_audit(db, property_id, row["restaurant_id"], session_id, actor_user_id, "takeover" if human_takeover else next_state)
        return {"session_id": session_id, "property_id": property_id, "status": status, "state": next_state, "human_takeover": human_takeover}

    def escalate_conversation(self, session_id: str, property_id: str, restaurant_id: str, reason: str = "") -> dict[str, Any]:
        now = int(time.time())
        clean_reason = " ".join(str(reason or "").split())[:500]
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM sessions WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone():
                raise KeyError("Conversation not found.")
            current = db.execute(
                "SELECT * FROM conversation_state WHERE session_id=? AND property_id=?",
                (session_id, property_id),
            ).fetchone()
            if current and current["state"] == "human_active":
                raise ValueError("A staff member is already handling this conversation.")
            if current and current["state"] in {"waiting_for_staff", "assigned"}:
                if current["restaurant_id"] != restaurant_id:
                    raise ValueError("This conversation is already queued for a different restaurant.")
            else:
                db.execute(
                    """INSERT INTO conversation_state
                    (session_id,property_id,status,human_takeover,updated_at,state,department_type,department_id,restaurant_id,assigned_user_id,assigned_at,escalation_reason)
                    VALUES(?,?,'escalated',0,?,'waiting_for_staff','restaurant',NULL,?,NULL,NULL,?)
                    ON CONFLICT(session_id) DO UPDATE SET status='escalated',human_takeover=0,updated_at=excluded.updated_at,
                    state='waiting_for_staff',department_type='restaurant',department_id=NULL,restaurant_id=excluded.restaurant_id,
                    assigned_user_id=NULL,assigned_at=NULL,escalation_reason=excluded.escalation_reason""",
                    (session_id, property_id, now, restaurant_id, clean_reason),
                )
                self._record_conversation_audit(db, property_id, restaurant_id, session_id, None, "escalated")
        return self.conversation_state(session_id, property_id)

    def accept_conversation(self, session_id: str, property_id: str, actor_user_id: str) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT restaurant_id,state,assigned_user_id FROM conversation_state WHERE session_id=? AND property_id=?",
                (session_id, property_id),
            ).fetchone()
            if not row or not row["restaurant_id"]:
                raise KeyError("Restaurant conversation not found.")
            cursor = db.execute(
                """UPDATE conversation_state SET state='human_active',status='open',human_takeover=1,
                assigned_user_id=?,assigned_at=?,updated_at=?
                WHERE session_id=? AND property_id=? AND (
                    (state='waiting_for_staff' AND assigned_user_id IS NULL)
                    OR (state='assigned' AND assigned_user_id=?)
                )""",
                (actor_user_id, now, now, session_id, property_id, actor_user_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Conversation is already assigned or no longer waiting.")
            self._record_conversation_audit(db, property_id, row["restaurant_id"], session_id, actor_user_id, "accepted")
        return self.conversation_state(session_id, property_id)

    def assign_conversation(
        self, session_id: str, property_id: str, target_user_id: str, actor_user_id: str
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT restaurant_id,state,assigned_user_id FROM conversation_state WHERE session_id=? AND property_id=?",
                (session_id, property_id),
            ).fetchone()
            if not row or not row["restaurant_id"] or row["state"] not in {"waiting_for_staff", "assigned", "human_active"}:
                raise KeyError("Assignable restaurant conversation not found.")
            db.execute(
                """UPDATE conversation_state SET state='assigned',status='escalated',human_takeover=0,
                assigned_user_id=?,assigned_at=?,updated_at=? WHERE session_id=? AND property_id=?""",
                (target_user_id, now, now, session_id, property_id),
            )
            action = "reassigned" if row["assigned_user_id"] else "assigned"
            self._record_conversation_audit(db, property_id, row["restaurant_id"], session_id, actor_user_id, action)
        return self.conversation_state(session_id, property_id)

    def resolve_conversation(
        self, session_id: str, property_id: str, actor_user_id: str, *, allow_unassigned: bool = False
    ) -> dict[str, Any]:
        return self._finish_human_conversation(session_id, property_id, actor_user_id, "resolved", allow_unassigned)

    def return_conversation_to_ai(
        self, session_id: str, property_id: str, actor_user_id: str, *, allow_unassigned: bool = False
    ) -> dict[str, Any]:
        return self._finish_human_conversation(session_id, property_id, actor_user_id, "returned_to_ai", allow_unassigned)

    def _finish_human_conversation(
        self, session_id: str, property_id: str, actor_user_id: str, next_state: str, allow_unassigned: bool
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT restaurant_id,state,assigned_user_id FROM conversation_state WHERE session_id=? AND property_id=?",
                (session_id, property_id),
            ).fetchone()
            if not row:
                raise KeyError("Conversation not found.")
            if not allow_unassigned and row["assigned_user_id"] != actor_user_id:
                raise PermissionError("Only the assigned staff member or an authorized manager can change this conversation.")
            status = "closed" if next_state == "resolved" else "open"
            db.execute(
                """UPDATE conversation_state SET state=?,status=?,human_takeover=0,assigned_user_id=NULL,
                assigned_at=NULL,updated_at=? WHERE session_id=? AND property_id=?""",
                (next_state, status, now, session_id, property_id),
            )
            self._record_conversation_audit(db, property_id, row["restaurant_id"], session_id, actor_user_id, next_state)
        return self.conversation_state(session_id, property_id)

    def reply_to_conversation(
        self,
        session_id: str,
        property_id: str,
        actor_user_id: str,
        content: str,
        *,
        allow_unassigned: bool = False,
    ) -> dict[str, Any]:
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = db.execute(
                "SELECT restaurant_id,state,assigned_user_id FROM conversation_state WHERE session_id=? AND property_id=?",
                (session_id, property_id),
            ).fetchone()
            if not state:
                raise KeyError("Conversation not found.")
            if not state["restaurant_id"] and not allow_unassigned:
                raise PermissionError("Conversation is not assigned to a restaurant.")
            if state["state"] != "human_active":
                raise ValueError("A staff member must accept the conversation before replying.")
            if state["assigned_user_id"] != actor_user_id and not allow_unassigned:
                raise PermissionError("Only the assigned staff member can reply.")
            if not db.execute("SELECT 1 FROM sessions WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone():
                raise KeyError("Conversation not found.")
            message_id = uuid.uuid4().hex
            db.execute(
                """INSERT INTO conversation_messages
                (message_id,property_id,session_id,role,content,provider,model,latency_ms,error,created_at,sender_user_id)
                VALUES(?,?,?,'staff',?,'human','staff',NULL,NULL,?,?)""",
                (message_id, property_id, session_id, content[:8000], now, actor_user_id),
            )
            db.execute("UPDATE conversation_state SET updated_at=? WHERE session_id=? AND property_id=?", (now, session_id, property_id))
            self._record_conversation_audit(db, property_id, state["restaurant_id"], session_id, actor_user_id, "staff_reply_sent")
        return {"message_id": message_id, "status": "sent"}

    @staticmethod
    def _record_conversation_audit(
        db: sqlite3.Connection,
        property_id: str,
        restaurant_id: str | None,
        conversation_id: str,
        actor_user_id: str | None,
        action: str,
    ) -> None:
        db.execute(
            """INSERT INTO conversation_audit_events
            (event_id,property_id,restaurant_id,conversation_id,actor_user_id,action,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (uuid.uuid4().hex, property_id, restaurant_id, conversation_id, actor_user_id, action, int(time.time())),
        )

    def staff_messages(self, session_id: str, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT message_id,content,created_at,sender_user_id FROM conversation_messages WHERE session_id=? AND property_id=? AND role='staff' ORDER BY created_at,message_id",
                (session_id, property_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def conversation_state(self, session_id: str, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM conversation_state WHERE session_id=? AND property_id=?", (session_id, property_id)).fetchone()
        if not row:
            return {"status": "open", "state": "ai_active", "human_takeover": False, "restaurant_id": None, "assigned_user_id": None, "escalation_reason": ""}
        return {
            "status": row["status"],
            "state": row["state"],
            "human_takeover": bool(row["human_takeover"]),
            "restaurant_id": row["restaurant_id"],
            "department_type": row["department_type"],
            "department_id": row["department_id"],
            "assigned_user_id": row["assigned_user_id"],
            "assigned_at": row["assigned_at"],
            "escalation_reason": row["escalation_reason"],
        }
