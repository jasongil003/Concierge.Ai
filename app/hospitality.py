import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


FACILITY_STATUSES = {"open", "closed", "temporarily_closed", "full", "maintenance", "private_event"}
RESTAURANT_STATUSES = FACILITY_STATUSES | {"disabled", "archived"}
SERVICE_STATUSES = ("new", "assigned", "accepted", "in_progress", "delivered", "completed")
NOTIFICATION_CATEGORIES = {"operational", "assistance", "experience", "promotional"}


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
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

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

    def catalog(self, property_id: str, guest: bool = False) -> dict[str, Any]:
        with self._connect() as db:
            departments = db.execute("SELECT * FROM departments WHERE property_id=? ORDER BY name", (property_id,)).fetchall()
            services = db.execute("SELECT * FROM service_catalog WHERE property_id=? ORDER BY sort_order,name", (property_id,)).fetchall()
        if guest:
            departments = [row for row in departments if row["enabled"]]
            services = [row for row in services if row["enabled"] and not row["archived"]]
        return {"departments": [self._department_dict(row) for row in departments], "services": [self._service_catalog_dict(row) for row in services]}

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
            "images": _json(list(payload.get("images") or [])[:12]),
            "capacity": payload.get("capacity"),
            "booking_supported": 1 if payload.get("booking_supported") else 0,
            "live_status": status,
            "status_note": _clean(payload.get("status_note"), 240),
            "updated_at": now,
            "created_at": now,
        }
        if not record["name"]:
            raise ValueError("Facility name is required.")
        with self._connect() as db:
            existing = db.execute("SELECT created_at FROM facility_profiles WHERE property_id=? AND facility_id=?", (property_id, facility_id)).fetchone()
            if existing:
                record["created_at"] = existing["created_at"]
                db.execute(
                    """UPDATE facility_profiles SET zone_id=:zone_id,building_id=:building_id,floor_id=:floor_id,
                    name=:name,facility_type=:facility_type,opening_hours=:opening_hours,description=:description,
                    images=:images,capacity=:capacity,booking_supported=:booking_supported,live_status=:live_status,
                    status_note=:status_note,updated_at=:updated_at WHERE property_id=:property_id AND facility_id=:facility_id""",
                    record,
                )
            else:
                db.execute(
                    """INSERT INTO facility_profiles VALUES
                    (:facility_id,:property_id,:zone_id,:building_id,:floor_id,:name,:facility_type,:opening_hours,
                    :description,:images,:capacity,:booking_supported,:live_status,:status_note,:updated_at,:created_at)""",
                    record,
                )
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
                f"SELECT * FROM menus WHERE property_id=? AND restaurant_id=? {clause} ORDER BY meal_period,name",
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

    def restaurant_analytics(self, property_id: str, restaurant_id: str) -> dict[str, Any]:
        self._require_owned("restaurants", "restaurant_id", restaurant_id, property_id)
        with self._connect() as db:
            conversations = db.execute(
                """SELECT COUNT(*) AS total,
                SUM(CASE WHEN state IN ('waiting_for_staff','assigned') THEN 1 ELSE 0 END) AS waiting,
                SUM(CASE WHEN state='human_active' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN state IN ('resolved','returned_to_ai') THEN 1 ELSE 0 END) AS completed
                FROM conversation_state WHERE property_id=? AND restaurant_id=?""",
                (property_id, restaurant_id),
            ).fetchone()
            messages = db.execute(
                """SELECT COUNT(*) FROM conversation_messages m
                JOIN conversation_state cs ON cs.property_id=m.property_id AND cs.session_id=m.session_id
                WHERE cs.property_id=? AND cs.restaurant_id=?""",
                (property_id, restaurant_id),
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
        if client_request_id:
            with self._connect() as db:
                existing = db.execute(
                    "SELECT * FROM service_requests WHERE property_id=? AND stay_id IS ? AND client_request_id=?",
                    (property_id, payload.get("stay_id"), client_request_id),
                ).fetchone()
            if existing:
                return {**self._service_dict(existing), "idempotent_replay": True}
        catalog_service = None
        if service_id:
            with self._connect() as db:
                catalog_service = db.execute(
                    "SELECT s.*, d.name AS department_name FROM service_catalog s LEFT JOIN departments d ON d.department_id=s.department_id WHERE s.property_id=? AND s.service_id=? AND s.enabled=1 AND s.archived=0",
                    (property_id, service_id),
                ).fetchone()
            if not catalog_service:
                raise ValueError("The selected service is not available.")
        sla = payload.get("sla_target_seconds")
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
        with self._connect() as db:
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
                clause = ",".join(f"{key}=?" for key in updates)
                db.execute(f"UPDATE service_requests SET {clause},updated_at=? WHERE property_id=? AND request_id=?", (*updates.values(), now, property_id, request_id))
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
        moment = now or _now()
        with self._connect() as db:
            row = db.execute("SELECT * FROM notification_rules WHERE property_id=? AND rule_id=?", (property_id, rule_id)).fetchone()
        if not row:
            raise KeyError("Notification rule not found.")
        rule = self._notification_rule_dict(row)
        allowed, reason = self._notification_allowed(rule, verified_payload, guest_preferences or {}, current_zone_id, moment)
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

    def overview(self, property_id: str, restaurant_ids: set[str] | None = None) -> dict[str, Any]:
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
            return {
                "facilities": [self._facility_dict(row) for row in db.execute("SELECT * FROM facility_profiles WHERE property_id=? ORDER BY name", (property_id,))],
                "restaurants": restaurants,
                "menus": menus,
                "promotions": promotions,
                "events": [self._event_dict(row) for row in db.execute("SELECT * FROM hotel_events WHERE property_id=? ORDER BY starts_at", (property_id,))],
                "service_requests": [self._service_dict(row) for row in db.execute("SELECT * FROM service_requests WHERE property_id=? ORDER BY created_at DESC", (property_id,))],
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
                    "SELECT * FROM facility_profiles WHERE property_id=? AND live_status NOT IN ('maintenance','private_event') ORDER BY name",
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
                    """SELECT mi.* FROM menu_items mi
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

    def request_metrics(self, property_id: str) -> dict[str, int]:
        with self._connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS total,
                SUM(CASE WHEN status!='completed' THEN 1 ELSE 0 END) AS open_count,
                SUM(CASE WHEN status!='completed' AND due_at IS NOT NULL AND due_at<? THEN 1 ELSE 0 END) AS overdue_count
                FROM service_requests WHERE property_id=?""",
                (_now(), property_id),
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
                f"SELECT * FROM service_requests WHERE property_id=? AND stay_id IN ({marks}) ORDER BY created_at DESC LIMIT 20",
                (property_id, *ids),
            ).fetchall()
        return [self._service_dict(row) for row in rows]

    def _notification_allowed(self, rule: dict[str, Any], payload: dict[str, Any], prefs: dict[str, Any], current_zone_id: str | None, moment: int) -> tuple[bool, str]:
        policy = rule.get("policy") or {}
        if not rule["enabled"]:
            return False, "rule_disabled"
        if rule["category"] == "promotional" and not prefs.get("promotional_consent", False):
            return False, "promotional_opt_out"
        quiet = policy.get("quiet_hours") or {}
        hour = time.localtime(moment).tm_hour
        if quiet and (int(quiet.get("start", 22)) <= hour or hour < int(quiet.get("end", 7))):
            return False, "quiet_hours"
        if current_zone_id and current_zone_id == payload.get("destination_zone_id"):
            return False, "already_at_destination"
        if payload.get("facility_status") in {"closed", "temporarily_closed", "full", "maintenance", "private_event"}:
            return False, "facility_not_available"
        return True, "eligible"

    def _require_owned(self, table: str, key: str, value: str, property_id: str) -> None:
        with self._connect() as db:
            row = db.execute(f"SELECT 1 FROM {table} WHERE property_id=? AND {key}=?", (property_id, value)).fetchone()
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
        if data["status"] == "completed":
            data["sla_state"] = "completed"
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
