import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import connect_database, enable_foreign_keys, table_columns, table_exists
from urllib.parse import urlsplit


FACILITY_STATUSES = {"open", "closed", "temporarily_closed", "full", "maintenance", "private_event"}
RESTAURANT_STATUSES = FACILITY_STATUSES | {"disabled", "archived"}
SERVICE_STATUSES = ("new", "assigned", "accepted", "in_progress", "delivered", "completed", "cancelled")
NOTIFICATION_CATEGORIES = {"operational", "assistance", "experience", "promotional"}
GUEST_NOTIFICATION_DEFAULT_PREFERENCES = {
    "operational": True,
    "assistance": True,
    # Experience messages are optional, and promotional messages require opt-in.
    "experience": False,
    "promotional": False,
}
GUEST_INBOX_STATUSES = {"queued", "sent", "delivered", "read", "failed", "expired"}
GUEST_INBOX_DISPATCH_STATUSES = {"queued", "sending", "retry_wait", "sent", "dead_letter", "expired"}
MAX_GUEST_NOTIFICATION_ATTEMPTS = 10
MAX_GUEST_NOTIFICATION_CLAIM_BATCH = 100


def _now() -> int:
    return int(time.time())


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def _load(value: str | None) -> Any:
    return json.loads(value or "{}")


class HospitalityStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = connect_database(self.path)
        enable_foreign_keys(connection)
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS facility_profiles (
                    facility_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    zone_id TEXT,
                    building_id TEXT,
                    floor_id TEXT,
                    name TEXT NOT NULL,
                    facility_type TEXT NOT NULL,
                    opening_hours TEXT NOT NULL DEFAULT '{}',
                    description TEXT NOT NULL DEFAULT '',
                    images TEXT NOT NULL DEFAULT '[]',
                    capacity INTEGER,
                    booking_supported INTEGER NOT NULL DEFAULT 0,
                    live_status TEXT NOT NULL DEFAULT 'open',
                    status_note TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS facility_metadata (
                    facility_id TEXT PRIMARY KEY REFERENCES facility_profiles(facility_id) ON DELETE CASCADE,
                    property_id TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    policies TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS restaurants (
                    restaurant_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    facility_id TEXT,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    opening_hours TEXT NOT NULL DEFAULT '{}',
                    meal_periods TEXT NOT NULL DEFAULT '[]',
                    reservation_available INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    cuisine TEXT NOT NULL DEFAULT '',
                    dress_code TEXT NOT NULL DEFAULT '',
                    capacity INTEGER,
                    phone_extension TEXT NOT NULL DEFAULT '',
                    external_reservation_url TEXT NOT NULL DEFAULT '',
                    contact_details TEXT NOT NULL DEFAULT '{}',
                    images TEXT NOT NULL DEFAULT '[]',
                    internal_notes TEXT NOT NULL DEFAULT '',
                    guest_notes TEXT NOT NULL DEFAULT '',
                    archived INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(property_id, restaurant_id)
                );
                CREATE TABLE IF NOT EXISTS menus (
                    menu_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    meal_period TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    workflow_status TEXT NOT NULL DEFAULT 'published',
                    created_by TEXT,
                    updated_by TEXT,
                    approved_by TEXT,
                    published_by TEXT,
                    approved_at INTEGER,
                    published_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(property_id, menu_id),
                    FOREIGN KEY(property_id, restaurant_id)
                        REFERENCES restaurants(property_id, restaurant_id) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS menu_items (
                    item_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    menu_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    price TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    ingredients TEXT NOT NULL DEFAULT '[]',
                    allergens TEXT NOT NULL DEFAULT '[]',
                    dietary_tags TEXT NOT NULL DEFAULT '[]',
                    available INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(property_id, menu_id)
                        REFERENCES menus(property_id, menu_id) ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS restaurant_promotions (
                    promotion_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    starts_at INTEGER,
                    ends_at INTEGER,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_by TEXT,
                    updated_by TEXT,
                    approved_by TEXT,
                    published_by TEXT,
                    approved_at INTEGER,
                    published_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(property_id, restaurant_id)
                        REFERENCES restaurants(property_id, restaurant_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS hotel_events (
                    event_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    starts_at INTEGER NOT NULL,
                    ends_at INTEGER,
                    facility_id TEXT,
                    zone_id TEXT,
                    audience TEXT NOT NULL DEFAULT 'all_guests',
                    capacity INTEGER,
                    description TEXT NOT NULL DEFAULT '',
                    notification_timing TEXT NOT NULL DEFAULT '{}',
                    cta TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS service_requests (
                    request_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT,
                    room TEXT,
                    request_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    department TEXT NOT NULL DEFAULT 'front_desk',
                    status TEXT NOT NULL DEFAULT 'new',
                    sla_target_seconds INTEGER,
                    due_at INTEGER,
                    completed_at INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS departments (
                    department_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    default_sla_minutes INTEGER NOT NULL DEFAULT 30,
                    escalation_target TEXT NOT NULL DEFAULT '',
                    operating_hours TEXT NOT NULL DEFAULT '{}',
                    webhook_url TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(property_id, name)
                );
                CREATE TABLE IF NOT EXISTS service_catalog (
                    service_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    department_id TEXT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    sla_minutes INTEGER NOT NULL DEFAULT 30,
                    confirmation_required INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    archived INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(property_id, name)
                );
                CREATE TABLE IF NOT EXISTS recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'other',
                    address TEXT NOT NULL DEFAULT '',
                    map_url TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    images TEXT NOT NULL DEFAULT '[]',
                    opening_hours TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'property',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE(property_id, name)
                );
                CREATE TABLE IF NOT EXISTS service_request_history (
                    history_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guest_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    request_id TEXT,
                    stay_id TEXT,
                    resolution TEXT NOT NULL,
                    rating INTEGER,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_rules (
                    rule_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    policy TEXT NOT NULL DEFAULT '{}',
                    template TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    rule_id TEXT,
                    stay_id TEXT,
                    category TEXT NOT NULL,
                    verified_payload TEXT NOT NULL DEFAULT '{}',
                    ai_wording TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    notification_id TEXT NOT NULL,
                    stay_id TEXT,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    delivered_at INTEGER,
                    viewed_at INTEGER,
                    clicked_at INTEGER,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guest_notification_preferences (
                    property_id TEXT NOT NULL,
                    stay_id TEXT NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('operational','assistance','experience','promotional')),
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(property_id, stay_id, category)
                );
                CREATE TABLE IF NOT EXISTS guest_inbox_notifications (
                    notification_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('operational','assistance','experience','promotional')),
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','sent','delivered','read','failed','expired')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    sent_at INTEGER,
                    delivered_at INTEGER,
                    read_at INTEGER,
                    failed_at INTEGER,
                    expired_at INTEGER,
                    failure_reason TEXT NOT NULL DEFAULT '',
                    expires_at INTEGER,
                    dispatch_status TEXT NOT NULL DEFAULT 'queued',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at INTEGER NOT NULL DEFAULT 0,
                    claim_token TEXT,
                    claimed_at INTEGER,
                    dead_letter_at INTEGER,
                    scheduled_at INTEGER,
                    timezone_name TEXT NOT NULL DEFAULT 'UTC',
                    quiet_hours TEXT NOT NULL DEFAULT '{}',
                    send_window TEXT NOT NULL DEFAULT '{}',
                    max_per_window INTEGER,
                    frequency_window_seconds INTEGER,
                    UNIQUE(property_id, stay_id, event_id)
                );
                CREATE INDEX IF NOT EXISTS idx_guest_inbox_scope_created
                    ON guest_inbox_notifications(property_id, stay_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_guest_inbox_expiry
                    ON guest_inbox_notifications(status, expires_at);
                CREATE TABLE IF NOT EXISTS guest_notification_frequency_locks (
                    property_id TEXT NOT NULL,
                    stay_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    touched_at INTEGER NOT NULL,
                    PRIMARY KEY(property_id,stay_id,category)
                );
                CREATE TABLE IF NOT EXISTS guest_notification_suppressions (
                    property_id TEXT NOT NULL,
                    stay_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    suppressed_at INTEGER NOT NULL,
                    PRIMARY KEY(property_id,stay_id,event_id)
                );
                CREATE TABLE IF NOT EXISTS guest_journey_events (
                    journey_event_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    stay_id TEXT,
                    event_type TEXT NOT NULL,
                    facility_id TEXT,
                    zone_id TEXT,
                    request_id TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    occurred_at INTEGER NOT NULL
                );
                """
            )
            self._ensure_column(db, "service_requests", "service_id", "TEXT")
            self._ensure_column(db, "service_requests", "assigned_to", "TEXT")
            self._ensure_column(db, "service_requests", "notes", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "service_requests", "client_request_id", "TEXT")
            for name, definition in (
                ("dispatch_status", "TEXT NOT NULL DEFAULT 'queued'"),
                ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
                ("next_attempt_at", "INTEGER NOT NULL DEFAULT 0"),
                ("claim_token", "TEXT"),
                ("claimed_at", "INTEGER"),
                ("dead_letter_at", "INTEGER"),
                ("scheduled_at", "INTEGER"),
                ("timezone_name", "TEXT NOT NULL DEFAULT 'UTC'"),
                ("quiet_hours", "TEXT NOT NULL DEFAULT '{}'"),
                ("send_window", "TEXT NOT NULL DEFAULT '{}'"),
                ("max_per_window", "INTEGER"),
                ("frequency_window_seconds", "INTEGER"),
            ):
                self._ensure_column(db, "guest_inbox_notifications", name, definition)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guest_inbox_dispatch_due "
                "ON guest_inbox_notifications(dispatch_status,next_attempt_at,created_at)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_guest_inbox_dispatch_frequency "
                "ON guest_inbox_notifications(property_id,stay_id,category,dispatch_status,claimed_at,sent_at)"
            )
            for name, definition in (
                ("cuisine", "TEXT NOT NULL DEFAULT ''"),
                ("dress_code", "TEXT NOT NULL DEFAULT ''"),
                ("capacity", "INTEGER"),
                ("phone_extension", "TEXT NOT NULL DEFAULT ''"),
                ("external_reservation_url", "TEXT NOT NULL DEFAULT ''"),
                ("contact_details", "TEXT NOT NULL DEFAULT '{}'"),
                ("images", "TEXT NOT NULL DEFAULT '[]'"),
                ("internal_notes", "TEXT NOT NULL DEFAULT ''"),
                ("guest_notes", "TEXT NOT NULL DEFAULT ''"),
                ("archived", "INTEGER NOT NULL DEFAULT 0"),
            ):
                self._ensure_column(db, "restaurants", name, definition)
            for name, definition in (
                ("workflow_status", "TEXT NOT NULL DEFAULT 'published'"),
                ("created_by", "TEXT"),
                ("updated_by", "TEXT"),
                ("approved_by", "TEXT"),
                ("published_by", "TEXT"),
                ("approved_at", "INTEGER"),
                ("published_at", "INTEGER"),
            ):
                self._ensure_column(db, "menus", name, definition)
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_restaurants_property_restaurant ON restaurants(property_id,restaurant_id)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_menus_property_menu ON menus(property_id,menu_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_menus_property_restaurant ON menus(property_id,restaurant_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_menu_items_property_menu ON menu_items(property_id,menu_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_restaurant_promotions_property_restaurant ON restaurant_promotions(property_id,restaurant_id)")
            db.execute(
                """CREATE TABLE IF NOT EXISTS restaurant_audit_events (
                    event_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    restaurant_id TEXT,
                    actor_user_id TEXT,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_restaurant_audit_property_time ON restaurant_audit_events(property_id,created_at DESC)")
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_service_request_idempotency ON service_requests(property_id, stay_id, client_request_id) WHERE client_request_id IS NOT NULL"
            )

    def _ensure_column(self, db: sqlite3.Connection, table: str, name: str, definition: str) -> None:
        allowed_definitions = {
            "service_requests": {
                "service_id": "TEXT",
                "assigned_to": "TEXT",
                "notes": "TEXT NOT NULL DEFAULT '[]'",
                "client_request_id": "TEXT",
            },
            "guest_inbox_notifications": {
                "dispatch_status": "TEXT NOT NULL DEFAULT 'queued'",
                "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                "next_attempt_at": "INTEGER NOT NULL DEFAULT 0",
                "claim_token": "TEXT",
                "claimed_at": "INTEGER",
                "dead_letter_at": "INTEGER",
                "scheduled_at": "INTEGER",
                "timezone_name": "TEXT NOT NULL DEFAULT 'UTC'",
                "quiet_hours": "TEXT NOT NULL DEFAULT '{}'",
                "send_window": "TEXT NOT NULL DEFAULT '{}'",
                "max_per_window": "INTEGER",
                "frequency_window_seconds": "INTEGER",
            },
            "restaurants": {
                "cuisine": "TEXT NOT NULL DEFAULT ''",
                "dress_code": "TEXT NOT NULL DEFAULT ''",
                "capacity": "INTEGER",
                "phone_extension": "TEXT NOT NULL DEFAULT ''",
                "external_reservation_url": "TEXT NOT NULL DEFAULT ''",
                "contact_details": "TEXT NOT NULL DEFAULT '{}'",
                "images": "TEXT NOT NULL DEFAULT '[]'",
                "internal_notes": "TEXT NOT NULL DEFAULT ''",
                "guest_notes": "TEXT NOT NULL DEFAULT ''",
                "archived": "INTEGER NOT NULL DEFAULT 0",
            },
            "menus": {
                "workflow_status": "TEXT NOT NULL DEFAULT 'published'",
                "created_by": "TEXT",
                "updated_by": "TEXT",
                "approved_by": "TEXT",
                "published_by": "TEXT",
                "approved_at": "INTEGER",
                "published_at": "INTEGER",
            },
        }
        if allowed_definitions.get(table, {}).get(name) != definition:
            raise ValueError("Unsupported schema column migration.")
        # Identifiers and DDL are selected from the fixed migration map above.
        # B608 rationale: table is selected from the fixed migration map above.
        columns = table_columns(db, table)
        if name not in columns:
            # B608 rationale: identifiers and types are selected from the fixed migration map above.
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")  # nosec B608

    def upsert_department(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        department_id = str(payload.get("department_id") or _id("dept"))
        name = _clean(payload.get("name"), 120)
        if not name:
            raise ValueError("Department name is required.")
        sla = int(payload.get("default_sla_minutes") or 30)
        if not 1 <= sla <= 1440:
            raise ValueError("Default SLA must be between 1 and 1440 minutes.")
        record = {
            "department_id": department_id, "property_id": property_id, "name": name,
            "enabled": 1 if payload.get("enabled", True) else 0,
            "default_sla_minutes": sla,
            "escalation_target": _clean(payload.get("escalation_target"), 240),
            "operating_hours": _json(payload.get("operating_hours") or {}),
            "webhook_url": _clean(payload.get("webhook_url"), 500),
            "created_at": now, "updated_at": now,
        }
        with self._connect() as db:
            existing = db.execute("SELECT created_at FROM departments WHERE property_id=? AND department_id=?", (property_id, department_id)).fetchone()
            if existing:
                record["created_at"] = existing["created_at"]
                db.execute("""UPDATE departments SET name=:name,enabled=:enabled,default_sla_minutes=:default_sla_minutes,
                    escalation_target=:escalation_target,operating_hours=:operating_hours,webhook_url=:webhook_url,
                    updated_at=:updated_at WHERE property_id=:property_id AND department_id=:department_id""", record)
            else:
                db.execute("INSERT INTO departments VALUES (:department_id,:property_id,:name,:enabled,:default_sla_minutes,:escalation_target,:operating_hours,:webhook_url,:created_at,:updated_at)", record)
        return self._department_dict(record)

    def delete_department(self, property_id: str, department_id: str) -> bool:
        with self._connect() as db:
            db.execute(
                "UPDATE service_catalog SET department_id=NULL,updated_at=? WHERE property_id=? AND department_id=?",
                (_now(), property_id, department_id),
            )
            cursor = db.execute(
                "DELETE FROM departments WHERE property_id=? AND department_id=?",
                (property_id, department_id),
            )
        return cursor.rowcount > 0

    def upsert_service(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        service_id = str(payload.get("service_id") or _id("svc"))
        name = _clean(payload.get("name"), 160)
        if not name:
            raise ValueError("Service name is required.")
        department_id = payload.get("department_id") or None
        if department_id:
            self._require_owned("departments", "department_id", str(department_id), property_id)
        sla = int(payload.get("sla_minutes") or 30)
        if not 1 <= sla <= 1440:
            raise ValueError("SLA must be between 1 and 1440 minutes.")
        record = {
            "service_id": service_id, "property_id": property_id, "department_id": department_id,
            "name": name, "description": _clean(payload.get("description"), 1000),
            "keywords": _json([_clean(item, 80) for item in list(payload.get("keywords") or [])[:30] if _clean(item, 80)]),
            "sla_minutes": sla, "confirmation_required": 1 if payload.get("confirmation_required", True) else 0,
            "enabled": 1 if payload.get("enabled", True) else 0,
            "archived": 1 if payload.get("archived", False) else 0,
            "sort_order": int(payload.get("sort_order") or 0), "created_at": now, "updated_at": now,
        }
        with self._connect() as db:
            existing = db.execute("SELECT created_at FROM service_catalog WHERE property_id=? AND service_id=?", (property_id, service_id)).fetchone()
            if existing:
                record["created_at"] = existing["created_at"]
                db.execute("""UPDATE service_catalog SET department_id=:department_id,name=:name,description=:description,
                    keywords=:keywords,sla_minutes=:sla_minutes,confirmation_required=:confirmation_required,enabled=:enabled,
                    archived=:archived,sort_order=:sort_order,updated_at=:updated_at
                    WHERE property_id=:property_id AND service_id=:service_id""", record)
            else:
                db.execute("INSERT INTO service_catalog VALUES (:service_id,:property_id,:department_id,:name,:description,:keywords,:sla_minutes,:confirmation_required,:enabled,:archived,:sort_order,:created_at,:updated_at)", record)
        return self._service_catalog_dict(record)

    def duplicate_service(self, property_id: str, service_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM service_catalog WHERE property_id=? AND service_id=?", (property_id, service_id)).fetchone()
        if not row:
            raise KeyError("Service not found.")
        data = self._service_catalog_dict(row)
        data.pop("service_id", None)
        data["name"] = f"{data['name']} Copy"
        data["sort_order"] = int(data.get("sort_order") or 0) + 1
        return self.upsert_service(property_id, data)

    def delete_service(self, property_id: str, service_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM service_catalog WHERE property_id=? AND service_id=?", (property_id, service_id))
        return cursor.rowcount > 0

    def upsert_recommendation(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        recommendation_id = str(payload.get("recommendation_id") or _id("rec"))
        name = _clean(payload.get("name"), 160)
        if not name:
            raise ValueError("Recommendation name is required.")
        record = {
            "recommendation_id": recommendation_id, "property_id": property_id, "name": name,
            "category": _clean(payload.get("category") or "other", 80),
            "address": _clean(payload.get("address"), 300), "map_url": _clean(payload.get("map_url"), 500),
            "description": _clean(payload.get("description"), 1200),
            "images": _json(list(payload.get("images") or [])[:12]),
            "opening_hours": _json(payload.get("opening_hours") or {}),
            "source": _clean(payload.get("source") or "property", 160),
            "enabled": 1 if payload.get("enabled", True) else 0, "created_at": now, "updated_at": now,
        }
        with self._connect() as db:
            existing = db.execute("SELECT created_at FROM recommendations WHERE property_id=? AND recommendation_id=?", (property_id, recommendation_id)).fetchone()
            if existing:
                record["created_at"] = existing["created_at"]
                db.execute("""UPDATE recommendations SET name=:name,category=:category,address=:address,map_url=:map_url,
                    description=:description,images=:images,opening_hours=:opening_hours,source=:source,enabled=:enabled,
                    updated_at=:updated_at WHERE property_id=:property_id AND recommendation_id=:recommendation_id""", record)
            else:
                db.execute("INSERT INTO recommendations VALUES (:recommendation_id,:property_id,:name,:category,:address,:map_url,:description,:images,:opening_hours,:source,:enabled,:created_at,:updated_at)", record)
        return self._recommendation_dict(record)

    def delete_recommendation(self, property_id: str, recommendation_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM recommendations WHERE property_id=? AND recommendation_id=?", (property_id, recommendation_id))
        return cursor.rowcount > 0

    def catalog(self, property_id: str, guest: bool = False, department_id: str | None = None) -> dict[str, Any]:
        with self._connect() as db:
            if department_id is None:
                departments = db.execute("SELECT * FROM departments WHERE property_id=? ORDER BY name", (property_id,)).fetchall()
                services = db.execute("SELECT * FROM service_catalog WHERE property_id=? ORDER BY sort_order,name", (property_id,)).fetchall()
            else:
                departments = db.execute(
                    "SELECT * FROM departments WHERE property_id=? AND department_id=? ORDER BY name",
                    (property_id, department_id),
                ).fetchall()
                services = db.execute(
                    "SELECT * FROM service_catalog WHERE property_id=? AND department_id=? ORDER BY sort_order,name",
                    (property_id, department_id),
                ).fetchall()
        if guest:
            departments = [row for row in departments if row["enabled"]]
            services = [row for row in services if row["enabled"] and not row["archived"]]
        return {"departments": [self._department_dict(row) for row in departments], "services": [self._service_catalog_dict(row) for row in services]}

    def get_department(self, property_id: str, department_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM departments WHERE property_id=? AND department_id=?",
                (property_id, department_id),
            ).fetchone()
        return self._department_dict(row) if row else None

    def get_service(self, property_id: str, service_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM service_catalog WHERE property_id=? AND service_id=?",
                (property_id, service_id),
            ).fetchone()
        return self._service_catalog_dict(row) if row else None

    def get_service_request(self, property_id: str, request_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM service_requests WHERE property_id=? AND request_id=?",
                (property_id, request_id),
            ).fetchone()
        return self._service_dict(row) if row else None

    def recommendations(self, property_id: str, guest: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM recommendations WHERE property_id=?"
        params: tuple[Any, ...] = (property_id,)
        if guest:
            query += " AND enabled=1"
        query += " ORDER BY name"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._recommendation_dict(row) for row in rows]

    def upsert_facility_profile(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("live_status") or "open")
        if status not in FACILITY_STATUSES:
            raise ValueError("Invalid facility status.")
        now = _now()
        facility_id = str(payload.get("facility_id") or _id("facp"))
        if "policies" in payload:
            policies = payload["policies"]
            if not isinstance(policies, list) or len(policies) > 8:
                raise ValueError("Facility policies must be a list of at most 8 items.")
            if any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 240 for item in policies):
                raise ValueError("Facility policies must contain 1 to 240 characters.")
            policies_json = _json([item.strip() for item in policies])
        else:
            policies_json = None
        images = payload.get("images", [])
        if not isinstance(images, list) or len(images) > 12:
            raise ValueError("Facility images must be a list of at most 12 URLs.")
        safe_images: list[str] = []
        for image in images:
            if not isinstance(image, str) or not image.strip() or len(image.strip()) > 500:
                raise ValueError("Facility image URLs must contain 1 to 500 characters.")
            image = image.strip()
            if "\\" in image or any(ord(char) < 32 or ord(char) == 127 for char in image):
                raise ValueError("Facility image URLs must use HTTPS or a safe same-origin path.")
            if image.startswith("/"):
                if image.startswith("//"):
                    raise ValueError("Facility image URLs must use HTTPS or a safe same-origin path.")
            else:
                parsed_image = urlsplit(image)
                try:
                    parsed_image.port
                except ValueError:
                    raise ValueError("Facility image URLs must use HTTPS or a safe same-origin path.") from None
                if parsed_image.scheme != "https" or not parsed_image.hostname or parsed_image.username or parsed_image.password:
                    raise ValueError("Facility image URLs must use HTTPS or a safe same-origin path.")
            safe_images.append(image)
        record = {
            "facility_id": facility_id,
            "property_id": property_id,
            "zone_id": payload.get("zone_id"),
            "building_id": payload.get("building_id"),
            "floor_id": payload.get("floor_id"),
            "name": _clean(payload.get("name"), 160),
            "facility_type": _clean(payload.get("facility_type") or "amenity", 80),
            "opening_hours": _json(payload.get("opening_hours") or {}),
            "description": _clean(payload.get("description"), 1000),
            "images": _json(safe_images),
            "capacity": payload.get("capacity"),
            "booking_supported": 1 if payload.get("booking_supported") else 0,
            "live_status": status,
            "status_note": _clean(payload.get("status_note"), 240),
            "updated_at": now,
            "created_at": now,
        }
        metadata = {
            "facility_id": facility_id,
            "property_id": property_id,
            "location": _clean(payload.get("location"), 240),
            "policies": policies_json or _json([]),
        }
        if not record["name"]:
            raise ValueError("Facility name is required.")
        if "location" in payload and (not isinstance(payload["location"], str) or len(payload["location"].strip()) > 240):
            raise ValueError("Facility location must be text up to 240 characters.")
        if "opening_hours" in payload:
            opening_hours = payload["opening_hours"]
            if not isinstance(opening_hours, dict) or len(opening_hours) > 14:
                raise ValueError("Facility hours must be an object with at most 14 periods.")
            if any(
                not isinstance(period, str) or len(period) > 24
                or not isinstance(value, str) or len(value) > 160
                for period, value in opening_hours.items()
            ):
                raise ValueError("Facility hours must use short text labels and values.")
        with self._connect() as db:
            existing = db.execute("SELECT * FROM facility_profiles WHERE property_id=? AND facility_id=?", (property_id, facility_id)).fetchone()
            if existing is None and db.execute(
                "SELECT 1 FROM facility_profiles WHERE facility_id=?", (facility_id,),
            ).fetchone():
                raise ValueError("Facility identifier is unavailable.")
            existing_metadata = db.execute(
                "SELECT location,policies FROM facility_metadata WHERE property_id=? AND facility_id=?",
                (property_id, facility_id),
            ).fetchone()
            if existing:
                record["created_at"] = existing["created_at"]
                for field in (
                    "zone_id", "building_id", "floor_id", "facility_type", "opening_hours", "description",
                    "images", "capacity", "booking_supported", "live_status", "status_note",
                ):
                    if field not in payload:
                        record[field] = existing[field]
                if existing_metadata:
                    if "location" not in payload:
                        metadata["location"] = existing_metadata["location"]
                    if policies_json is None:
                        metadata["policies"] = existing_metadata["policies"]
                db.execute(
                    """UPDATE facility_profiles SET zone_id=:zone_id,building_id=:building_id,floor_id=:floor_id,
                    name=:name,facility_type=:facility_type,opening_hours=:opening_hours,description=:description,
                    images=:images,capacity=:capacity,booking_supported=:booking_supported,live_status=:live_status,
                    status_note=:status_note,updated_at=:updated_at WHERE property_id=:property_id AND facility_id=:facility_id""",
                    record,
                )
            else:
                db.execute(
                    """INSERT INTO facility_profiles
                    (facility_id,property_id,zone_id,building_id,floor_id,name,facility_type,opening_hours,
                    description,images,capacity,booking_supported,live_status,status_note,updated_at,created_at) VALUES
                    (:facility_id,:property_id,:zone_id,:building_id,:floor_id,:name,:facility_type,:opening_hours,
                    :description,:images,:capacity,:booking_supported,:live_status,:status_note,:updated_at,:created_at)""",
                    record,
                )
            metadata.update({"facility_id": facility_id, "property_id": property_id})
            db.execute(
                """INSERT INTO facility_metadata (facility_id,property_id,location,policies)
                VALUES (:facility_id,:property_id,:location,:policies)
                ON CONFLICT(facility_id) DO UPDATE SET
                property_id=excluded.property_id,location=excluded.location,policies=excluded.policies""",
                metadata,
            )
        record["location"] = metadata["location"]
        record["policies"] = metadata["policies"]
        return self._facility_dict(record)

    def delete_facility_profile(self, property_id: str, facility_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM facility_profiles WHERE property_id=? AND facility_id=?",
                (property_id, facility_id),
            )
        return cursor.rowcount > 0

    def create_restaurant(
        self,
        property_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
        restaurant_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        status = str(payload.get("status") or "open")
        if status not in RESTAURANT_STATUSES:
            raise ValueError("Invalid restaurant status.")
        if payload.get("restaurant_id"):
            raise ValueError("Restaurant IDs are generated by the server.")
        facility_id = str(payload.get("facility_id") or "").strip() or None
        if facility_id:
            self._require_owned("facility_profiles", "facility_id", facility_id, property_id)
        capacity = payload.get("capacity")
        if capacity is not None and (not isinstance(capacity, int) or not 1 <= capacity <= 100000):
            raise ValueError("Restaurant capacity must be between 1 and 100000.")
        external_url = self._external_reservation_url(payload.get("external_reservation_url"))
        record = {
            "restaurant_id": restaurant_id or _id("rest"),
            "property_id": property_id,
            "facility_id": facility_id,
            "name": _clean(payload.get("name"), 160),
            "location": _clean(payload.get("location"), 240),
            "opening_hours": _json(payload.get("opening_hours") or {}),
            "meal_periods": _json(list(payload.get("meal_periods") or [])[:12]),
            "reservation_available": 1 if payload.get("reservation_available") else 0,
            "description": _clean(payload.get("description"), 1000),
            "status": status,
            "cuisine": _clean(payload.get("cuisine"), 120),
            "dress_code": _clean(payload.get("dress_code"), 120),
            "capacity": capacity,
            "phone_extension": _clean(payload.get("phone_extension"), 80),
            "external_reservation_url": external_url,
            "contact_details": _json(self._contact_details(payload.get("contact_details"))),
            "images": _json(self._image_urls(payload.get("images"))),
            "internal_notes": _clean(payload.get("internal_notes"), 2000),
            "guest_notes": _clean(payload.get("guest_notes"), 1000),
            "archived": 1 if status == "archived" else 0,
            "updated_at": now,
            "created_at": now,
        }
        if not record["name"]:
            raise ValueError("Restaurant name is required.")
        with self._connect() as db:
            db.execute(
                """INSERT INTO restaurants
                (restaurant_id,property_id,facility_id,name,location,opening_hours,meal_periods,
                 reservation_available,description,status,cuisine,dress_code,capacity,phone_extension,
                 external_reservation_url,contact_details,images,internal_notes,guest_notes,archived,updated_at,created_at)
                VALUES
                (:restaurant_id,:property_id,:facility_id,:name,:location,:opening_hours,:meal_periods,
                 :reservation_available,:description,:status,:cuisine,:dress_code,:capacity,:phone_extension,
                 :external_reservation_url,:contact_details,:images,:internal_notes,:guest_notes,:archived,:updated_at,:created_at)""",
                record,
            )
            self._record_restaurant_audit(db, property_id, record["restaurant_id"], actor_user_id, "restaurant", record["restaurant_id"], "created")
        return self._restaurant_dict(record)

    def update_restaurant(self, property_id: str, restaurant_id: str, payload: dict[str, Any], actor_user_id: str | None = None) -> dict[str, Any]:
        existing = self.get_restaurant(property_id, restaurant_id)
        if not existing:
            raise KeyError("Restaurant not found.")
        data = {**existing, **payload}
        hours_changed = (
            existing.get("opening_hours") != (data.get("opening_hours") or {})
            or existing.get("meal_periods") != list(data.get("meal_periods") or [])
        )
        status = str(data.get("status") or "open")
        if status not in RESTAURANT_STATUSES:
            raise ValueError("Invalid restaurant status.")
        facility_id = str(data.get("facility_id") or "").strip() or None
        if facility_id:
            self._require_owned("facility_profiles", "facility_id", facility_id, property_id)
        capacity = data.get("capacity")
        if capacity is not None and (not isinstance(capacity, int) or not 1 <= capacity <= 100000):
            raise ValueError("Restaurant capacity must be between 1 and 100000.")
        record = {
            "property_id": property_id,
            "restaurant_id": restaurant_id,
            "facility_id": facility_id,
            "name": _clean(data.get("name"), 160),
            "location": _clean(data.get("location"), 240),
            "opening_hours": _json(data.get("opening_hours") or {}),
            "meal_periods": _json(list(data.get("meal_periods") or [])[:12]),
            "reservation_available": 1 if data.get("reservation_available") else 0,
            "description": _clean(data.get("description"), 1000),
            "status": status,
            "cuisine": _clean(data.get("cuisine"), 120),
            "dress_code": _clean(data.get("dress_code"), 120),
            "capacity": capacity,
            "phone_extension": _clean(data.get("phone_extension"), 80),
            "external_reservation_url": self._external_reservation_url(data.get("external_reservation_url")),
            "contact_details": _json(self._contact_details(data.get("contact_details"))),
            "images": _json(self._image_urls(data.get("images"))),
            "internal_notes": _clean(data.get("internal_notes"), 2000),
            "guest_notes": _clean(data.get("guest_notes"), 1000),
            "archived": 1 if status == "archived" else 0,
            "updated_at": _now(),
        }
        if not record["name"]:
            raise ValueError("Restaurant name is required.")
        with self._connect() as db:
            db.execute(
                """UPDATE restaurants SET facility_id=:facility_id,name=:name,location=:location,
                opening_hours=:opening_hours,meal_periods=:meal_periods,reservation_available=:reservation_available,
                description=:description,status=:status,cuisine=:cuisine,dress_code=:dress_code,capacity=:capacity,
                phone_extension=:phone_extension,external_reservation_url=:external_reservation_url,
                contact_details=:contact_details,images=:images,internal_notes=:internal_notes,guest_notes=:guest_notes,
                archived=:archived,updated_at=:updated_at
                WHERE property_id=:property_id AND restaurant_id=:restaurant_id""",
                record,
            )
            self._record_restaurant_audit(db, property_id, restaurant_id, actor_user_id, "restaurant", restaurant_id, "updated")
            if hours_changed:
                self._record_restaurant_audit(db, property_id, restaurant_id, actor_user_id, "restaurant", restaurant_id, "hours_changed")
        return self.get_restaurant(property_id, restaurant_id) or {}

    def get_restaurant(self, property_id: str, restaurant_id: str, *, guest: bool = False) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM restaurants WHERE property_id=? AND restaurant_id=?",
                (property_id, restaurant_id),
            ).fetchone()
        return self._restaurant_dict(row, guest=guest) if row else None

    def delete_restaurant(self, property_id: str, restaurant_id: str) -> bool:
        return self.archive_restaurant(property_id, restaurant_id)

    def archive_restaurant(self, property_id: str, restaurant_id: str, actor_user_id: str | None = None) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE restaurants SET status='archived',archived=1,updated_at=? WHERE property_id=? AND restaurant_id=? AND archived=0",
                (_now(), property_id, restaurant_id),
            )
            if cursor.rowcount:
                self._record_restaurant_audit(db, property_id, restaurant_id, actor_user_id, "restaurant", restaurant_id, "archived")
        return cursor.rowcount > 0

    @staticmethod
    def _external_reservation_url(value: Any) -> str:
        url = _clean(value, 500)
        if not url:
            return ""
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise ValueError("Reservation URL must be a valid HTTPS URL.") from exc
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Reservation URL must be a valid HTTPS URL.")
        return url

    @staticmethod
    def _image_urls(values: Any) -> list[str]:
        if values is None:
            return []
        if not isinstance(values, list):
            raise ValueError("Restaurant images must be a list of URLs.")
        result: list[str] = []
        for value in values[:20]:
            url = _clean(value, 500)
            if not url:
                continue
            if url.startswith("/") and not url.startswith("//"):
                result.append(url)
                continue
            try:
                parsed = urlsplit(url)
            except ValueError as exc:
                raise ValueError("Restaurant images must use HTTPS URLs or same-origin paths.") from exc
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Restaurant images must use HTTPS URLs or same-origin paths.")
            result.append(url)
        return result

    @staticmethod
    def _image_url(value: Any) -> str:
        url = _clean(value, 500)
        if not url:
            return ""
        return HospitalityStore._image_urls([url])[0]

    @staticmethod
    def _contact_details(value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("Restaurant contact details must be an object.")
        email = _clean(value.get("email"), 254).lower()
        if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
            raise ValueError("Restaurant contact email is invalid.")
        website = HospitalityStore._external_reservation_url(value.get("website"))
        phone = _clean(value.get("phone"), 80)
        return {key: item for key, item in {"email": email, "phone": phone, "website": website}.items() if item}

    @staticmethod
    def _record_restaurant_audit(
        db: sqlite3.Connection,
        property_id: str,
        restaurant_id: str | None,
        actor_user_id: str | None,
        resource_type: str,
        resource_id: str,
        action: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        db.execute(
            """INSERT INTO restaurant_audit_events
            (event_id,property_id,restaurant_id,actor_user_id,resource_type,resource_id,action,metadata,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (_id("audit"), property_id, restaurant_id, actor_user_id, resource_type, resource_id, action, _json(metadata or {}), _now()),
        )

    def create_menu(
        self,
        property_id: str,
        restaurant_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        restaurant = self.get_restaurant(property_id, restaurant_id)
        if not restaurant or restaurant["archived"] or restaurant["status"] in {"disabled", "archived"}:
            raise KeyError("Restaurant not found.")
        now = _now()
        status = "pending_approval"
        record = {
            "menu_id": _id("menu"),
            "property_id": property_id,
            "restaurant_id": restaurant_id,
            "name": _clean(payload.get("name"), 160),
            "meal_period": _clean(payload.get("meal_period") or "all_day", 80),
            "active": 1 if payload.get("active", True) else 0,
            "workflow_status": status,
            "created_by": actor_user_id,
            "updated_by": actor_user_id,
            "approved_by": None,
            "published_by": None,
            "approved_at": None,
            "published_at": None,
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Menu name is required.")
        with self._connect() as db:
            db.execute(
                """INSERT INTO menus
                (menu_id,property_id,restaurant_id,name,meal_period,active,workflow_status,created_by,updated_by,
                 approved_by,published_by,approved_at,published_at,created_at,updated_at)
                VALUES
                (:menu_id,:property_id,:restaurant_id,:name,:meal_period,:active,:workflow_status,:created_by,:updated_by,
                 :approved_by,:published_by,:approved_at,:published_at,:created_at,:updated_at)""",
                record,
            )
            self._record_restaurant_audit(db, property_id, restaurant_id, actor_user_id, "menu", record["menu_id"], "created", {"status": status})
        return self._menu_dict(record)

    def restaurant_menus(self, property_id: str, restaurant_id: str, *, guest: bool = False) -> list[dict[str, Any]]:
        self._require_owned("restaurants", "restaurant_id", restaurant_id, property_id)
        clause = "AND workflow_status='published' AND active=1" if guest else ""
        with self._connect() as db:
            menus = db.execute(
                # B608 rationale: clause is one of two fixed literals selected by the guest flag; values remain bound.
                f"SELECT * FROM menus WHERE property_id=? AND restaurant_id=? {clause} ORDER BY meal_period,name",  # nosec B608
                (property_id, restaurant_id),
            ).fetchall()
            result = []
            for menu in menus:
                items = db.execute(
                    "SELECT * FROM menu_items WHERE property_id=? AND menu_id=? ORDER BY name",
                    (property_id, menu["menu_id"]),
                ).fetchall()
                result.append({**self._menu_dict(menu), "items": [self._menu_item_dict(item) for item in items if not guest or item["available"]]})
        return result

    def update_menu(
        self, property_id: str, menu_id: str, payload: dict[str, Any], *, actor_user_id: str | None = None
    ) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            row = db.execute("SELECT * FROM menus WHERE property_id=? AND menu_id=?", (property_id, menu_id)).fetchone()
            if not row:
                raise KeyError("Menu not found.")
            name = _clean(payload.get("name", row["name"]), 160)
            meal_period = _clean(payload.get("meal_period", row["meal_period"]), 80)
            if not name:
                raise ValueError("Menu name is required.")
            db.execute(
                """UPDATE menus SET name=?,meal_period=?,active=0,workflow_status='pending_approval',
                updated_by=?,approved_by=NULL,approved_at=NULL,published_by=NULL,published_at=NULL,updated_at=?
                WHERE property_id=? AND menu_id=?""",
                (name, meal_period, actor_user_id, now, property_id, menu_id),
            )
            self._record_restaurant_audit(db, property_id, row["restaurant_id"], actor_user_id, "menu", menu_id, "updated", {"status": "pending_approval"})
            result = db.execute("SELECT * FROM menus WHERE property_id=? AND menu_id=?", (property_id, menu_id)).fetchone()
        return self._menu_dict(result)

    def restaurant_id_for_menu(self, property_id: str, menu_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT restaurant_id FROM menus WHERE property_id=? AND menu_id=?",
                (property_id, menu_id),
            ).fetchone()
        return row["restaurant_id"] if row else None

    def restaurant_id_for_menu_item(self, property_id: str, item_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT m.restaurant_id FROM menu_items i
                JOIN menus m ON m.property_id=i.property_id AND m.menu_id=i.menu_id
                WHERE i.property_id=? AND i.item_id=?""",
                (property_id, item_id),
            ).fetchone()
        return row["restaurant_id"] if row else None

    def restaurant_id_for_promotion(self, property_id: str, promotion_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT restaurant_id FROM restaurant_promotions WHERE property_id=? AND promotion_id=?",
                (property_id, promotion_id),
            ).fetchone()
        return row["restaurant_id"] if row else None

    def restaurant_analytics(self, property_id: str, restaurant_id: str, start_at: int | None = None, end_at: int | None = None) -> dict[str, Any]:
        self._require_owned("restaurants", "restaurant_id", restaurant_id, property_id)
        time_clause = ""
        time_params: tuple[int, ...] = ()
        if start_at is not None and end_at is not None:
            time_clause = " AND created_at>=? AND created_at<=?"
            time_params = (start_at, end_at)
        message_time_clause = ""
        message_time_params: tuple[int, ...] = ()
        if start_at is not None and end_at is not None:
            message_time_clause = " AND m.created_at>=? AND m.created_at<=?"
            message_time_params = (start_at, end_at)
        with self._connect() as db:
            # B608 rationale: time_clause is a fixed pair of predicates; timestamps are bound below.
            conversations = db.execute(
                f"""SELECT COUNT(*) AS total,
                SUM(CASE WHEN state IN ('waiting_for_staff','assigned') THEN 1 ELSE 0 END) AS waiting,
                SUM(CASE WHEN state='human_active' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN state IN ('resolved','returned_to_ai') THEN 1 ELSE 0 END) AS completed
                FROM conversation_state WHERE property_id=? AND restaurant_id=?{time_clause}""",  # nosec B608
                (property_id, restaurant_id, *time_params),
            ).fetchone()
            # B608 rationale: message_time_clause is a fixed pair of predicates; timestamps are bound below.
            messages = db.execute(
                f"""SELECT COUNT(*) FROM conversation_messages m
                JOIN conversation_state cs ON cs.property_id=m.property_id AND cs.session_id=m.session_id
                WHERE cs.property_id=? AND cs.restaurant_id=?{message_time_clause}""",  # nosec B608
                (property_id, restaurant_id, *message_time_params),
            ).fetchone()[0]
            menus = db.execute(
                "SELECT COUNT(*) FROM menus WHERE property_id=? AND restaurant_id=?",
                (property_id, restaurant_id),
            ).fetchone()[0]
            promotions = db.execute(
                "SELECT COUNT(*) FROM restaurant_promotions WHERE property_id=? AND restaurant_id=?",
                (property_id, restaurant_id),
            ).fetchone()[0]
        return {
            "conversations": int(conversations["total"] or 0),
            "waiting_for_staff": int(conversations["waiting"] or 0),
            "human_active": int(conversations["active"] or 0),
            "completed": int(conversations["completed"] or 0),
            "messages": int(messages or 0),
            "menus": int(menus or 0),
            "promotions": int(promotions or 0),
        }

    def approve_menu(self, property_id: str, menu_id: str, actor_user_id: str) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            db.execute(
                """UPDATE menus SET workflow_status='approved',approved_by=?,approved_at=?,updated_by=?,updated_at=?
                WHERE property_id=? AND menu_id=? AND workflow_status IN ('pending_approval','draft','approved')""",
                (actor_user_id, now, actor_user_id, now, property_id, menu_id),
            )
            row = db.execute("SELECT * FROM menus WHERE property_id=? AND menu_id=?", (property_id, menu_id)).fetchone()
            if row:
                self._record_restaurant_audit(db, property_id, row["restaurant_id"], actor_user_id, "menu", menu_id, "approved")
        if not row:
            raise KeyError("Menu not found.")
        return self._menu_dict(row)

    def publish_menu(self, property_id: str, menu_id: str, actor_user_id: str) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            db.execute(
                """UPDATE menus SET workflow_status='published',active=1,published_by=?,published_at=?,updated_by=?,updated_at=?
                WHERE property_id=? AND menu_id=? AND workflow_status IN ('approved','published')""",
                (actor_user_id, now, actor_user_id, now, property_id, menu_id),
            )
            row = db.execute("SELECT * FROM menus WHERE property_id=? AND menu_id=?", (property_id, menu_id)).fetchone()
            if row and row["workflow_status"] == "published":
                self._record_restaurant_audit(db, property_id, row["restaurant_id"], actor_user_id, "menu", menu_id, "published")
        if not row or row["workflow_status"] != "published":
            raise ValueError("Only an approved menu can be published.")
        return self._menu_dict(row)

    def create_menu_item(
        self,
        property_id: str,
        menu_id: str,
        payload: dict[str, Any],
        *,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_owned("menus", "menu_id", menu_id, property_id)
        now = _now()
        record = {
            "item_id": _id("item"),
            "property_id": property_id,
            "menu_id": menu_id,
            "name": _clean(payload.get("name"), 160),
            "description": _clean(payload.get("description"), 1000),
            "price": _clean(payload.get("price"), 40),
            "image_url": self._image_url(payload.get("image_url")),
            "ingredients": _json(list(payload.get("ingredients") or [])[:40]),
            "allergens": _json(list(payload.get("allergens") or [])[:40]),
            "dietary_tags": _json(list(payload.get("dietary_tags") or [])[:40]),
            "available": 1 if payload.get("available", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Menu item name is required.")
        with self._connect() as db:
            db.execute(
                """INSERT INTO menu_items VALUES
                (:item_id,:property_id,:menu_id,:name,:description,:price,:image_url,:ingredients,
                :allergens,:dietary_tags,:available,:created_at,:updated_at)""",
                record,
            )
            parent = db.execute("SELECT restaurant_id,workflow_status FROM menus WHERE property_id=? AND menu_id=?", (property_id, menu_id)).fetchone()
            db.execute(
                "UPDATE menus SET workflow_status='pending_approval',active=0,updated_by=?,updated_at=? WHERE property_id=? AND menu_id=?",
                (actor_user_id, now, property_id, menu_id),
            )
            self._record_restaurant_audit(db, property_id, parent["restaurant_id"], actor_user_id, "menu_item", record["item_id"], "created")
        return self._menu_item_dict(record)

    def update_menu_item(
        self, property_id: str, item_id: str, payload: dict[str, Any], *, actor_user_id: str | None = None
    ) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM menu_items WHERE property_id=? AND item_id=?",
                (property_id, item_id),
            ).fetchone()
            if not row:
                raise KeyError("Menu item not found.")
            parent = db.execute(
                "SELECT * FROM menus WHERE property_id=? AND menu_id=?",
                (property_id, row["menu_id"]),
            ).fetchone()
            if not parent or not db.execute(
                "SELECT 1 FROM restaurants WHERE property_id=? AND restaurant_id=?",
                (property_id, parent["restaurant_id"]),
            ).fetchone():
                raise KeyError("Menu item not found.")
            record = {
                "name": _clean(payload.get("name", row["name"]), 160),
                "description": _clean(payload.get("description", row["description"]), 1000),
                "price": _clean(payload.get("price", row["price"]), 40),
                "image_url": self._image_url(payload.get("image_url", row["image_url"])),
                "ingredients": _json(payload.get("ingredients", _load(row["ingredients"]))),
                "allergens": _json(payload.get("allergens", _load(row["allergens"]))),
                "dietary_tags": _json(payload.get("dietary_tags", _load(row["dietary_tags"]))),
                "available": 1 if payload.get("available", bool(row["available"])) else 0,
                "updated_at": _now(),
                "property_id": property_id,
                "item_id": item_id,
                "menu_id": row["menu_id"],
                "restaurant_id": parent["restaurant_id"],
            }
            if not record["name"]:
                raise ValueError("Menu item name is required.")
            db.execute(
                """UPDATE menu_items SET name=:name,description=:description,price=:price,image_url=:image_url,
                ingredients=:ingredients,allergens=:allergens,dietary_tags=:dietary_tags,available=:available,
                updated_at=:updated_at WHERE property_id=:property_id AND menu_id=:menu_id AND item_id=:item_id""",
                record,
            )
            db.execute(
                """UPDATE menus SET workflow_status='pending_approval',active=0,updated_by=?,updated_at=?
                WHERE property_id=? AND menu_id=?""",
                (actor_user_id, record["updated_at"], property_id, row["menu_id"]),
            )
            self._record_restaurant_audit(db, property_id, parent["restaurant_id"], actor_user_id, "menu_item", item_id, "updated")
            result = db.execute("SELECT * FROM menu_items WHERE property_id=? AND item_id=?", (property_id, item_id)).fetchone()
        return self._menu_item_dict(result)

    def create_promotion(
        self, property_id: str, restaurant_id: str, payload: dict[str, Any], *, actor_user_id: str | None = None
    ) -> dict[str, Any]:
        self._require_owned("restaurants", "restaurant_id", restaurant_id, property_id)
        now = _now()
        starts_at = self._optional_timestamp(payload.get("starts_at"))
        ends_at = self._optional_timestamp(payload.get("ends_at"))
        if starts_at is not None and ends_at is not None and ends_at < starts_at:
            raise ValueError("Promotion end time must be after its start time.")
        title = _clean(payload.get("title"), 180)
        if not title:
            raise ValueError("Promotion title is required.")
        record = {
            "promotion_id": _id("promo"),
            "property_id": property_id,
            "restaurant_id": restaurant_id,
            "title": title,
            "description": _clean(payload.get("description"), 1000),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "status": "pending_approval",
            "created_by": actor_user_id,
            "updated_by": actor_user_id,
            "approved_by": None,
            "published_by": None,
            "approved_at": None,
            "published_at": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO restaurant_promotions
                (promotion_id,property_id,restaurant_id,title,description,starts_at,ends_at,status,created_by,updated_by,
                 approved_by,published_by,approved_at,published_at,created_at,updated_at)
                VALUES
                (:promotion_id,:property_id,:restaurant_id,:title,:description,:starts_at,:ends_at,:status,:created_by,:updated_by,
                 :approved_by,:published_by,:approved_at,:published_at,:created_at,:updated_at)""",
                record,
            )
            self._record_restaurant_audit(db, property_id, restaurant_id, actor_user_id, "promotion", record["promotion_id"], "created")
        return self._promotion_dict(record)

    def update_promotion(
        self, property_id: str, promotion_id: str, payload: dict[str, Any], *, actor_user_id: str | None = None
    ) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM restaurant_promotions WHERE property_id=? AND promotion_id=?",
                (property_id, promotion_id),
            ).fetchone()
            if not row:
                raise KeyError("Promotion not found.")
            starts_at = self._optional_timestamp(payload.get("starts_at", row["starts_at"]))
            ends_at = self._optional_timestamp(payload.get("ends_at", row["ends_at"]))
            if starts_at is not None and ends_at is not None and ends_at < starts_at:
                raise ValueError("Promotion end time must be after its start time.")
            title = _clean(payload.get("title", row["title"]), 180)
            if not title:
                raise ValueError("Promotion title is required.")
            db.execute(
                """UPDATE restaurant_promotions SET title=?,description=?,starts_at=?,ends_at=?,status='pending_approval',
                updated_by=?,approved_by=NULL,approved_at=NULL,published_by=NULL,published_at=NULL,updated_at=?
                WHERE property_id=? AND promotion_id=?""",
                (title, _clean(payload.get("description", row["description"]), 1000), starts_at, ends_at, actor_user_id, now, property_id, promotion_id),
            )
            self._record_restaurant_audit(db, property_id, row["restaurant_id"], actor_user_id, "promotion", promotion_id, "updated", {"status": "pending_approval"})
            result = db.execute(
                "SELECT * FROM restaurant_promotions WHERE property_id=? AND promotion_id=?",
                (property_id, promotion_id),
            ).fetchone()
        return self._promotion_dict(result)

    def restaurant_promotions(
        self, property_id: str, restaurant_id: str, *, guest: bool = False
    ) -> list[dict[str, Any]]:
        self._require_owned("restaurants", "restaurant_id", restaurant_id, property_id)
        now = _now()
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM restaurant_promotions
                WHERE property_id=? AND restaurant_id=?
                  AND (?=0 OR (status='published' AND (starts_at IS NULL OR starts_at<=?) AND (ends_at IS NULL OR ends_at>=?)))
                ORDER BY starts_at,title""",
                (property_id, restaurant_id, 1 if guest else 0, now, now),
            ).fetchall()
        return [self._promotion_dict(row, guest=guest) for row in rows]

    def approve_promotion(self, property_id: str, promotion_id: str, actor_user_id: str) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            db.execute(
                """UPDATE restaurant_promotions SET status='approved',approved_by=?,approved_at=?,updated_by=?,updated_at=?
                WHERE property_id=? AND promotion_id=? AND status IN ('draft','pending_approval','approved')""",
                (actor_user_id, now, actor_user_id, now, property_id, promotion_id),
            )
            row = db.execute(
                "SELECT * FROM restaurant_promotions WHERE property_id=? AND promotion_id=?",
                (property_id, promotion_id),
            ).fetchone()
            if row and row["status"] == "approved":
                self._record_restaurant_audit(db, property_id, row["restaurant_id"], actor_user_id, "promotion", promotion_id, "approved")
        if not row or row["status"] != "approved":
            raise KeyError("Promotion not found or cannot be approved.")
        return self._promotion_dict(row)

    def publish_promotion(self, property_id: str, promotion_id: str, actor_user_id: str) -> dict[str, Any]:
        now = _now()
        with self._connect() as db:
            db.execute(
                """UPDATE restaurant_promotions SET status='published',published_by=?,published_at=?,updated_by=?,updated_at=?
                WHERE property_id=? AND promotion_id=? AND status IN ('approved','published')""",
                (actor_user_id, now, actor_user_id, now, property_id, promotion_id),
            )
            row = db.execute(
                "SELECT * FROM restaurant_promotions WHERE property_id=? AND promotion_id=?",
                (property_id, promotion_id),
            ).fetchone()
            if row and row["status"] == "published":
                self._record_restaurant_audit(db, property_id, row["restaurant_id"], actor_user_id, "promotion", promotion_id, "published")
        if not row or row["status"] != "published":
            raise ValueError("Only an approved promotion can be published.")
        return self._promotion_dict(row)

    @staticmethod
    def _optional_timestamp(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Promotion dates must be Unix timestamps.") from exc
        if number < 0:
            raise ValueError("Promotion dates must be Unix timestamps.")
        return number

    def create_event(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        record = {
            "event_id": _id("event"),
            "property_id": property_id,
            "title": _clean(payload.get("title"), 180),
            "starts_at": int(payload.get("starts_at") or now),
            "ends_at": payload.get("ends_at"),
            "facility_id": payload.get("facility_id"),
            "zone_id": payload.get("zone_id"),
            "audience": _clean(payload.get("audience") or "all_guests", 120),
            "capacity": payload.get("capacity"),
            "description": _clean(payload.get("description"), 1000),
            "notification_timing": _json(payload.get("notification_timing") or {}),
            "cta": _clean(payload.get("cta"), 200),
            "status": _clean(payload.get("status") or "scheduled", 80),
            "created_at": now,
            "updated_at": now,
        }
        if not record["title"]:
            raise ValueError("Event title is required.")
        with self._connect() as db:
            db.execute(
                """INSERT INTO hotel_events VALUES
                (:event_id,:property_id,:title,:starts_at,:ends_at,:facility_id,:zone_id,:audience,
                :capacity,:description,:notification_timing,:cta,:status,:created_at,:updated_at)""",
                record,
            )
        return self._event_dict(record)

    def create_service_request(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        service_id = payload.get("service_id") or None
        client_request_id = _clean(payload.get("client_request_id"), 120) or None
        sla = payload.get("sla_target_seconds")
        record: dict[str, Any]
        with self._connect() as db:
            if client_request_id:
                # Serialize lookup and insert so simultaneous retries return the
                # existing ticket instead of racing into the unique constraint.
                db.execute("BEGIN IMMEDIATE")
                stay_id = payload.get("stay_id")
                if stay_id is None:
                    lookup_query = "SELECT * FROM service_requests WHERE property_id=? AND stay_id IS NULL AND client_request_id=?"
                    lookup_values = (property_id, client_request_id)
                else:
                    lookup_query = "SELECT * FROM service_requests WHERE property_id=? AND stay_id=? AND client_request_id=?"
                    lookup_values = (property_id, stay_id, client_request_id)
                existing = db.execute(lookup_query, lookup_values).fetchone()
                if existing:
                    return {**self._service_dict(existing), "idempotent_replay": True}
            catalog_service = None
            if service_id:
                catalog_service = db.execute(
                    "SELECT s.*, d.name AS department_name FROM service_catalog s LEFT JOIN departments d ON d.department_id=s.department_id AND d.property_id=s.property_id WHERE s.property_id=? AND s.service_id=? AND s.enabled=1 AND s.archived=0",
                    (property_id, service_id),
                ).fetchone()
            if not catalog_service:
                if service_id:
                    raise ValueError("The selected service is not available.")
            if sla is None and catalog_service:
                sla = int(catalog_service["sla_minutes"]) * 60
            due_at = now + int(sla) if sla else None
            record = {
                "request_id": _id("req"),
                "property_id": property_id,
                "service_id": service_id,
                "stay_id": payload.get("stay_id"),
                "room": _clean(payload.get("room"), 80) or None,
                "request_type": _clean((catalog_service["name"] if catalog_service else payload.get("request_type")) or "general", 80),
                "description": _clean(payload.get("description"), 1000),
                "priority": _clean(payload.get("priority") or "normal", 40),
                "department": _clean((catalog_service["department_name"] if catalog_service else payload.get("department")) or "front_desk", 80),
                "assigned_to": _clean(payload.get("assigned_to"), 160) or None,
                "notes": _json(list(payload.get("notes") or [])[:100]),
                "status": "new",
                "sla_target_seconds": sla,
                "due_at": due_at,
                "completed_at": None,
                "created_at": now,
                "updated_at": now,
                "client_request_id": client_request_id,
            }
            if not record["description"]:
                raise ValueError("Service request description is required.")
            db.execute(
                """INSERT INTO service_requests
                (request_id,property_id,stay_id,room,request_type,description,priority,department,status,
                 sla_target_seconds,due_at,completed_at,created_at,updated_at,service_id,assigned_to,notes,client_request_id)
                VALUES (:request_id,:property_id,:stay_id,:room,:request_type,:description,:priority,:department,
                :status,:sla_target_seconds,:due_at,:completed_at,:created_at,:updated_at,:service_id,:assigned_to,:notes,:client_request_id)""",
                record,
            )
            self._record_request_history(db, property_id, record["request_id"], "created", {"status": "new"}, now)
        return self._service_dict(record)

    def update_service_status(self, property_id: str, request_id: str, status: str) -> dict[str, Any]:
        if status not in SERVICE_STATUSES:
            raise ValueError("Invalid service request status.")
        now = _now()
        completed = now if status == "completed" else None
        with self._connect() as db:
            db.execute(
                "UPDATE service_requests SET status=?, completed_at=COALESCE(?,completed_at), updated_at=? WHERE property_id=? AND request_id=?",
                (status, completed, now, property_id, request_id),
            )
            row = db.execute("SELECT * FROM service_requests WHERE property_id=? AND request_id=?", (property_id, request_id)).fetchone()
            if row:
                self._record_request_history(db, property_id, request_id, "status_changed", {"status": status}, now)
        if not row:
            raise KeyError("Service request not found.")
        return self._service_dict(row)

    def cancel_guest_service_request(self, property_id: str, request_id: str, stay_ids: set[str]) -> dict[str, Any]:
        """Cancel only a new request owned by one of the caller's stay handles."""
        ids = sorted(value for value in stay_ids if value)
        if not ids:
            raise KeyError("Service request not found.")
        marks = ",".join("?" for _ in ids)
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                # B608 rationale: marks contains only generated placeholders; stay IDs are bound below.
                f"SELECT * FROM service_requests WHERE property_id=? AND request_id=? AND stay_id IN ({marks})",  # nosec B608
                (property_id, request_id, *ids),
            ).fetchone()
            if not row:
                raise KeyError("Service request not found.")
            if row["status"] != "new":
                raise ValueError("This request can no longer be cancelled online. Please contact hotel staff.")
            db.execute(
                "UPDATE service_requests SET status='cancelled',completed_at=?,updated_at=? WHERE property_id=? AND request_id=? AND status='new'",
                (now, now, property_id, request_id),
            )
            self._record_request_history(db, property_id, request_id, "guest_cancelled", {"status": "cancelled"}, now)
            updated = db.execute("SELECT * FROM service_requests WHERE property_id=? AND request_id=?", (property_id, request_id)).fetchone()
        return self._service_dict(updated)

    def update_service_request(self, property_id: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"priority", "department", "assigned_to"}
        updates = {key: _clean(payload.get(key), 160) for key in allowed if key in payload}
        note = _clean(payload.get("note"), 1000)
        now = _now()
        with self._connect() as db:
            row = db.execute("SELECT * FROM service_requests WHERE property_id=? AND request_id=?", (property_id, request_id)).fetchone()
            if not row:
                raise KeyError("Service request not found.")
            notes = _load(row["notes"] or "[]")
            if note:
                notes.append({"text": note, "created_at": now})
                updates["notes"] = _json(notes[-100:])
            if updates:
                allowed_columns = {"priority", "department", "assigned_to", "notes"}
                if not set(updates) <= allowed_columns:
                    raise ValueError("Unsupported service request update field.")
                clause = ",".join(f"{key}=?" for key in updates)
                # B608 rationale: update columns are checked against a fixed allowlist; all values are bound.
                db.execute(f"UPDATE service_requests SET {clause},updated_at=? WHERE property_id=? AND request_id=?", (*updates.values(), now, property_id, request_id))  # nosec B608
                self._record_request_history(db, property_id, request_id, "updated", {key: value for key, value in updates.items() if key != "notes"} | ({"note": note} if note else {}), now)
            row = db.execute("SELECT * FROM service_requests WHERE property_id=? AND request_id=?", (property_id, request_id)).fetchone()
        return self._service_dict(row)

    def request_history(self, property_id: str, request_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM service_request_history WHERE property_id=? AND request_id=? ORDER BY created_at,history_id", (property_id, request_id)).fetchall()
        return [{**dict(row), "detail": _load(row["detail"])} for row in rows]

    def _record_request_history(self, db: sqlite3.Connection, property_id: str, request_id: str, action: str, detail: dict[str, Any], created_at: int) -> None:
        db.execute("INSERT INTO service_request_history VALUES (?,?,?,?,?,?)", (_id("hist"), property_id, request_id, action, _json(detail), created_at))

    def add_feedback(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        resolution = str(payload.get("resolution") or "")
        if resolution not in {"yes", "partially", "no"}:
            raise ValueError("Feedback resolution must be yes, partially, or no.")
        record = {
            "feedback_id": _id("fb"),
            "property_id": property_id,
            "request_id": payload.get("request_id"),
            "stay_id": payload.get("stay_id"),
            "resolution": resolution,
            "rating": payload.get("rating"),
            "comment": _clean(payload.get("comment"), 1000),
            "created_at": _now(),
        }
        with self._connect() as db:
            db.execute("INSERT INTO guest_feedback VALUES (:feedback_id,:property_id,:request_id,:stay_id,:resolution,:rating,:comment,:created_at)", record)
        return record

    def create_notification_rule(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        category = str(payload.get("category") or "operational")
        if category not in NOTIFICATION_CATEGORIES:
            raise ValueError("Invalid notification category.")
        now = _now()
        record = {
            "rule_id": _id("rule"),
            "property_id": property_id,
            "name": _clean(payload.get("name"), 160),
            "category": category,
            "trigger_type": _clean(payload.get("trigger_type") or "manual", 80),
            "enabled": 1 if payload.get("enabled", True) else 0,
            "policy": _json(payload.get("policy") or {}),
            "template": _clean(payload.get("template"), 1000),
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Notification rule name is required.")
        with self._connect() as db:
            db.execute("INSERT INTO notification_rules VALUES (:rule_id,:property_id,:name,:category,:trigger_type,:enabled,:policy,:template,:created_at,:updated_at)", record)
        return self._notification_rule_dict(record)

    def evaluate_notification(
        self,
        property_id: str,
        rule_id: str,
        stay_id: str | None,
        verified_payload: dict[str, Any],
        guest_preferences: dict[str, Any] | None = None,
        current_zone_id: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            row = db.execute("SELECT * FROM notification_rules WHERE property_id=? AND rule_id=?", (property_id, rule_id)).fetchone()
            property_row = (
                db.execute("SELECT timezone FROM properties WHERE property_id=?", (property_id,)).fetchone()
                if table_exists(db, "properties") else None
            )
        if not row:
            raise KeyError("Notification rule not found.")
        rule = self._notification_rule_dict(row)
        allowed, reason = self._notification_allowed(
            rule, verified_payload, guest_preferences or {}, current_zone_id, moment,
            property_timezone=property_row["timezone"] if property_row else "UTC",
        )
        if allowed:
            policy = rule.get("policy") or {}
            scheduled_at = policy.get("scheduled_at", policy.get("not_before"))
            if scheduled_at is not None:
                try:
                    if moment < int(scheduled_at):
                        allowed, reason = False, "scheduled_for_later"
                except (TypeError, ValueError, OverflowError):
                    allowed, reason = False, "invalid_schedule"
            limit = policy.get("frequency_limit")
            if isinstance(limit, dict):
                max_per_window = limit.get("max")
                window_seconds = limit.get("window_seconds", 86400)
            else:
                max_per_window = limit if limit is not None else policy.get("max_per_stay")
                window_seconds = policy.get("frequency_window_seconds", 86400)
            if allowed and max_per_window is not None and stay_id:
                try:
                    maximum = int(max_per_window)
                    window = int(window_seconds)
                    if isinstance(max_per_window, bool) or not 1 <= maximum <= 100 or not 60 <= window <= 31 * 86400:
                        raise ValueError
                except (TypeError, ValueError, OverflowError):
                    allowed, reason = False, "invalid_frequency_limit"
                else:
                    with self._connect() as db:
                        sent_in_window = db.execute(
                            """SELECT COUNT(*) AS count FROM notifications
                               WHERE property_id=? AND stay_id=? AND category=?
                                 AND status='eligible' AND created_at>?""",
                            (property_id, stay_id, rule["category"], moment - window),
                        ).fetchone()
                    if int(sent_in_window["count"] or 0) >= maximum:
                        allowed, reason = False, "frequency_limit"
        notification = {
            "notification_id": _id("notif"),
            "property_id": property_id,
            "rule_id": rule_id,
            "stay_id": stay_id,
            "category": rule["category"],
            "verified_payload": _json(verified_payload),
            "ai_wording": _clean(verified_payload.get("wording") or rule["template"], 1000),
            "status": "eligible" if allowed else "suppressed",
            "created_at": moment,
            "updated_at": moment,
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO notifications VALUES
                (:notification_id,:property_id,:rule_id,:stay_id,:category,:verified_payload,:ai_wording,:status,:created_at,:updated_at)""",
                notification,
            )
            db.execute(
                "INSERT INTO notification_deliveries VALUES (?,?,?,?,?,?,?,?,?,?)",
                (_id("deliv"), property_id, notification["notification_id"], stay_id, "eligible" if allowed else "suppressed", reason, None, None, None, moment),
            )
        result = self._notification_dict(notification)
        result["allowed"] = allowed
        result["reason"] = reason
        return result

    def get_guest_notification_preferences(self, property_id: str, stay_id: str) -> dict[str, bool]:
        """Return property/stay preferences, including conservative optional defaults."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        preferences = dict(GUEST_NOTIFICATION_DEFAULT_PREFERENCES)
        with self._connect() as db:
            rows = db.execute(
                "SELECT category,enabled FROM guest_notification_preferences WHERE property_id=? AND stay_id=?",
                (property_id, stay_id),
            )
            for row in rows:
                preferences[row["category"]] = bool(row["enabled"])
        return preferences

    def set_guest_notification_preference(
        self,
        property_id: str,
        stay_id: str,
        category: str,
        enabled: bool,
        *,
        now: int | None = None,
    ) -> dict[str, bool]:
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        if category not in NOTIFICATION_CATEGORIES:
            raise ValueError("Invalid notification category.")
        if not isinstance(enabled, bool):
            raise ValueError("Notification preference must be a boolean.")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            db.execute(
                """INSERT INTO guest_notification_preferences
                   (property_id,stay_id,category,enabled,created_at,updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(property_id,stay_id,category) DO UPDATE SET
                     enabled=excluded.enabled,updated_at=excluded.updated_at""",
                (property_id, stay_id, category, int(enabled), moment, moment),
            )
        return self.get_guest_notification_preferences(property_id, stay_id)

    def create_guest_inbox_notification(
        self,
        property_id: str,
        stay_id: str,
        event_id: str,
        category: str,
        title: str,
        body: str,
        *,
        expires_at: int | None = None,
        scheduled_at: int | None = None,
        timezone_name: str = "UTC",
        quiet_hours: dict[str, Any] | None = None,
        send_window: dict[str, Any] | None = None,
        max_per_window: int | None = None,
        frequency_window_seconds: int | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Queue one in-app inbox item, deduplicated within its property and stay.

        A queued record is only persisted work. It is not considered sent or
        delivered until the dispatch worker and guest client acknowledge those
        separate steps.
        """
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        event_id = self._guest_event_id(event_id)
        if category not in NOTIFICATION_CATEGORIES:
            raise ValueError("Invalid notification category.")
        clean_title = _clean(title, 160)
        clean_body = _clean(body, 2000)
        if not clean_title or not clean_body:
            raise ValueError("Notification title and body are required.")
        moment = _now() if now is None else int(now)
        expiry = int(expires_at) if expires_at is not None else None
        if expiry is not None and expiry <= moment:
            raise ValueError("Notification expiry must be in the future.")
        schedule = self._validate_guest_delivery_schedule(
            timezone_name,
            quiet_hours=quiet_hours,
            send_window=send_window,
            max_per_window=max_per_window,
            frequency_window_seconds=frequency_window_seconds,
        )
        available_at = int(scheduled_at) if scheduled_at is not None else moment
        if available_at < 0:
            raise ValueError("Notification schedule must be a valid timestamp.")

        with self._connect() as db:
            suppressed = db.execute(
                """SELECT 1 FROM guest_notification_suppressions
                   WHERE property_id=? AND stay_id=? AND event_id=?""",
                (property_id, stay_id, event_id),
            ).fetchone()
            if suppressed:
                return {
                    "notification_id": "", "property_id": property_id,
                    "stay_id": stay_id, "event_id": event_id, "category": category,
                    "title": "", "body": "", "status": "expired", "created": False,
                    "suppressed": True,
                }
            existing = db.execute(
                """SELECT * FROM guest_inbox_notifications
                   WHERE property_id=? AND stay_id=? AND event_id=?""",
                (property_id, stay_id, event_id),
            ).fetchone()
            if existing:
                result = self._guest_inbox_notification_dict(existing)
                result["created"] = False
                return result

            preference = db.execute(
                """SELECT enabled FROM guest_notification_preferences
                   WHERE property_id=? AND stay_id=? AND category=?""",
                (property_id, stay_id, category),
            ).fetchone()
            enabled = (
                bool(preference["enabled"])
                if preference
                else GUEST_NOTIFICATION_DEFAULT_PREFERENCES[category]
            )
            if not enabled:
                raise PermissionError("Guest has not opted in to this notification category.")

            notification_id = _id("ginbox")
            cursor = db.execute(
                """INSERT INTO guest_inbox_notifications
                   (notification_id,property_id,stay_id,event_id,category,title,body,status,
                    created_at,updated_at,expires_at,dispatch_status,attempt_count,next_attempt_at,
                    scheduled_at,timezone_name,quiet_hours,send_window,max_per_window,frequency_window_seconds)
                   VALUES (?,?,?,?,?,?,?,'queued',?,?,?,'queued',0,?,?,?,?,?,?,?)
                   ON CONFLICT(property_id,stay_id,event_id) DO NOTHING""",
                (
                    notification_id, property_id, stay_id, event_id, category,
                    clean_title, clean_body, moment, moment, expiry,
                    available_at, available_at, schedule["timezone_name"],
                    _json(schedule["quiet_hours"]), _json(schedule["send_window"]),
                    schedule["max_per_window"], schedule["frequency_window_seconds"],
                ),
            )
            row = db.execute(
                """SELECT * FROM guest_inbox_notifications
                   WHERE property_id=? AND stay_id=? AND event_id=?""",
                (property_id, stay_id, event_id),
            ).fetchone()
            if row is None:  # Defensive: a successful insert must be visible in its transaction.
                raise RuntimeError("Notification could not be queued.")
            result = self._guest_inbox_notification_dict(row)
            result["created"] = cursor.rowcount == 1
            return result

    def claim_guest_inbox_notifications(
        self,
        *,
        limit: int = 20,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        now: int | None = None,
        property_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Atomically claim due inbox jobs for one dispatcher worker.

        Claims are leased and have unique tokens. A crashed worker's lease can
        be reclaimed after ``lease_seconds``; every claim consumes one bounded
        attempt so repeatedly crashing workers eventually dead-letter the row.
        """
        moment = _now() if now is None else int(now)
        if isinstance(limit, bool) or not 1 <= int(limit) <= MAX_GUEST_NOTIFICATION_CLAIM_BATCH:
            raise ValueError(f"Claim limit must be between 1 and {MAX_GUEST_NOTIFICATION_CLAIM_BATCH}.")
        if isinstance(lease_seconds, bool) or not 5 <= int(lease_seconds) <= 3600:
            raise ValueError("Claim lease must be between 5 and 3600 seconds.")
        if isinstance(max_attempts, bool) or not 1 <= int(max_attempts) <= MAX_GUEST_NOTIFICATION_ATTEMPTS:
            raise ValueError(f"Maximum attempts must be between 1 and {MAX_GUEST_NOTIFICATION_ATTEMPTS}.")
        scoped_property = self._guest_scope_value(property_id, "Property id") if property_id is not None else None
        lease_cutoff = moment - int(lease_seconds)
        claimed: list[dict[str, Any]] = []

        with self._connect() as db:
            # SQLite serializes claim transactions here. On PostgreSQL the
            # subsequent compare-and-set UPDATE prevents a concurrent worker
            # from returning an item claimed by another transaction.
            db.execute("BEGIN IMMEDIATE")
            self._expire_guest_inbox_rows(
                db, moment, property_id=scoped_property,
            )
            if scoped_property is None:
                candidates = db.execute(
                    """SELECT * FROM guest_inbox_notifications
                        WHERE (expires_at IS NULL OR expires_at>?)
                          AND ((dispatch_status IN ('queued','retry_wait') AND next_attempt_at<=?)
                               OR (dispatch_status='sending' AND claimed_at<=?))
                        ORDER BY next_attempt_at,created_at,notification_id LIMIT ?""",
                    (moment, moment, lease_cutoff, int(limit) * 10),
                ).fetchall()
            else:
                candidates = db.execute(
                    """SELECT * FROM guest_inbox_notifications
                        WHERE (expires_at IS NULL OR expires_at>?)
                          AND ((dispatch_status IN ('queued','retry_wait') AND next_attempt_at<=?)
                               OR (dispatch_status='sending' AND claimed_at<=?))
                          AND property_id=?
                        ORDER BY next_attempt_at,created_at,notification_id LIMIT ?""",
                    (moment, moment, lease_cutoff, scoped_property, int(limit) * 10),
                ).fetchall()

            for row in candidates:
                if len(claimed) >= int(limit):
                    break
                attempts = int(row["attempt_count"] or 0)
                stale_claim = row["dispatch_status"] == "sending"
                if attempts >= int(max_attempts):
                    if stale_claim:
                        db.execute(
                            """UPDATE guest_inbox_notifications
                               SET status='failed',dispatch_status='dead_letter',
                                   failed_at=?,dead_letter_at=?,failure_reason=?,
                                   claim_token=NULL,claimed_at=NULL,updated_at=?
                               WHERE notification_id=? AND property_id=? AND stay_id=?
                                 AND dispatch_status='sending' AND claim_token=?""",
                            (
                                moment, moment, "Delivery claim expired after maximum attempts.",
                                moment, row["notification_id"], row["property_id"],
                                row["stay_id"], row["claim_token"],
                            ),
                        )
                    else:
                        db.execute(
                            """UPDATE guest_inbox_notifications
                               SET status='failed',dispatch_status='dead_letter',
                                   failed_at=?,dead_letter_at=?,failure_reason=?,updated_at=?
                               WHERE notification_id=? AND property_id=? AND stay_id=?
                                 AND dispatch_status IN ('queued','retry_wait')""",
                            (
                                moment, moment, "Delivery attempts exhausted.", moment,
                                row["notification_id"], row["property_id"], row["stay_id"],
                            ),
                        )
                    continue

                if not self._guest_delivery_schedule_allows(moment, row):
                    next_time = self._next_guest_delivery_time(moment, row)
                    due_time = next_time if next_time is not None else moment + 24 * 60 * 60
                    self._release_guest_delivery_claim(db, row, due_time, moment)
                    continue

                max_per_window = row["max_per_window"]
                window = row["frequency_window_seconds"]
                if max_per_window is not None and window is not None:
                    # A per-stay/category write lock makes the following count
                    # and claim serializable on PostgreSQL as well as SQLite.
                    db.execute(
                        """INSERT INTO guest_notification_frequency_locks
                           (property_id,stay_id,category,touched_at) VALUES (?,?,?,?)
                           ON CONFLICT(property_id,stay_id,category) DO UPDATE SET
                             touched_at=excluded.touched_at""",
                        (row["property_id"], row["stay_id"], row["category"], moment),
                    )
                    threshold = moment - int(window)
                    active_count = db.execute(
                        """SELECT COUNT(*) AS count,MIN(COALESCE(sent_at,claimed_at,created_at)) AS oldest
                           FROM guest_inbox_notifications
                           WHERE property_id=? AND stay_id=? AND category=?
                             AND notification_id<>? AND dispatch_status IN ('sending','sent')
                             AND COALESCE(sent_at,claimed_at,created_at)>?""",
                        (
                            row["property_id"], row["stay_id"], row["category"],
                            row["notification_id"], threshold,
                        ),
                    ).fetchone()
                    if int(active_count["count"] or 0) >= int(max_per_window):
                        next_time = int(active_count["oldest"] or moment) + int(window)
                        self._release_guest_delivery_claim(db, row, max(moment + 1, next_time), moment)
                        continue

                claim_token = uuid.uuid4().hex
                if stale_claim:
                    update = db.execute(
                        """UPDATE guest_inbox_notifications
                           SET dispatch_status='sending',attempt_count=attempt_count+1,
                               claim_token=?,claimed_at=?,updated_at=?
                           WHERE notification_id=? AND property_id=? AND stay_id=?
                             AND dispatch_status='sending' AND claim_token=? AND claimed_at<=?""",
                        (
                            claim_token, moment, moment, row["notification_id"],
                            row["property_id"], row["stay_id"], row["claim_token"], lease_cutoff,
                        ),
                    )
                else:
                    update = db.execute(
                        """UPDATE guest_inbox_notifications
                           SET dispatch_status='sending',attempt_count=attempt_count+1,
                               claim_token=?,claimed_at=?,updated_at=?
                           WHERE notification_id=? AND property_id=? AND stay_id=?
                             AND dispatch_status IN ('queued','retry_wait') AND next_attempt_at<=?""",
                        (
                            claim_token, moment, moment, row["notification_id"],
                            row["property_id"], row["stay_id"], moment,
                        ),
                    )
                if update.rowcount != 1:
                    continue
                fresh = db.execute(
                    "SELECT * FROM guest_inbox_notifications WHERE notification_id=? AND claim_token=?",
                    (row["notification_id"], claim_token),
                ).fetchone()
                if fresh is not None:
                    claimed.append(self._guest_inbox_notification_dict(fresh))
            return claimed

    def retry_guest_inbox_notification(
        self,
        property_id: str,
        stay_id: str,
        notification_id: str,
        claim_token: str,
        reason: str,
        *,
        max_attempts: int = 5,
        base_backoff_seconds: int = 30,
        max_backoff_seconds: int = 3600,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Release one claimed item for bounded exponential retry or dead-letter."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        notification_id = self._guest_scope_value(notification_id, "Notification id")
        claim_token = self._guest_scope_value(claim_token, "Claim token")
        failure_reason = _clean(reason, 240)
        if not failure_reason:
            raise ValueError("Failure reason is required.")
        if isinstance(max_attempts, bool) or not 1 <= int(max_attempts) <= MAX_GUEST_NOTIFICATION_ATTEMPTS:
            raise ValueError(f"Maximum attempts must be between 1 and {MAX_GUEST_NOTIFICATION_ATTEMPTS}.")
        if isinstance(base_backoff_seconds, bool) or not 1 <= int(base_backoff_seconds) <= 3600:
            raise ValueError("Base backoff must be between 1 and 3600 seconds.")
        if isinstance(max_backoff_seconds, bool) or not int(base_backoff_seconds) <= int(max_backoff_seconds) <= 86400:
            raise ValueError("Maximum backoff must be between the base delay and 86400 seconds.")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._load_guest_inbox_row(db, property_id, stay_id, notification_id, moment)
            if row["dispatch_status"] != "sending" or row["claim_token"] != claim_token:
                raise ValueError("Notification claim is no longer active.")
            attempts = int(row["attempt_count"] or 0)
            if attempts >= int(max_attempts):
                db.execute(
                    """UPDATE guest_inbox_notifications
                       SET status='failed',dispatch_status='dead_letter',failure_reason=?,
                           failed_at=?,dead_letter_at=?,claim_token=NULL,claimed_at=NULL,updated_at=?
                       WHERE notification_id=? AND property_id=? AND stay_id=?
                         AND dispatch_status='sending' AND claim_token=?""",
                    (
                        failure_reason, moment, moment, moment, notification_id,
                        property_id, stay_id, claim_token,
                    ),
                )
            else:
                delay = min(int(base_backoff_seconds) * (2 ** max(attempts - 1, 0)), int(max_backoff_seconds))
                db.execute(
                    """UPDATE guest_inbox_notifications
                       SET status='queued',dispatch_status='retry_wait',failure_reason=?,
                           next_attempt_at=?,claim_token=NULL,claimed_at=NULL,updated_at=?
                       WHERE notification_id=? AND property_id=? AND stay_id=?
                         AND dispatch_status='sending' AND claim_token=?""",
                    (
                        failure_reason, moment + delay, moment, notification_id,
                        property_id, stay_id, claim_token,
                    ),
                )
            updated = self._load_guest_inbox_row(db, property_id, stay_id, notification_id, moment)
            return self._guest_inbox_notification_dict(updated)

    def list_guest_notification_dead_letters(
        self,
        property_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Expose terminal dispatch failures to property-scoped operator tooling."""
        property_id = self._guest_scope_value(property_id, "Property id")
        if isinstance(limit, bool) or not 1 <= int(limit) <= 500:
            raise ValueError("Dead-letter limit must be between 1 and 500.")
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM guest_inbox_notifications
                   WHERE property_id=? AND dispatch_status='dead_letter'
                   ORDER BY dead_letter_at DESC,notification_id LIMIT ?""",
                (property_id, int(limit)),
            ).fetchall()
        return [self._guest_inbox_notification_dict(row) for row in rows]

    def list_guest_notification_history(
        self,
        property_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return property-scoped delivery state without guest message bodies."""
        property_id = self._guest_scope_value(property_id, "Property id")
        if isinstance(limit, bool) or not 1 <= int(limit) <= 500:
            raise ValueError("Notification history limit must be between 1 and 500.")
        with self._connect() as db:
            rows = db.execute(
                """SELECT notification_id,stay_id,event_id,category,status,created_at,
                          sent_at,delivered_at,read_at,failed_at,expired_at,dispatch_status,
                          attempt_count,next_attempt_at,failure_reason
                   FROM guest_inbox_notifications WHERE property_id=?
                   ORDER BY created_at DESC,notification_id LIMIT ?""",
                (property_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_guest_inbox_notification_sent(
        self,
        property_id: str,
        stay_id: str,
        notification_id: str,
        *,
        claim_token: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record that the in-app dispatcher handed the item to the guest inbox."""
        return self._transition_guest_inbox_notification(
            property_id, stay_id, notification_id, "sent", now=now, claim_token=claim_token
        )

    def acknowledge_guest_inbox_notification(
        self,
        property_id: str,
        stay_id: str,
        notification_id: str,
        action: str,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record guest-client evidence: receipt for ``delivered``, explicit open for ``read``.

        Listing an item is not an acknowledgment. ``delivered_at`` means the
        in-app client acknowledged receipt/rendering; ``read_at`` means that
        client explicitly marked the item read, not proof of human attention.
        """
        if action not in {"delivered", "read"}:
            raise ValueError("Acknowledgement must be 'delivered' or 'read'.")
        return self._transition_guest_inbox_notification(
            property_id, stay_id, notification_id, action, now=now
        )

    def fail_guest_inbox_notification(
        self,
        property_id: str,
        stay_id: str,
        notification_id: str,
        reason: str,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record a terminal in-app dispatch failure before client receipt."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        notification_id = self._guest_scope_value(notification_id, "Notification id")
        failure_reason = _clean(reason, 240)
        if not failure_reason:
            raise ValueError("Failure reason is required.")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            row = self._load_guest_inbox_row(db, property_id, stay_id, notification_id, moment)
            if row["status"] == "failed":
                return self._guest_inbox_notification_dict(row)
            if row["status"] not in {"queued", "sent"}:
                raise ValueError("Only queued or sent notifications can fail.")
            db.execute(
                """UPDATE guest_inbox_notifications
                   SET status='failed',dispatch_status='dead_letter',failure_reason=?,
                       failed_at=?,dead_letter_at=?,claim_token=NULL,claimed_at=NULL,updated_at=?
                   WHERE property_id=? AND stay_id=? AND notification_id=?
                     AND status IN ('queued','sent')""",
                (failure_reason, moment, moment, moment, property_id, stay_id, notification_id),
            )
            updated = self._load_guest_inbox_row(db, property_id, stay_id, notification_id, moment)
            if updated["status"] != "failed":
                raise ValueError("Notification changed state before failure was recorded.")
            return self._guest_inbox_notification_dict(updated)

    def list_guest_inbox_notifications(
        self,
        property_id: str,
        stay_id: str,
        *,
        now: int | None = None,
    ) -> list[dict[str, Any]]:
        """List inbox items for exactly one property/stay and expire stale items."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            self._expire_guest_inbox_rows(db, moment, property_id=property_id, stay_id=stay_id)
            return [
                self._guest_inbox_notification_dict(row)
                for row in db.execute(
                    """SELECT * FROM guest_inbox_notifications
                       WHERE property_id=? AND stay_id=?
                       ORDER BY created_at DESC,notification_id""",
                    (property_id, stay_id),
                )
            ]

    def expire_guest_inbox_notifications(
        self,
        *,
        now: int | None = None,
        property_id: str | None = None,
        stay_id: str | None = None,
    ) -> int:
        """Expire due records, optionally restricted to one guest property/stay."""
        if (property_id is None) != (stay_id is None):
            raise ValueError("Property and stay must be supplied together.")
        if property_id is not None:
            property_id = self._guest_scope_value(property_id, "Property id")
            stay_id = self._guest_scope_value(stay_id, "Stay id")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            return self._expire_guest_inbox_rows(
                db, moment, property_id=property_id, stay_id=stay_id
            )

    def expire_guest_inbox_for_stay(
        self,
        property_id: str,
        stay_id: str,
        *,
        now: int | None = None,
    ) -> int:
        """Close any pending or visible inbox items when a stay checks out."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            return db.execute(
                """UPDATE guest_inbox_notifications
                   SET status='expired',dispatch_status='expired',expired_at=?,
                       claim_token=NULL,claimed_at=NULL,updated_at=?
                   WHERE property_id=? AND stay_id=?
                     AND status IN ('queued','sent','delivered')""",
                (moment, moment, property_id, stay_id),
            ).rowcount

    def purge_guest_inbox_for_stay(self, property_id: str, stay_id: str) -> int:
        """Erase guest-linked notification content on checkout, including read items."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        with self._connect() as db:
            deleted = db.execute(
                "DELETE FROM guest_inbox_notifications WHERE property_id=? AND stay_id=?",
                (property_id, stay_id),
            ).rowcount
            db.execute(
                "DELETE FROM guest_notification_preferences WHERE property_id=? AND stay_id=?",
                (property_id, stay_id),
            )
            db.execute(
                "DELETE FROM guest_notification_frequency_locks WHERE property_id=? AND stay_id=?",
                (property_id, stay_id),
            )
            db.execute(
                "DELETE FROM guest_notification_suppressions WHERE property_id=? AND stay_id=?",
                (property_id, stay_id),
            )
            return deleted

    def purge_guest_inbox_category(self, property_id: str, stay_id: str, category: str) -> int:
        """Remove guest-linked content immediately after an opt-out."""
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        if category not in NOTIFICATION_CATEGORIES:
            raise ValueError("Invalid notification category.")
        with self._connect() as db:
            self._suppress_guest_inbox_events(db, property_id, stay_id, category, _now())
            return db.execute(
                "DELETE FROM guest_inbox_notifications WHERE property_id=? AND stay_id=? AND category=?",
                (property_id, stay_id, category),
            ).rowcount

    @staticmethod
    def _suppress_guest_inbox_events(db, property_id: str, stay_id: str, category: str, moment: int) -> None:
        event_ids = db.execute(
            """SELECT event_id FROM guest_inbox_notifications
               WHERE property_id=? AND stay_id=? AND category=?""",
            (property_id, stay_id, category),
        ).fetchall()
        for row in event_ids:
            db.execute(
                """INSERT INTO guest_notification_suppressions
                   (property_id,stay_id,event_id,category,suppressed_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(property_id,stay_id,event_id) DO NOTHING""",
                (property_id, stay_id, row["event_id"], category, moment),
            )

    def cleanup_guest_inbox_retention(self, *, now: int | None = None, retention_days: int = 7) -> int:
        """Delete checked-out inbox data and aged expired messages.

        Active-stay messages remain available unless their explicit expiry and
        configured retention period have both elapsed. Operational metrics
        retain only aggregate deletion counts, never guest identifiers.
        """
        if isinstance(retention_days, bool) or not 0 <= retention_days <= 365:
            raise ValueError("Notification retention days must be between 0 and 365.")
        moment = _now() if now is None else int(now)
        cutoff = moment - retention_days * 86400
        with self._connect() as db:
            if not table_exists(db, "concierge_stays"):
                # Some isolated deployments keep inbox tables without the
                # identity module. Explicit expiry remains enforceable there.
                return db.execute(
                    "DELETE FROM guest_inbox_notifications WHERE status='expired' AND expired_at IS NOT NULL AND expired_at<=?",
                    (cutoff,),
                ).rowcount
            deleted = db.execute(
                """DELETE FROM guest_inbox_notifications
                   WHERE EXISTS (
                       SELECT 1 FROM concierge_stays s
                       WHERE s.property_id=guest_inbox_notifications.property_id
                         AND s.stay_id=guest_inbox_notifications.stay_id
                         AND s.status!='active'
                   )
                   OR (status='expired' AND expired_at IS NOT NULL AND expired_at<=?)""",
                (cutoff,),
            ).rowcount
            if table_exists(db, "guest_privacy_consents") and table_exists(db, "guest_sessions"):
                optional_groups = db.execute(
                    """SELECT DISTINCT n.property_id,n.stay_id,n.category
                       FROM guest_inbox_notifications n
                       JOIN concierge_stays s
                         ON s.property_id=n.property_id AND s.stay_id=n.stay_id
                       WHERE s.status='active' AND n.category IN ('experience','promotional')"""
                ).fetchall()
                for group in optional_groups:
                    property_id = str(group["property_id"])
                    stay_id = str(group["stay_id"])
                    category = str(group["category"])
                    consent_name = "proactive_notifications" if category == "experience" else "promotional_messages"
                    preference = db.execute(
                        """SELECT enabled FROM guest_notification_preferences
                           WHERE property_id=? AND stay_id=? AND category=?""",
                        (property_id, stay_id, category),
                    ).fetchone()
                    enabled = (
                        bool(preference["enabled"])
                        if preference
                        else GUEST_NOTIFICATION_DEFAULT_PREFERENCES[category]
                    )
                    linked_sessions = db.execute(
                        """SELECT DISTINCT concierge_session_id FROM guest_sessions
                           WHERE property_id=? AND stay_id=? AND concierge_session_id IS NOT NULL""",
                        (property_id, stay_id),
                    ).fetchall()
                    session_ids = [str(row["concierge_session_id"]) for row in linked_sessions]
                    if session_ids:
                        placeholders = ",".join("?" for _ in session_ids)
                        consent_rows = db.execute(
                            f"""SELECT granted FROM guest_privacy_consents
                                WHERE property_id=? AND category=? AND session_id IN ({placeholders})""",  # nosec B608 - only placeholder tokens are generated.
                            (property_id, consent_name, *session_ids),
                        ).fetchall()
                    else:
                        consent_rows = []
                    if enabled and any(bool(row["granted"]) for row in consent_rows):
                        continue
                    self._suppress_guest_inbox_events(db, property_id, stay_id, category, moment)
                    deleted += db.execute(
                        "DELETE FROM guest_inbox_notifications WHERE property_id=? AND stay_id=? AND category=?",
                        (property_id, stay_id, category),
                    ).rowcount
            for table in ("guest_notification_preferences", "guest_notification_frequency_locks"):
                db.execute(
                    f"""DELETE FROM {table} WHERE EXISTS (
                        SELECT 1 FROM concierge_stays s
                        WHERE s.property_id={table}.property_id AND s.stay_id={table}.stay_id
                          AND s.status!='active'
                    )""",  # nosec B608 - table names are the fixed tuple above.
                    (),
                )
            db.execute(
                """DELETE FROM guest_notification_suppressions WHERE NOT EXISTS (
                       SELECT 1 FROM concierge_stays s
                       WHERE s.property_id=guest_notification_suppressions.property_id
                         AND s.stay_id=guest_notification_suppressions.stay_id
                         AND s.status='active'
                   )"""
            )
            return deleted

    def _transition_guest_inbox_notification(
        self,
        property_id: str,
        stay_id: str,
        notification_id: str,
        target_status: str,
        *,
        claim_token: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        property_id = self._guest_scope_value(property_id, "Property id")
        stay_id = self._guest_scope_value(stay_id, "Stay id")
        notification_id = self._guest_scope_value(notification_id, "Notification id")
        moment = _now() if now is None else int(now)
        with self._connect() as db:
            row = self._load_guest_inbox_row(db, property_id, stay_id, notification_id, moment)
            current = row["status"]
            if target_status == "sent" and current == "sent":
                if claim_token and row["claim_token"] not in {None, claim_token}:
                    raise ValueError("Notification claim is no longer active.")
                return self._guest_inbox_notification_dict(row)
            if target_status == "delivered" and current in {"delivered", "read"}:
                return self._guest_inbox_notification_dict(row)
            if target_status == "read" and current == "read":
                return self._guest_inbox_notification_dict(row)

            transitions = {"sent": "queued", "delivered": "sent", "read": "delivered"}
            expected = transitions[target_status]
            if current != expected:
                raise ValueError(f"Cannot transition notification from {current} to {target_status}.")

            if target_status == "sent":
                if row["dispatch_status"] == "sending":
                    if not claim_token or row["claim_token"] != claim_token:
                        raise ValueError("Notification claim is no longer active.")
                    updated_count = db.execute(
                        """UPDATE guest_inbox_notifications
                           SET status='sent',dispatch_status='sent',sent_at=?,updated_at=?,
                               claim_token=NULL,claimed_at=NULL
                           WHERE property_id=? AND stay_id=? AND notification_id=?
                             AND status='queued' AND dispatch_status='sending' AND claim_token=?""",
                        (moment, moment, property_id, stay_id, notification_id, claim_token),
                    ).rowcount
                elif row["dispatch_status"] == "queued" and claim_token is None:
                    if int(row["next_attempt_at"] or 0) > moment:
                        raise ValueError("Notification is not due for dispatch yet.")
                    if not self._guest_delivery_schedule_allows(moment, row):
                        raise ValueError("Notification is outside its configured delivery window.")
                    if row["max_per_window"] is not None:
                        raise ValueError("Rate-limited notifications must be atomically claimed before sending.")
                    updated_count = db.execute(
                        """UPDATE guest_inbox_notifications
                           SET status='sent',dispatch_status='sent',sent_at=?,updated_at=?
                           WHERE property_id=? AND stay_id=? AND notification_id=?
                             AND status='queued' AND dispatch_status='queued' AND next_attempt_at<=?""",
                        (moment, moment, property_id, stay_id, notification_id, moment),
                    ).rowcount
                else:
                    raise ValueError("Notification claim is no longer active.")
                if updated_count != 1:
                    raise ValueError("Notification changed state before it was sent.")
            elif target_status == "delivered":
                db.execute(
                    """UPDATE guest_inbox_notifications SET status='delivered',delivered_at=?,updated_at=?
                       WHERE property_id=? AND stay_id=? AND notification_id=? AND status='sent'""",
                    (moment, moment, property_id, stay_id, notification_id),
                )
            else:
                db.execute(
                    """UPDATE guest_inbox_notifications SET status='read',read_at=?,updated_at=?
                       WHERE property_id=? AND stay_id=? AND notification_id=? AND status='delivered'""",
                    (moment, moment, property_id, stay_id, notification_id),
                )
            updated = self._load_guest_inbox_row(db, property_id, stay_id, notification_id, moment)
            if updated["status"] != target_status and not (
                target_status == "delivered" and updated["status"] == "read"
            ):
                raise ValueError("Notification changed state before acknowledgement was recorded.")
            return self._guest_inbox_notification_dict(updated)

    def _load_guest_inbox_row(
        self,
        db: sqlite3.Connection,
        property_id: str,
        stay_id: str,
        notification_id: str,
        moment: int,
    ) -> sqlite3.Row:
        row = db.execute(
            """SELECT * FROM guest_inbox_notifications
               WHERE property_id=? AND stay_id=? AND notification_id=?""",
            (property_id, stay_id, notification_id),
        ).fetchone()
        if row is None:
            raise KeyError("Notification not found.")
        if row["status"] in {"queued", "sent", "delivered"} and row["expires_at"] is not None and row["expires_at"] <= moment:
            self._expire_guest_inbox_rows(
                db, moment, property_id=property_id, stay_id=stay_id,
                notification_id=notification_id,
            )
            row = db.execute(
                """SELECT * FROM guest_inbox_notifications
                   WHERE property_id=? AND stay_id=? AND notification_id=?""",
                (property_id, stay_id, notification_id),
            ).fetchone()
        return row

    @staticmethod
    def _expire_guest_inbox_rows(
        db: sqlite3.Connection,
        moment: int,
        *,
        property_id: str | None = None,
        stay_id: str | None = None,
        notification_id: str | None = None,
    ) -> int:
        sql = """UPDATE guest_inbox_notifications
                 SET status='expired',dispatch_status='expired',expired_at=?,
                     claim_token=NULL,claimed_at=NULL,updated_at=?
                 WHERE status IN ('queued','sent','delivered')
                   AND expires_at IS NOT NULL AND expires_at<=?"""
        params: list[Any] = [moment, moment, moment]
        if property_id is not None:
            sql += " AND property_id=? AND stay_id=?"
            params.extend((property_id, stay_id))
        if notification_id is not None:
            sql += " AND notification_id=?"
            params.append(notification_id)
        return db.execute(sql, params).rowcount

    @staticmethod
    def _guest_scope_value(value: Any, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > 240:
            raise ValueError(f"{label} is required and must be at most 240 characters.")
        return normalized

    @staticmethod
    def _clock_minutes(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{label} must be an hour or HH:MM value.")
        if isinstance(value, int):
            if not 0 <= value <= 23:
                raise ValueError(f"{label} hour must be between 0 and 23.")
            return value * 60
        if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
            raise ValueError(f"{label} must be an hour or HH:MM value.")
        try:
            hour, minute = (int(part) for part in value.split(":"))
        except ValueError as exc:
            raise ValueError(f"{label} must be an hour or HH:MM value.") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError(f"{label} must be a valid time of day.")
        return hour * 60 + minute

    @classmethod
    def _normalize_daily_interval(cls, value: dict[str, Any] | None, label: str) -> dict[str, int]:
        if value is None or value == {}:
            return {}
        if not isinstance(value, dict) or "start" not in value or "end" not in value:
            raise ValueError(f"{label} requires start and end values.")
        return {
            "start": cls._clock_minutes(value["start"], f"{label} start"),
            "end": cls._clock_minutes(value["end"], f"{label} end"),
        }

    @classmethod
    def _validate_guest_delivery_schedule(
        cls,
        timezone_name: str,
        *,
        quiet_hours: dict[str, Any] | None,
        send_window: dict[str, Any] | None,
        max_per_window: int | None,
        frequency_window_seconds: int | None,
    ) -> dict[str, Any]:
        zone_name = str(timezone_name or "UTC").strip()
        try:
            ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Notification timezone must be a valid IANA timezone.") from exc
        quiet = cls._normalize_daily_interval(quiet_hours, "Quiet hours")
        window = cls._normalize_daily_interval(send_window, "Send window")
        if window and window["start"] == window["end"]:
            raise ValueError("Send window start and end must differ.")
        if max_per_window is not None:
            if isinstance(max_per_window, bool) or not 1 <= int(max_per_window) <= 100:
                raise ValueError("Frequency limit must be between 1 and 100.")
            max_per_window = int(max_per_window)
        if frequency_window_seconds is not None:
            if isinstance(frequency_window_seconds, bool) or not 60 <= int(frequency_window_seconds) <= 31 * 86400:
                raise ValueError("Frequency window must be between 60 seconds and 31 days.")
            frequency_window_seconds = int(frequency_window_seconds)
        elif max_per_window is not None:
            frequency_window_seconds = 86400
        if max_per_window is None and frequency_window_seconds is not None:
            raise ValueError("A frequency limit is required when a frequency window is configured.")
        return {
            "timezone_name": zone_name,
            "quiet_hours": quiet,
            "send_window": window,
            "max_per_window": max_per_window,
            "frequency_window_seconds": frequency_window_seconds,
        }

    @staticmethod
    def _minute_in_interval(minute: int, interval: dict[str, Any], *, quiet: bool) -> bool:
        if not interval:
            return False
        start, end = int(interval["start"]), int(interval["end"])
        if start == end:
            return quiet
        inside = start <= minute < end if start < end else minute >= start or minute < end
        return inside

    @classmethod
    def _guest_delivery_schedule_allows(cls, moment: int, row: sqlite3.Row | dict[str, Any]) -> bool:
        zone = ZoneInfo(str(row["timezone_name"] or "UTC"))
        local = datetime.fromtimestamp(moment, timezone.utc).astimezone(zone)
        minute = local.hour * 60 + local.minute
        quiet = _load(row["quiet_hours"])
        window = _load(row["send_window"])
        if cls._minute_in_interval(minute, quiet, quiet=True):
            return False
        if window and not cls._minute_in_interval(minute, window, quiet=False):
            return False
        return True

    @classmethod
    def _next_guest_delivery_time(cls, moment: int, row: sqlite3.Row | dict[str, Any]) -> int | None:
        for offset in range(60, 48 * 60 * 60 + 1, 60):
            candidate = moment + offset
            if cls._guest_delivery_schedule_allows(candidate, row):
                return candidate
        return None

    @staticmethod
    def _release_guest_delivery_claim(db: sqlite3.Connection, row: sqlite3.Row | dict[str, Any], next_attempt_at: int, moment: int) -> None:
        # A queued row has no token; a stale sending row must still match its
        # lease. PostgreSQL does not accept a bound value with `IS ?`.
        params: list[Any] = [
            next_attempt_at, moment, row["notification_id"], row["property_id"],
            row["stay_id"], row["dispatch_status"],
        ]
        if row["claim_token"] is None:
            db.execute(
                """UPDATE guest_inbox_notifications
                   SET status='queued',dispatch_status='retry_wait',next_attempt_at=?,
                       claim_token=NULL,claimed_at=NULL,updated_at=?
                   WHERE notification_id=? AND property_id=? AND stay_id=? AND dispatch_status=?
                     AND claim_token IS NULL""",
                params,
            )
        else:
            db.execute(
                """UPDATE guest_inbox_notifications
                   SET status='queued',dispatch_status='retry_wait',next_attempt_at=?,
                       claim_token=NULL,claimed_at=NULL,updated_at=?
                   WHERE notification_id=? AND property_id=? AND stay_id=? AND dispatch_status=?
                     AND claim_token=?""",
                (*params, row["claim_token"]),
            )

    @staticmethod
    def _guest_event_id(value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > 180:
            raise ValueError("Event id is required and must be at most 180 characters.")
        return normalized

    @staticmethod
    def _guest_inbox_notification_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "notification_id": row["notification_id"],
            "property_id": row["property_id"],
            "stay_id": row["stay_id"],
            "event_id": row["event_id"],
            "category": row["category"],
            "title": row["title"],
            "body": row["body"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "sent_at": row["sent_at"],
            "delivered_at": row["delivered_at"],
            "read_at": row["read_at"],
            "failed_at": row["failed_at"],
            "expired_at": row["expired_at"],
            "failure_reason": row["failure_reason"],
            "expires_at": row["expires_at"],
            "dispatch_status": row["dispatch_status"],
            "attempt_count": row["attempt_count"],
            "next_attempt_at": row["next_attempt_at"],
            "claim_token": row["claim_token"],
            "claimed_at": row["claimed_at"],
            "dead_letter_at": row["dead_letter_at"],
            "scheduled_at": row["scheduled_at"],
            "timezone_name": row["timezone_name"],
            "max_per_window": row["max_per_window"],
            "frequency_window_seconds": row["frequency_window_seconds"],
        }

    def record_journey_event(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "journey_event_id": _id("journey"),
            "property_id": property_id,
            "stay_id": payload.get("stay_id"),
            "event_type": _clean(payload.get("event_type"), 120),
            "facility_id": payload.get("facility_id"),
            "zone_id": payload.get("zone_id"),
            "request_id": payload.get("request_id"),
            "metadata": _json(payload.get("metadata") or {}),
            "occurred_at": int(payload.get("occurred_at") or _now()),
        }
        if not record["event_type"]:
            raise ValueError("Journey event type is required.")
        with self._connect() as db:
            db.execute("INSERT INTO guest_journey_events VALUES (:journey_event_id,:property_id,:stay_id,:event_type,:facility_id,:zone_id,:request_id,:metadata,:occurred_at)", record)
        record["metadata"] = _load(record["metadata"])
        return record

    def overview(
        self,
        property_id: str,
        restaurant_ids: set[str] | None = None,
        department_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as db:
            restaurants = [
                self._restaurant_dict(row)
                for row in db.execute("SELECT * FROM restaurants WHERE property_id=? ORDER BY name", (property_id,))
            ]
            promotions = [
                self._promotion_dict(row)
                for row in db.execute("SELECT * FROM restaurant_promotions WHERE property_id=? ORDER BY created_at DESC", (property_id,))
            ]
            if restaurant_ids is not None:
                restaurants = [item for item in restaurants if item["restaurant_id"] in restaurant_ids]
                promotions = [item for item in promotions if item["restaurant_id"] in restaurant_ids]
            menus = {
                item["restaurant_id"]: self.restaurant_menus(property_id, item["restaurant_id"])
                for item in restaurants
            }
            if department_id is None:
                service_requests = db.execute(
                    "SELECT * FROM service_requests WHERE property_id=? ORDER BY created_at DESC",
                    (property_id,),
                ).fetchall()
            else:
                department = db.execute(
                    "SELECT name FROM departments WHERE property_id=? AND department_id=?",
                    (property_id, department_id),
                ).fetchone()
                scoped_department = department["name"] if department else "__unauthorized_department__"
                service_requests = db.execute(
                    "SELECT * FROM service_requests WHERE property_id=? AND department=? ORDER BY created_at DESC",
                    (property_id, scoped_department),
                ).fetchall()
            return {
                "facilities": [
                    self._facility_dict(row) for row in db.execute(
                        """SELECT f.*,COALESCE(m.location,'') AS location,COALESCE(m.policies,'[]') AS policies
                        FROM facility_profiles f LEFT JOIN facility_metadata m
                          ON m.facility_id=f.facility_id AND m.property_id=f.property_id
                        WHERE f.property_id=? ORDER BY f.name""",
                        (property_id,),
                    )
                ],
                "restaurants": restaurants,
                "menus": menus,
                "promotions": promotions,
                "events": [self._event_dict(row) for row in db.execute("SELECT * FROM hotel_events WHERE property_id=? ORDER BY starts_at", (property_id,))],
                "service_requests": [self._service_dict(row) for row in service_requests],
                "notification_rules": [self._notification_rule_dict(row) for row in db.execute("SELECT * FROM notification_rules WHERE property_id=? ORDER BY name", (property_id,))],
                "departments": [self._department_dict(row) for row in db.execute("SELECT * FROM departments WHERE property_id=? ORDER BY name", (property_id,))],
                "services": [self._service_catalog_dict(row) for row in db.execute("SELECT * FROM service_catalog WHERE property_id=? ORDER BY sort_order,name", (property_id,))],
                "recommendations": [self._recommendation_dict(row) for row in db.execute("SELECT * FROM recommendations WHERE property_id=? ORDER BY name", (property_id,))],
            }

    def guest_facilities(self, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            facilities = [
                self._facility_dict(row)
                for row in db.execute(
                    """SELECT f.*,COALESCE(m.location,'') AS location,COALESCE(m.policies,'[]') AS policies
                    FROM facility_profiles f LEFT JOIN facility_metadata m
                      ON m.facility_id=f.facility_id AND m.property_id=f.property_id
                    WHERE f.property_id=? AND f.live_status NOT IN ('maintenance','private_event') ORDER BY f.name""",
                    (property_id,),
                )
            ]
            restaurants = [
                self._restaurant_dict(row, guest=True)
                for row in db.execute(
                    "SELECT * FROM restaurants WHERE property_id=? AND archived=0 AND status NOT IN ('disabled','archived') ORDER BY name",
                    (property_id,),
                )
            ]
            menus = [
                self._menu_item_dict(row)
                for row in db.execute(
                    """SELECT mi.*,m.restaurant_id FROM menu_items mi
                    JOIN menus m ON m.menu_id=mi.menu_id AND m.property_id=mi.property_id
                    JOIN restaurants r ON r.restaurant_id=m.restaurant_id AND r.property_id=m.property_id
                    WHERE mi.property_id=? AND mi.available=1 AND m.active=1
                      AND m.workflow_status='published' AND r.archived=0 AND r.status NOT IN ('disabled','archived')""",
                    (property_id,),
                )
            ]
            promotions = [
                self._promotion_dict(row, guest=True)
                for row in db.execute(
                    """SELECT p.* FROM restaurant_promotions p
                    JOIN restaurants r ON r.restaurant_id=p.restaurant_id AND r.property_id=p.property_id
                    WHERE p.property_id=? AND p.status='published'
                      AND (p.starts_at IS NULL OR p.starts_at<=?)
                      AND (p.ends_at IS NULL OR p.ends_at>=?)
                      AND r.archived=0 AND r.status NOT IN ('disabled','archived')
                    ORDER BY p.starts_at,p.title""",
                    (property_id, _now(), _now()),
                )
            ]
            events = [self._event_dict(row) for row in db.execute("SELECT * FROM hotel_events WHERE property_id=? AND status='scheduled' ORDER BY starts_at", (property_id,))]
        return {"facilities": facilities, "restaurants": restaurants, "menu_items": menus, "promotions": promotions, "events": events}

    def request_metrics(self, property_id: str, *, department_name: str | None = None) -> dict[str, int]:
        with self._connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS total,
                SUM(CASE WHEN status NOT IN ('completed','cancelled') THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN status NOT IN ('completed','cancelled') AND due_at IS NOT NULL AND due_at<? THEN 1 ELSE 0 END) AS overdue_count
                FROM service_requests WHERE property_id=? AND (CAST(? AS TEXT) IS NULL OR department=?)""",
                (_now(), property_id, department_name, department_name),
            ).fetchone()
        return {"total_requests": int(row["total"] or 0), "open_requests": int(row["open_count"] or 0), "overdue_requests": int(row["overdue_count"] or 0)}

    def guest_requests_for_stay(self, property_id: str, stay_ids: set[str]) -> list[dict[str, Any]]:
        """Return service requests scoped to known guest session/stay handles."""
        ids = [value for value in stay_ids if value]
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        with self._connect() as db:
            rows = db.execute(
                # B608 rationale: marks contains only generated placeholders; stay IDs are bound below.
                f"SELECT * FROM service_requests WHERE property_id=? AND stay_id IN ({marks}) ORDER BY created_at DESC LIMIT 20",  # nosec B608
                (property_id, *ids),
            ).fetchall()
        return [self._service_dict(row) for row in rows]

    def _notification_allowed(self, rule: dict[str, Any], payload: dict[str, Any], prefs: dict[str, Any], current_zone_id: str | None, moment: int, *, property_timezone: str = "UTC") -> tuple[bool, str]:
        policy = rule.get("policy") or {}
        if not rule["enabled"]:
            return False, "rule_disabled"
        if rule["category"] == "experience" and not prefs.get("proactive_notifications", False):
            return False, "proactive_opt_out"
        if rule["category"] == "promotional" and not prefs.get("promotional_consent", False):
            return False, "promotional_opt_out"
        quiet = policy.get("quiet_hours") or {}
        timezone_name = policy.get("timezone", property_timezone)
        try:
            zone = ZoneInfo(str(timezone_name))
        except (ZoneInfoNotFoundError, ValueError):
            return False, "invalid_timezone"
        local = datetime.fromtimestamp(moment, timezone.utc).astimezone(zone)
        minute = local.hour * 60 + local.minute
        if quiet:
            try:
                interval = self._normalize_daily_interval(
                    {"start": quiet.get("start", 22), "end": quiet.get("end", 7)},
                    "Quiet hours",
                )
            except ValueError:
                return False, "invalid_quiet_hours"
            if self._minute_in_interval(minute, interval, quiet=True):
                return False, "quiet_hours"
        send_window = policy.get("send_window") or {}
        if send_window:
            try:
                interval = self._normalize_daily_interval(send_window, "Send window")
            except ValueError:
                return False, "invalid_send_window"
            if interval["start"] == interval["end"] or not self._minute_in_interval(minute, interval, quiet=False):
                return False, "outside_send_window"
        if current_zone_id and current_zone_id == payload.get("destination_zone_id"):
            return False, "already_at_destination"
        if payload.get("facility_status") in {"closed", "temporarily_closed", "full", "maintenance", "private_event"}:
            return False, "facility_not_available"
        return True, "eligible"

    def _require_owned(self, table: str, key: str, value: str, property_id: str) -> None:
        allowed_keys = {
            "departments": {"department_id"},
            "facility_profiles": {"facility_id"},
            "restaurants": {"restaurant_id"},
            "menus": {"menu_id"},
        }
        if key not in allowed_keys.get(table, set()):
            raise ValueError("Unsupported ownership lookup.")
        with self._connect() as db:
            # B608 rationale: table and key are selected from the fixed allowed_keys mapping above.
            row = db.execute(f"SELECT 1 FROM {table} WHERE property_id=? AND {key}=?", (property_id, value)).fetchone()  # nosec B608
        if row is None:
            raise KeyError(f"{table} record not found.")

    def _bools(self, row: sqlite3.Row | dict[str, Any], fields: list[str]) -> dict[str, Any]:
        data = dict(row)
        for field in fields:
            data[field] = bool(data[field])
        return data

    def _facility_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["booking_supported"])
        data["opening_hours"] = _load(data["opening_hours"])
        data["images"] = json.loads(data["images"] or "[]")
        data["policies"] = json.loads(data.get("policies") or "[]")
        return data

    def _restaurant_dict(self, row: sqlite3.Row | dict[str, Any], *, guest: bool = False) -> dict[str, Any]:
        data = self._bools(row, ["reservation_available", "archived"])
        data["opening_hours"] = _load(data["opening_hours"])
        data["meal_periods"] = json.loads(data["meal_periods"] or "[]")
        data["contact_details"] = _load(data.get("contact_details"))
        data["images"] = json.loads(data.get("images") or "[]")
        if guest:
            data.pop("internal_notes", None)
        return data

    @staticmethod
    def _menu_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["active"] = bool(data["active"])
        return data

    def _promotion_dict(self, row: sqlite3.Row | dict[str, Any], *, guest: bool = False) -> dict[str, Any]:
        data = dict(row)
        if guest:
            data.pop("created_by", None)
            data.pop("updated_by", None)
            data.pop("approved_by", None)
            data.pop("published_by", None)
        return data

    def _menu_item_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["available"])
        data["ingredients"] = json.loads(data["ingredients"] or "[]")
        data["allergens"] = json.loads(data["allergens"] or "[]")
        data["dietary_tags"] = json.loads(data["dietary_tags"] or "[]")
        return data

    def _event_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["notification_timing"] = _load(data["notification_timing"])
        return data

    def _service_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["notes"] = _load(data.get("notes") or "[]")
        now = _now()
        if data["status"] in {"completed", "cancelled"}:
            data["sla_state"] = data["status"]
        elif data.get("due_at") and now > data["due_at"]:
            data["sla_state"] = "overdue"
        elif data.get("due_at") and now > data["due_at"] - 300:
            data["sla_state"] = "warning"
        else:
            data["sla_state"] = "within_sla"
        return data

    def _department_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["enabled"])
        data["operating_hours"] = _load(data["operating_hours"])
        return data

    def _service_catalog_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["confirmation_required", "enabled", "archived"])
        data["keywords"] = _load(data["keywords"])
        return data

    def _recommendation_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["enabled"])
        data["images"] = _load(data["images"])
        data["opening_hours"] = _load(data["opening_hours"])
        return data

    def _notification_rule_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["enabled"])
        data["policy"] = _load(data["policy"])
        return data

    def _notification_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["verified_payload"] = _load(data["verified_payload"])
        return data
