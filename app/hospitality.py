import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


FACILITY_STATUSES = {"open", "closed", "temporarily_closed", "full", "maintenance", "private_event"}
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
                    updated_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS menus (
                    menu_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    restaurant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    meal_period TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
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
                    updated_at INTEGER NOT NULL
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

    def create_restaurant(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        status = str(payload.get("status") or "open")
        if status not in FACILITY_STATUSES:
            raise ValueError("Invalid restaurant status.")
        record = {
            "restaurant_id": _id("rest"),
            "property_id": property_id,
            "facility_id": payload.get("facility_id"),
            "name": _clean(payload.get("name"), 160),
            "location": _clean(payload.get("location"), 240),
            "opening_hours": _json(payload.get("opening_hours") or {}),
            "meal_periods": _json(list(payload.get("meal_periods") or [])[:12]),
            "reservation_available": 1 if payload.get("reservation_available") else 0,
            "description": _clean(payload.get("description"), 1000),
            "status": status,
            "updated_at": now,
            "created_at": now,
        }
        if not record["name"]:
            raise ValueError("Restaurant name is required.")
        with self._connect() as db:
            db.execute(
                """INSERT INTO restaurants VALUES
                (:restaurant_id,:property_id,:facility_id,:name,:location,:opening_hours,:meal_periods,
                :reservation_available,:description,:status,:updated_at,:created_at)""",
                record,
            )
        return self._restaurant_dict(record)

    def create_menu(self, property_id: str, restaurant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_owned("restaurants", "restaurant_id", restaurant_id, property_id)
        now = _now()
        record = {
            "menu_id": _id("menu"),
            "property_id": property_id,
            "restaurant_id": restaurant_id,
            "name": _clean(payload.get("name"), 160),
            "meal_period": _clean(payload.get("meal_period") or "all_day", 80),
            "active": 1 if payload.get("active", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Menu name is required.")
        with self._connect() as db:
            db.execute("INSERT INTO menus VALUES (:menu_id,:property_id,:restaurant_id,:name,:meal_period,:active,:created_at,:updated_at)", record)
        return self._bools(record, ["active"])

    def create_menu_item(self, property_id: str, menu_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_owned("menus", "menu_id", menu_id, property_id)
        now = _now()
        record = {
            "item_id": _id("item"),
            "property_id": property_id,
            "menu_id": menu_id,
            "name": _clean(payload.get("name"), 160),
            "description": _clean(payload.get("description"), 1000),
            "price": _clean(payload.get("price"), 40),
            "image_url": _clean(payload.get("image_url"), 500),
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
        return self._menu_item_dict(record)

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
        sla = payload.get("sla_target_seconds")
        due_at = now + int(sla) if sla else None
        record = {
            "request_id": _id("req"),
            "property_id": property_id,
            "stay_id": payload.get("stay_id"),
            "room": _clean(payload.get("room"), 80) or None,
            "request_type": _clean(payload.get("request_type") or "general", 80),
            "description": _clean(payload.get("description"), 1000),
            "priority": _clean(payload.get("priority") or "normal", 40),
            "department": _clean(payload.get("department") or "front_desk", 80),
            "status": "new",
            "sla_target_seconds": sla,
            "due_at": due_at,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        if not record["description"]:
            raise ValueError("Service request description is required.")
        with self._connect() as db:
            db.execute(
                """INSERT INTO service_requests VALUES
                (:request_id,:property_id,:stay_id,:room,:request_type,:description,:priority,:department,
                :status,:sla_target_seconds,:due_at,:completed_at,:created_at,:updated_at)""",
                record,
            )
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
        if not row:
            raise KeyError("Service request not found.")
        return self._service_dict(row)

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

    def overview(self, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            return {
                "facilities": [self._facility_dict(row) for row in db.execute("SELECT * FROM facility_profiles WHERE property_id=? ORDER BY name", (property_id,))],
                "restaurants": [self._restaurant_dict(row) for row in db.execute("SELECT * FROM restaurants WHERE property_id=? ORDER BY name", (property_id,))],
                "events": [self._event_dict(row) for row in db.execute("SELECT * FROM hotel_events WHERE property_id=? ORDER BY starts_at", (property_id,))],
                "service_requests": [self._service_dict(row) for row in db.execute("SELECT * FROM service_requests WHERE property_id=? ORDER BY created_at DESC", (property_id,))],
                "notification_rules": [self._notification_rule_dict(row) for row in db.execute("SELECT * FROM notification_rules WHERE property_id=? ORDER BY name", (property_id,))],
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
            restaurants = [self._restaurant_dict(row) for row in db.execute("SELECT * FROM restaurants WHERE property_id=? ORDER BY name", (property_id,))]
            menus = [self._menu_item_dict(row) for row in db.execute("SELECT mi.* FROM menu_items mi JOIN menus m ON m.menu_id=mi.menu_id WHERE mi.property_id=? AND mi.available=1 AND m.active=1", (property_id,))]
            events = [self._event_dict(row) for row in db.execute("SELECT * FROM hotel_events WHERE property_id=? AND status='scheduled' ORDER BY starts_at", (property_id,))]
        return {"facilities": facilities, "restaurants": restaurants, "menu_items": menus, "events": events}

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

    def _restaurant_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["reservation_available"])
        data["opening_hours"] = _load(data["opening_hours"])
        data["meal_periods"] = json.loads(data["meal_periods"] or "[]")
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

    def _notification_rule_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = self._bools(row, ["enabled"])
        data["policy"] = _load(data["policy"])
        return data

    def _notification_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        data["verified_payload"] = _load(data["verified_payload"])
        return data
