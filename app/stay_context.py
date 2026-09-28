"""Deterministic, privacy-filtered context for the current guest stay."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .guardrails import normalize_guardrails

ACTIVE_REQUEST_STATUSES = {"new", "assigned", "accepted", "in_progress"}


def _local_time(property_timezone: str | None, now: datetime | None = None) -> tuple[datetime, str]:
    try:
        tz = ZoneInfo(str(property_timezone or "UTC"))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        tz = timezone.utc
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz), getattr(tz, "key", "UTC")


def _phase(hour: int, authenticated: bool, stay: dict[str, Any] | None) -> str:
    if stay and stay.get("status") in {"checked_out", "departed"}:
        return "departed"
    if not authenticated:
        return "arrival"
    if hour < 5 or hour >= 22:
        return "late_night"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "daytime"
    return "evening"


def _safe_request(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(row.get("request_id") or ""),
        "name": str(row.get("request_type") or "Service request")[:100],
        "description": str(row.get("description") or "")[:240],
        "department": str(row.get("department") or "")[:100],
        "status": str(row.get("status") or "unknown")[:40],
        "created_at": int(row.get("created_at") or 0),
        "updated_at": int(row.get("updated_at") or 0),
        "cancellable": row.get("status") == "new",
    }


class StayContextEngine:
    """Builds current stay facts from property-scoped stores without AI calls."""

    def build(
        self,
        property_record: Any,
        session: Any,
        hospitality: Any,
        identities: Any,
        personalization: Any,
        conversation_store: Any = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        local_now, timezone_name = _local_time(getattr(property_record, "timezone", "UTC"), now)
        authenticated = bool(getattr(session, "authenticated", False))
        linked_stay = None
        if authenticated and identities is not None:
            linked_stay = identities.active_stay_for_session(property_record.property_id, session.session_id)

        state = personalization.guest_state(property_record.property_id, session.session_id) if personalization else {"enabled": False, "preferences": []}
        preferences = []
        if state.get("enabled"):
            preferences = [
                {"category": str(item.get("category") or "")[:40], "value": str(item.get("value") or "")[:160]}
                for item in state.get("preferences", [])
                if isinstance(item, dict)
            ][:20]

        stay_ids = {session.session_id}
        if linked_stay and linked_stay.get("stay_id"):
            stay_ids.add(str(linked_stay["stay_id"]))
        rows = hospitality.guest_requests_for_stay(property_record.property_id, stay_ids) if hospitality else []
        requests = [_safe_request(row) for row in rows]
        active_requests = [item for item in requests if item["status"] in ACTIVE_REQUEST_STATUSES]

        inventory = hospitality.guest_facilities(property_record.property_id) if hospitality else {
            "facilities": [], "restaurants": [], "menu_items": [], "promotions": [], "events": []
        }
        moment = int(local_now.timestamp())
        events = []
        for item in inventory.get("events", []):
            if item.get("audience", "all_guests") not in {"all_guests", "all", "guests"}:
                continue
            starts = int(item.get("starts_at") or 0)
            ends = int(item.get("ends_at") or 0)
            if starts >= moment or (ends and ends >= moment):
                events.append({
                    "event_id": str(item.get("event_id") or ""),
                    "title": str(item.get("title") or "")[:180],
                    "description": str(item.get("description") or "")[:500],
                    "starts_at": starts,
                    "ends_at": ends or None,
                    "facility_id": item.get("facility_id"),
                    "cta": str(item.get("cta") or "")[:100],
                })
        events.sort(key=lambda item: item["starts_at"])

        restaurants = [
            item for item in inventory.get("restaurants", [])
            if item.get("status") not in {"disabled", "archived"} and not item.get("archived")
        ]
        facilities = [
            item for item in inventory.get("facilities", [])
            if item.get("live_status") not in {"maintenance", "private_event"}
        ]
        catalog = hospitality.catalog(property_record.property_id, guest=True) if hospitality else {"departments": [], "services": []}
        services = [item for item in catalog.get("services", []) if item.get("enabled") and not item.get("archived")]
        departments = [item for item in catalog.get("departments", []) if item.get("enabled")]
        guardrails = normalize_guardrails(getattr(property_record, "guardrails", {}))
        if not guardrails.get("service_requests_enabled"):
            services = []
        recommendations = hospitality.recommendations(property_record.property_id, guest=True) if hospitality else []

        conversation = {}
        if conversation_store is not None:
            try:
                value = conversation_store.conversation_state(session.session_id, property_record.property_id)
                conversation = {"status": str(value.get("state") or "open"), "staff_active": value.get("state") == "human_active"}
            except (KeyError, TypeError, AttributeError):
                conversation = {}

        return {
            "property": {"name": str(property_record.hotel_name), "timezone": timezone_name},
            "session": {"authenticated": authenticated},
            "stay": {
                "status": "departed" if linked_stay and linked_stay.get("status") in {"checked_out", "departed"} else "checked_in" if authenticated else "unverified",
                "phase": _phase(local_now.hour, authenticated, linked_stay),
            },
            "time_context": {
                "local_datetime": local_now.isoformat(timespec="minutes"),
                "local_date": local_now.date().isoformat(),
                "local_time": local_now.strftime("%-I:%M %p"),
                "hour": local_now.hour,
                "greeting": "Good morning" if local_now.hour < 12 else "Good afternoon" if local_now.hour < 17 else "Good evening",
            },
            "preferences": preferences,
            "recent_interests": [],
            "active_requests": active_requests,
            "recent_requests": requests[:10],
            "restaurant_activity": [],
            "restaurant_recommendations": restaurants,
            "facilities": facilities,
            "hotel_events": events,
            "promotions": inventory.get("promotions", []),
            "menu_items": inventory.get("menu_items", []),
            "recommendations": recommendations,
            "staff_conversations": conversation,
            "navigation_context": {},
            "weather_context": {},
            "guest_location_context": {},
            "available_actions": [action for action in [
                *(["service_request.create", "service_request.view"] if services else ["service_request.view"]),
                "restaurant.search" if restaurants else None,
                "restaurant.menu.search" if inventory.get("menu_items") else None,
                "facility.search" if facilities else None,
                "event.list" if events else None,
                "promotion.list" if inventory.get("promotions") else None,
                "recommendation.search" if recommendations else None,
                "personalization.update",
                "personalization.delete",
                "human_handoff.request" if guardrails.get("human_escalation_enabled") and (restaurants or departments) else None,
            ] if action],
        }

    @staticmethod
    def prompt_context(context: dict[str, Any]) -> dict[str, Any]:
        """Remove identifiers and fields that are only needed to render UI cards."""
        return {
            "property": context.get("property", {}),
            "session": context.get("session", {}),
            "stay": context.get("stay", {}),
            "time_context": context.get("time_context", {}),
            "preferences": context.get("preferences", []),
            "active_requests": [
                {key: row.get(key) for key in ("name", "description", "department", "status", "created_at", "updated_at")}
                for row in context.get("active_requests", [])
            ],
            "recent_requests": [
                {key: row.get(key) for key in ("name", "description", "department", "status", "created_at", "updated_at")}
                for row in context.get("recent_requests", [])
            ],
            "restaurant_recommendations": [
                {key: row.get(key) for key in ("name", "location", "description", "cuisine", "status", "opening_hours")}
                for row in context.get("restaurant_recommendations", [])
            ],
            "facilities": [
                {key: row.get(key) for key in ("name", "facility_type", "description", "live_status", "opening_hours")}
                for row in context.get("facilities", [])
            ],
            "hotel_events": [
                {key: row.get(key) for key in ("title", "description", "starts_at", "ends_at", "cta")}
                for row in context.get("hotel_events", [])
            ],
            "promotions": [
                {key: row.get(key) for key in ("title", "description", "starts_at", "ends_at")}
                for row in context.get("promotions", [])
            ],
            "menu_items": [
                {key: row.get(key) for key in ("name", "description", "price", "ingredients", "allergens", "dietary_tags", "available")}
                for row in context.get("menu_items", [])
            ],
            "recommendations": [
                {key: row.get(key) for key in ("name", "category", "description", "address", "opening_hours")}
                for row in context.get("recommendations", [])
            ],
            "staff_conversations": context.get("staff_conversations", {}),
            "available_actions": [action for action in context.get("available_actions", []) if action],
        }
