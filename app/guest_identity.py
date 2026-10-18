import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .database import connect_database, table_columns, table_exists


MAX_ADMIN_SESSION_PAGE_SIZE = 100
MAX_ADMIN_SESSION_PAGE_OFFSET = 1_000_000


def _session_page_bounds(limit: int, offset: int) -> tuple[int, int]:
    page_limit, page_offset = int(limit), int(offset)
    if not 1 <= page_limit <= MAX_ADMIN_SESSION_PAGE_SIZE or not 0 <= page_offset <= MAX_ADMIN_SESSION_PAGE_OFFSET:
        raise ValueError("Invalid guest-record page bounds.")
    return page_limit, page_offset


def _session_search_term(query: str) -> str:
    return str(query or "").strip().casefold()[:120]


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
                    retention_days INTEGER NOT NULL DEFAULT 2,
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
            if "retention_days" not in table_columns(db, "concierge_stays"):
                db.execute(
                    "ALTER TABLE concierge_stays ADD COLUMN retention_days INTEGER NOT NULL DEFAULT 2"
                )
            # Older releases used this deadline to expire active stays. The
            # retention window applies only after an explicit checkout.
            db.execute("UPDATE concierge_stays SET retention_until=NULL WHERE status='active'")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_concierge_stays_retention "
                "ON concierge_stays(status,retention_until)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_concierge_stays_property_activity "
                "ON concierge_stays(property_id,updated_at DESC,stay_id DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guest_sessions_property_activity "
                "ON guest_sessions(property_id,last_seen_at DESC,guest_session_id DESC)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_device_identities_property_activity "
                "ON device_identities(property_id,last_seen_at DESC,device_id DESC)"
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

    def preview_device_id(self, property_id: str, raw_mac: str) -> str:
        """Compute the property-scoped pseudonym without recording a device observation."""
        return pseudonymous_device_id(self.property_secret(property_id), raw_mac)

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
        keep_days = max(int(retention_days), 0)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if concierge_session_id:
                existing = db.execute(
                    """SELECT gs.guest_session_id,gs.stay_id,s.device_id,s.status
                    FROM guest_sessions gs JOIN concierge_stays s
                      ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                    WHERE gs.property_id=? AND gs.concierge_session_id=?
                    ORDER BY gs.last_seen_at DESC LIMIT 1""",
                    (property_id, concierge_session_id),
                ).fetchone()
                if existing:
                    if existing["status"] != "active" or existing["device_id"] != device_id:
                        raise ValueError("That Concierge session is already linked to a different stay or device.")
                    db.execute(
                        """UPDATE concierge_stays SET room=COALESCE(?,room),pms_guest_id=COALESCE(?,pms_guest_id),
                        retention_days=?,updated_at=? WHERE property_id=? AND stay_id=? AND status='active'""",
                        (room, pms_guest_id, keep_days, now, property_id, existing["stay_id"]),
                    )
                    db.execute(
                        "UPDATE guest_sessions SET last_seen_at=? WHERE property_id=? AND guest_session_id=?",
                        (now, property_id, existing["guest_session_id"]),
                    )
                    stay = db.execute(
                        "SELECT * FROM concierge_stays WHERE property_id=? AND stay_id=?",
                        (property_id, existing["stay_id"]),
                    ).fetchone()
                    return self._stay_dict(stay, str(existing["guest_session_id"]))
            stay = db.execute(
                """SELECT * FROM concierge_stays
                WHERE property_id=? AND device_id=? AND status='active'
                ORDER BY updated_at DESC LIMIT 1""",
                (property_id, device_id),
            ).fetchone()
            if stay is None:
                stay_id = "stay_" + uuid.uuid4().hex[:16]
                db.execute(
                    """INSERT INTO concierge_stays
                    (stay_id,property_id,device_id,pms_guest_id,room,status,memory_summary,retention_until,retention_days,created_at,updated_at,checked_out_at)
                    VALUES(?,?,?,?,?,'active','{}',NULL,?,?,?,NULL)""",
                    (stay_id, property_id, device_id, pms_guest_id, room, keep_days, now, now),
                )
                stay = db.execute("SELECT * FROM concierge_stays WHERE stay_id=?", (stay_id,)).fetchone()
            else:
                db.execute(
                    "UPDATE concierge_stays SET room=COALESCE(?,room), pms_guest_id=COALESCE(?,pms_guest_id), retention_days=?, retention_until=NULL, updated_at=? WHERE property_id=? AND stay_id=? AND status='active'",
                    (room, pms_guest_id, keep_days, now, property_id, stay["stay_id"]),
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

    def stay_for_session(self, property_id: str, concierge_session_id: str) -> dict[str, Any] | None:
        """Return the most recent explicitly linked stay without crossing property scope."""
        with self._connect() as db:
            row = db.execute(
                """SELECT s.* FROM guest_sessions gs
                JOIN concierge_stays s ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                WHERE gs.property_id=? AND gs.concierge_session_id=?
                ORDER BY gs.last_seen_at DESC,s.updated_at DESC LIMIT 1""",
                (property_id, concierge_session_id),
            ).fetchone()
        return self._stay_dict(row) if row else None

    def checkout(self, property_id: str, stay_id: str, anonymize: bool = True) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            if anonymize:
                db.execute(
                    """UPDATE concierge_stays
                       SET status='checked_out',memory_summary='{}',room=NULL,pms_guest_id=NULL,
                           checked_out_at=COALESCE(checked_out_at,?),
                           retention_until=COALESCE(retention_until,? + retention_days * 86400),
                           updated_at=CASE WHEN status='active' THEN ? ELSE updated_at END
                       WHERE property_id=? AND stay_id=?""",
                    (now, now, now, property_id, stay_id),
                )
            else:
                db.execute(
                    """UPDATE concierge_stays
                       SET status='checked_out',checked_out_at=COALESCE(checked_out_at,?),
                           retention_until=COALESCE(retention_until,? + retention_days * 86400),
                           updated_at=CASE WHEN status='active' THEN ? ELSE updated_at END
                       WHERE property_id=? AND stay_id=?""",
                    (now, now, now, property_id, stay_id),
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

    def get_stay(self, property_id: str, stay_id: str) -> dict[str, Any] | None:
        """Return a stay only when both its ID and property match."""
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM concierge_stays WHERE property_id=? AND stay_id=?",
                (property_id, stay_id),
            ).fetchone()
        return self._stay_dict(row) if row else None

    def guest_sessions_for_stay(self, property_id: str, stay_id: str) -> list[dict[str, Any]]:
        """Return property-scoped WLAN association metadata for one known stay."""
        with self._connect() as db:
            rows = db.execute(
                """SELECT guest_session_id,stay_id,concierge_session_id,antlabs_session_id,
                browser_session_id,created_at,last_seen_at FROM guest_sessions
                WHERE property_id=? AND stay_id=? ORDER BY last_seen_at DESC,guest_session_id DESC""",
                (property_id, stay_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def unlink_guest_session(self, property_id: str, guest_session_id: str) -> str:
        """Remove only the WLAN-to-stay association, preserving the stay and app session."""
        with self._connect() as db:
            row = db.execute(
                "SELECT stay_id FROM guest_sessions WHERE property_id=? AND guest_session_id=?",
                (property_id, guest_session_id),
            ).fetchone()
            if row is None:
                raise KeyError("Guest link not found.")
            db.execute(
                "DELETE FROM guest_sessions WHERE property_id=? AND guest_session_id=?",
                (property_id, guest_session_id),
            )
        return str(row["stay_id"])

    def cleanup_retention(self, property_id: str | None = None, *, now: int | None = None) -> int:
        current = _now() if now is None else int(now)
        query = "DELETE FROM concierge_stays WHERE status='checked_out' AND retention_until IS NOT NULL AND retention_until<=?"
        params: tuple[Any, ...] = (current,)
        if property_id is not None:
            query += " AND property_id=?"
            params = (current, property_id)
        query += " RETURNING property_id,stay_id,device_id"
        with self._connect() as db:
            if not table_exists(db, "concierge_stays"):
                return 0
            expired = db.execute(query, params).fetchall()
            for stay in expired:
                db.execute(
                    "DELETE FROM guest_sessions WHERE property_id=? AND stay_id=?",
                    (stay["property_id"], stay["stay_id"]),
                )
                db.execute(
                    """DELETE FROM device_identities WHERE property_id=? AND device_id=?
                       AND NOT EXISTS (SELECT 1 FROM concierge_stays s
                           WHERE s.property_id=device_identities.property_id
                             AND s.device_id=device_identities.device_id)""",
                    (stay["property_id"], stay["device_id"]),
                )
            orphan_query = """DELETE FROM guest_sessions WHERE NOT EXISTS (
                SELECT 1 FROM concierge_stays s
                WHERE s.property_id=guest_sessions.property_id AND s.stay_id=guest_sessions.stay_id
            )"""
            orphan_params: tuple[Any, ...] = ()
            if property_id is not None:
                orphan_query += " AND property_id=?"
                orphan_params = (property_id,)
            db.execute(orphan_query, orphan_params)
            return len(expired)

    def list_stays(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [self._stay_dict(row) for row in db.execute("SELECT * FROM concierge_stays WHERE property_id=? ORDER BY updated_at DESC", (property_id,))]

    def list_stays_page(
        self, property_id: str, *, limit: int = 50, offset: int = 0, query: str = "", status: str | None = None,
    ) -> dict[str, Any]:
        limit, offset = _session_page_bounds(limit, offset)
        search = _session_search_term(query)
        pattern = f"%{search}%" if search else ""
        if status not in (None, "active", "checked_out"):
            raise ValueError("Unsupported stay filter.")
        with self._connect() as db:
            total = int(db.execute(
                """SELECT COUNT(*) FROM concierge_stays
                WHERE property_id=? AND (?='' OR status=?)
                  AND (?='' OR LOWER(stay_id) LIKE ? OR LOWER(COALESCE(device_id,'')) LIKE ?
                    OR LOWER(COALESCE(pms_guest_id,'')) LIKE ? OR LOWER(COALESCE(room,'')) LIKE ?
                    OR LOWER(COALESCE(memory_summary,'')) LIKE ?)""",
                (property_id, status or "", status or "", search, pattern, pattern, pattern, pattern, pattern),
            ).fetchone()[0])
            actual_offset = min(offset, max(total - 1, 0) // limit * limit)
            rows = db.execute(
                """SELECT * FROM concierge_stays
                WHERE property_id=? AND (?='' OR status=?)
                  AND (?='' OR LOWER(stay_id) LIKE ? OR LOWER(COALESCE(device_id,'')) LIKE ?
                    OR LOWER(COALESCE(pms_guest_id,'')) LIKE ? OR LOWER(COALESCE(room,'')) LIKE ?
                    OR LOWER(COALESCE(memory_summary,'')) LIKE ?)
                ORDER BY updated_at DESC, stay_id DESC LIMIT ? OFFSET ?""",
                (property_id, status or "", status or "", search, pattern, pattern, pattern, pattern, pattern, limit, actual_offset),
            ).fetchall()
        return {"items": [self._stay_dict(row) for row in rows], "total": total, "limit": limit, "offset": actual_offset}

    def list_guest_sessions(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT gs.guest_session_id,gs.stay_id,gs.concierge_session_id,
                gs.antlabs_session_id,gs.browser_session_id,gs.created_at,gs.last_seen_at,
                s.device_id,s.room,s.status AS stay_status
                FROM guest_sessions gs
                JOIN concierge_stays s ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                WHERE gs.property_id=? ORDER BY gs.last_seen_at DESC""",
                (property_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_guest_sessions_page(
        self, property_id: str, *, limit: int = 50, offset: int = 0, query: str = "",
    ) -> dict[str, Any]:
        limit, offset = _session_page_bounds(limit, offset)
        search = _session_search_term(query)
        pattern = f"%{search}%" if search else ""
        params = (property_id, search, pattern, pattern, pattern, pattern, pattern, pattern, pattern)
        with self._connect() as db:
            count = db.execute(
                """SELECT COUNT(*) FROM guest_sessions gs
                JOIN concierge_stays s ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                WHERE gs.property_id=? AND (?='' OR LOWER(gs.guest_session_id) LIKE ? OR LOWER(gs.stay_id) LIKE ?
                    OR LOWER(COALESCE(gs.concierge_session_id,'')) LIKE ? OR LOWER(COALESCE(gs.antlabs_session_id,'')) LIKE ?
                    OR LOWER(COALESCE(gs.browser_session_id,'')) LIKE ? OR LOWER(COALESCE(s.device_id,'')) LIKE ?
                    OR LOWER(COALESCE(s.room,'')) LIKE ?)""",
                params,
            ).fetchone()
            total = int(count[0])
            actual_offset = min(offset, max(total - 1, 0) // limit * limit)
            rows = db.execute(
                """SELECT gs.guest_session_id,gs.stay_id,gs.concierge_session_id,
                gs.antlabs_session_id,gs.browser_session_id,gs.created_at,gs.last_seen_at,
                s.device_id,s.room,s.status AS stay_status
                FROM guest_sessions gs
                JOIN concierge_stays s ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                WHERE gs.property_id=? AND (?='' OR LOWER(gs.guest_session_id) LIKE ? OR LOWER(gs.stay_id) LIKE ?
                    OR LOWER(COALESCE(gs.concierge_session_id,'')) LIKE ? OR LOWER(COALESCE(gs.antlabs_session_id,'')) LIKE ?
                    OR LOWER(COALESCE(gs.browser_session_id,'')) LIKE ? OR LOWER(COALESCE(s.device_id,'')) LIKE ?
                    OR LOWER(COALESCE(s.room,'')) LIKE ?)
                ORDER BY gs.last_seen_at DESC, gs.guest_session_id DESC LIMIT ? OFFSET ?""",
                (*params, limit, actual_offset),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": actual_offset}

    def list_devices(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM device_identities WHERE property_id=? ORDER BY last_seen_at DESC", (property_id,))]

    def list_devices_page(
        self, property_id: str, *, limit: int = 50, offset: int = 0, query: str = "",
    ) -> dict[str, Any]:
        limit, offset = _session_page_bounds(limit, offset)
        search = _session_search_term(query)
        pattern = f"%{search}%" if search else ""
        with self._connect() as db:
            total = int(db.execute(
                """SELECT COUNT(*) FROM device_identities WHERE property_id=?
                AND (?='' OR LOWER(device_id) LIKE ? OR LOWER(source) LIKE ?)""",
                (property_id, search, pattern, pattern),
            ).fetchone()[0])
            actual_offset = min(offset, max(total - 1, 0) // limit * limit)
            rows = db.execute(
                """SELECT * FROM device_identities WHERE property_id=?
                AND (?='' OR LOWER(device_id) LIKE ? OR LOWER(source) LIKE ?)
                ORDER BY last_seen_at DESC, device_id DESC LIMIT ? OFFSET ?""",
                (property_id, search, pattern, pattern, limit, actual_offset),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": actual_offset}

    def session_record_counts(self, property_id: str) -> dict[str, int]:
        with self._connect() as db:
            stays = db.execute(
                """SELECT COUNT(*) AS total,
                COUNT(CASE WHEN status='active' THEN 1 END) AS active
                FROM concierge_stays WHERE property_id=?""", (property_id,),
            ).fetchone()
            links = db.execute("SELECT COUNT(*) FROM guest_sessions WHERE property_id=?", (property_id,)).fetchone()
            devices = db.execute("SELECT COUNT(*) FROM device_identities WHERE property_id=?", (property_id,)).fetchone()
        return {"stays": int(stays["total"]), "active_stays": int(stays["active"]), "guest_links": int(links[0]), "devices": int(devices[0])}

    def _stay_dict(self, row: sqlite3.Row, guest_session_id: str | None = None) -> dict[str, Any]:
        data = dict(row)
        data["memory_summary"] = json.loads(data.get("memory_summary") or "{}")
        if guest_session_id:
            data["guest_session_id"] = guest_session_id
        return data
