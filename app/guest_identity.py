import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .database import connect_database


def _now() -> int:
    return int(time.time())


def normalize_mac(value: str) -> str:
    compact = "".join(ch for ch in value.lower() if ch.isalnum())
    if len(compact) != 12:
        raise ValueError("Invalid WLAN device identifier.")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


def pseudonymous_device_id(property_secret: str, raw_mac: str) -> str:
    normalized = normalize_mac(raw_mac)
    digest = hmac.new(property_secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()
    return "device_" + digest[:32]


class GuestIdentityStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS property_secrets (
                    property_id TEXT PRIMARY KEY,
                    secret TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS device_identities (
                    device_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'wlan'
                );
                CREATE TABLE IF NOT EXISTS concierge_stays (
                    stay_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    pms_guest_id TEXT,
                    room TEXT,
                    status TEXT NOT NULL,
                    memory_summary TEXT NOT NULL DEFAULT '{}',
                    retention_until INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    checked_out_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS guest_sessions (
                    guest_session_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT NOT NULL,
                    concierge_session_id TEXT,
                    antlabs_session_id TEXT,
                    browser_session_id TEXT,
                    created_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                );
                """
            )

    def property_secret(self, property_id: str) -> str:
        with self._connect() as db:
            row = db.execute("SELECT secret FROM property_secrets WHERE property_id=?", (property_id,)).fetchone()
            if row:
                return row["secret"]
            secret = uuid.uuid4().hex + uuid.uuid4().hex
            db.execute(
                "INSERT INTO property_secrets VALUES (?,?,?)",
                (property_id, secret, _now()),
            )
            return secret

    def observe_device(self, property_id: str, raw_mac: str, source: str = "wlan") -> str:
        device_id = pseudonymous_device_id(self.property_secret(property_id), raw_mac)
        now = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO device_identities(device_id,property_id,first_seen_at,last_seen_at,source)
                VALUES(?,?,?,?,?)
                ON CONFLICT(device_id) DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                (device_id, property_id, now, now, source),
            )
        return device_id

    def reconnect_or_create_stay(
        self,
        property_id: str,
        device_id: str,
        concierge_session_id: str | None = None,
        antlabs_session_id: str | None = None,
        browser_session_id: str | None = None,
        room: str | None = None,
        pms_guest_id: str | None = None,
        retention_days: int = 2,
    ) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            stay = db.execute(
                """SELECT * FROM concierge_stays
                WHERE property_id=? AND device_id=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1""",
                (property_id, device_id),
            ).fetchone()
            if stay is None:
                stay_id = "stay_" + uuid.uuid4().hex[:16]
                retention_until = now + max(retention_days, 0) * 86400
                db.execute(
                    """INSERT INTO concierge_stays
                    (stay_id,property_id,device_id,pms_guest_id,room,status,memory_summary,retention_until,created_at,updated_at,checked_out_at)
                    VALUES(?,?,?,?,?,'active','{}',?,?,?,NULL)""",
                    (stay_id, property_id, device_id, pms_guest_id, room, retention_until, now, now),
                )
                stay = db.execute("SELECT * FROM concierge_stays WHERE stay_id=?", (stay_id,)).fetchone()
            else:
                db.execute(
                    "UPDATE concierge_stays SET room=COALESCE(?,room), pms_guest_id=COALESCE(?,pms_guest_id), updated_at=? WHERE stay_id=?",
                    (room, pms_guest_id, now, stay["stay_id"]),
                )
                stay = db.execute("SELECT * FROM concierge_stays WHERE stay_id=?", (stay["stay_id"],)).fetchone()
            guest_session_id = "gs_" + uuid.uuid4().hex[:16]
            db.execute(
                """INSERT INTO guest_sessions
                (guest_session_id,property_id,stay_id,concierge_session_id,antlabs_session_id,browser_session_id,created_at,last_seen_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (guest_session_id, property_id, stay["stay_id"], concierge_session_id, antlabs_session_id, browser_session_id, now, now),
            )
        return self._stay_dict(stay, guest_session_id)

    def update_memory(self, property_id: str, stay_id: str, memory: dict[str, Any]) -> dict[str, Any]:
        compact = {
            "conversation_summary": str(memory.get("conversation_summary", ""))[:2000],
            "preferences": list(memory.get("preferences", []))[:20],
            "recent_requests": list(memory.get("recent_requests", []))[:20],
            "unresolved_service_requests": list(memory.get("unresolved_service_requests", []))[:20],
            "important_context": str(memory.get("important_context", ""))[:1200],
        }
        with self._connect() as db:
            db.execute(
                "UPDATE concierge_stays SET memory_summary=?, updated_at=? WHERE property_id=? AND stay_id=?",
                (json.dumps(compact), _now(), property_id, stay_id),
            )
            row = db.execute("SELECT * FROM concierge_stays WHERE property_id=? AND stay_id=?", (property_id, stay_id)).fetchone()
        if not row:
            raise KeyError("Stay not found.")
        return self._stay_dict(row)

    def active_stay_for_session(self, property_id: str, concierge_session_id: str) -> dict[str, Any] | None:
        """Return only the active stay explicitly linked to this property/session."""
        with self._connect() as db:
            row = db.execute(
                """SELECT s.* FROM guest_sessions gs
                JOIN concierge_stays s ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                WHERE gs.property_id=? AND gs.concierge_session_id=? AND s.status='active'
                ORDER BY gs.last_seen_at DESC LIMIT 1""",
                (property_id, concierge_session_id),
            ).fetchone()
        return self._stay_dict(row) if row else None

    def checkout(self, property_id: str, stay_id: str, anonymize: bool = True) -> dict[str, Any]:
        now = _now()
        memory = "{}" if anonymize else None
        with self._connect() as db:
            if anonymize:
                db.execute(
                    "UPDATE concierge_stays SET status='checked_out', memory_summary=?, room=NULL, pms_guest_id=NULL, checked_out_at=?, updated_at=? WHERE property_id=? AND stay_id=?",
                    (memory, now, now, property_id, stay_id),
                )
            else:
                db.execute(
                    "UPDATE concierge_stays SET status='checked_out', checked_out_at=?, updated_at=? WHERE property_id=? AND stay_id=?",
                    (now, now, property_id, stay_id),
                )
            row = db.execute("SELECT * FROM concierge_stays WHERE property_id=? AND stay_id=?", (property_id, stay_id)).fetchone()
        if not row:
            raise KeyError("Stay not found.")
        return self._stay_dict(row)

    def sessions_for_stay(self, property_id: str, stay_id: str) -> list[str]:
        """Return explicitly linked Concierge sessions for a property-scoped stay."""
        with self._connect() as db:
            rows = db.execute(
                """SELECT concierge_session_id FROM guest_sessions
                WHERE property_id=? AND stay_id=? AND concierge_session_id IS NOT NULL""",
                (property_id, stay_id),
            ).fetchall()
        return list(dict.fromkeys(str(row["concierge_session_id"]) for row in rows if row["concierge_session_id"]))

    def cleanup_retention(self, property_id: str | None = None) -> int:
        now = _now()
        query = "DELETE FROM concierge_stays WHERE retention_until IS NOT NULL AND retention_until < ?"
        params: tuple[Any, ...] = (now,)
        if property_id:
            query += " AND property_id=?"
            params = (now, property_id)
        with self._connect() as db:
            cursor = db.execute(query, params)
            return cursor.rowcount

    def list_stays(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [self._stay_dict(row) for row in db.execute("SELECT * FROM concierge_stays WHERE property_id=? ORDER BY updated_at DESC", (property_id,))]

    def list_devices(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM device_identities WHERE property_id=? ORDER BY last_seen_at DESC", (property_id,))]

    def _stay_dict(self, row: sqlite3.Row, guest_session_id: str | None = None) -> dict[str, Any]:
        data = dict(row)
        data["memory_summary"] = json.loads(data.get("memory_summary") or "{}")
        if guest_session_id:
            data["guest_session_id"] = guest_session_id
        return data
