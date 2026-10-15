"""Property and guest-session scoped optional processing consent."""

import sqlite3
import time
from pathlib import Path
from .database import connect_database, table_columns


CONSENT_CATEGORIES = (
    "location_services",
    "proactive_notifications",
    "promotional_messages",
    "external_data_processing",
)
DEFAULT_CONSENTS = {category: False for category in CONSENT_CATEGORIES}
DEFAULT_RETENTION_SECONDS = 60 * 24 * 60 * 60


class PrivacyConsentStore:
    """Store optional guest choices without including direct guest identifiers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS guest_privacy_consents (
                    property_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    granted INTEGER NOT NULL CHECK(granted IN (0, 1)),
                    stay_id TEXT,
                    updated_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY(property_id, session_id, category)
                )"""
            )
            columns = table_columns(db, "guest_privacy_consents")
            if "stay_id" not in columns:
                db.execute("ALTER TABLE guest_privacy_consents ADD COLUMN stay_id TEXT")

    def get(
        self,
        property_id: str,
        session_id: str,
        now: int | None = None,
        *,
        location_stay_id: str | None = None,
    ) -> dict[str, bool]:
        current = int(time.time()) if now is None else int(now)
        values = dict(DEFAULT_CONSENTS)
        with self._connect() as db:
            rows = db.execute(
                """SELECT category,granted,stay_id FROM guest_privacy_consents
                WHERE property_id=? AND session_id=? AND expires_at>?""",
                (property_id, session_id, current),
            ).fetchall()
        for row in rows:
            if row["category"] in values:
                if row["category"] == "location_services" and row["granted"] and row["stay_id"] != location_stay_id:
                    continue
                values[row["category"]] = bool(row["granted"])
        return values

    def set(
        self,
        property_id: str,
        session_id: str,
        consents: dict[str, bool],
        *,
        expires_at: int | None = None,
        location_stay_id: str | None = None,
        now: int | None = None,
    ) -> dict[str, bool]:
        unknown = set(consents) - set(CONSENT_CATEGORIES)
        if unknown:
            raise ValueError("Unknown privacy consent category.")
        if any(type(value) is not bool for value in consents.values()):
            raise ValueError("Privacy consent choices must be boolean.")
        if consents.get("location_services") is True and not location_stay_id:
            raise ValueError("Location consent requires an active linked stay.")
        current = int(time.time()) if now is None else int(now)
        expiry = int(expires_at) if expires_at is not None else current + DEFAULT_RETENTION_SECONDS
        if expiry <= current:
            raise ValueError("Privacy consent retention must be in the future.")
        with self._connect() as db:
            for category, granted in consents.items():
                db.execute(
                    """INSERT INTO guest_privacy_consents
                    (property_id,session_id,category,granted,stay_id,updated_at,expires_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(property_id,session_id,category) DO UPDATE SET
                    granted=excluded.granted,stay_id=excluded.stay_id,
                    updated_at=excluded.updated_at,expires_at=excluded.expires_at""",
                    (
                        property_id,
                        session_id,
                        category,
                        int(granted),
                        location_stay_id if category == "location_services" and granted else None,
                        current,
                        expiry,
                    ),
                )
        return self.get(property_id, session_id, now=current, location_stay_id=location_stay_id)

    def delete_sessions(self, property_id: str, session_ids: list[str]) -> int:
        if not session_ids:
            return 0
        with self._connect() as db:
            cursor = db.executemany(
                "DELETE FROM guest_privacy_consents WHERE property_id=? AND session_id=?",
                [(property_id, session_id) for session_id in dict.fromkeys(session_ids)],
            )
            return cursor.rowcount

    def cleanup_retention(self, now: int | None = None) -> int:
        current = int(time.time()) if now is None else int(now)
        with self._connect() as db:
            cursor = db.execute(
                """DELETE FROM guest_privacy_consents
                WHERE expires_at<=?
                   OR EXISTS (
                       SELECT 1 FROM guest_sessions gs
                       LEFT JOIN concierge_stays s
                         ON s.stay_id=gs.stay_id AND s.property_id=gs.property_id
                       WHERE gs.property_id=guest_privacy_consents.property_id
                         AND gs.concierge_session_id=guest_privacy_consents.session_id
                         AND (s.stay_id IS NULL OR s.status!='active'
                              OR (s.retention_until IS NOT NULL AND s.retention_until<=?))
                   )
                   OR EXISTS (
                       SELECT 1 FROM concierge_stays s
                       WHERE s.property_id=guest_privacy_consents.property_id
                         AND s.stay_id=guest_privacy_consents.stay_id
                         AND guest_privacy_consents.category='location_services'
                         AND (s.status!='active'
                              OR (s.retention_until IS NOT NULL AND s.retention_until<=?))
                   )""",
                (current, current, current),
            )
            return cursor.rowcount
