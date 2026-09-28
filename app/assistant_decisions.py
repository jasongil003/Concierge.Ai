"""Ranks deterministic, guest-safe home content without calling an LLM."""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _clock_label(value: str) -> str:
    try:
        return datetime.strptime(value, "%H:%M").strftime("%-I:%M %p")
    except (TypeError, ValueError):
        return value


def _open_status(opening_hours: Any, local_now: datetime) -> str | None:
    """Return a status only when today's configured hours can be parsed."""
    if not isinstance(opening_hours, dict):
        return None
    day_names = (local_now.strftime("%A"), local_now.strftime("%a"), local_now.strftime("%A").lower(), local_now.strftime("%a").lower())
    hours = next((opening_hours.get(day) for day in day_names if day in opening_hours), None)
    if hours is None:
        # Some properties configure a single daily schedule rather than weekdays.
        hours = opening_hours.get("daily") or opening_hours.get("default")
    if isinstance(hours, dict):
        if hours.get("closed") is True or hours.get("is_closed") is True:
            return "Closed"
        opening, closing = hours.get("open") or hours.get("opens_at"), hours.get("close") or hours.get("closes_at")
        if opening and closing:
            hours = f"{opening}-{closing}"
    if isinstance(hours, list):
        hours = hours[0] if hours else None
    if not isinstance(hours, str):
        return None
    normalized = hours.strip().casefold()
    if normalized in {"24 hours", "24/7", "open 24 hours"}:
        return "Open 24 hours"
    if normalized in {"closed", "closed today"}:
        return "Closed"
    parts = hours.replace("–", "-").replace("—", "-").split("-", 1)
    if len(parts) != 2:
        return None
    try:
        opening = datetime.strptime(parts[0].strip(), "%H:%M").time()
        closing = datetime.strptime(parts[1].strip(), "%H:%M").time()
    except ValueError:
        return None
    current = local_now.time().replace(tzinfo=None)
    is_open = opening <= current < closing if opening < closing else current >= opening or current < closing
    if not is_open:
        return "Closed"
    return f"Open until {_clock_label(parts[1].strip())}"


class AssistantDecisionEngine:
    """Builds a small ranked set of cards from verified property and stay data."""

    def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        now = datetime.fromisoformat(context["time_context"]["local_datetime"])
        preferences = [str(item.get("value") or "").casefold() for item in context.get("preferences", [])]

        for request in context.get("active_requests", [])[:1]:
            candidates.append({
                "type": "active_request", "priority": 100,
                "reason_codes": ["active_request"],
                "resource": request,
                "card": {
                    "type": "request", "title": request["name"], "subtitle": request.get("department"),
                    "status": request.get("status"), "description": request.get("description"),
                    "request_id": request.get("request_id"), "cancellable": request.get("cancellable", False),
                },
            })

        meal_period = "dinner" if 17 <= now.hour <= 22 else "lunch" if 11 <= now.hour < 15 else "breakfast" if 6 <= now.hour < 11 else ""
        for restaurant in context.get("restaurant_recommendations", []):
            cuisine = str(restaurant.get("cuisine") or "")
            pref_match = bool(cuisine and any(cuisine.casefold() in value or value in cuisine.casefold() for value in preferences))
            hours_label = _open_status(restaurant.get("opening_hours"), now)
            live_status = str(restaurant.get("status") or "").casefold()
            if live_status in {"closed", "temporarily_closed", "full", "maintenance", "private_event"}:
                hours_label = {
                    "temporarily_closed": "Temporarily closed", "private_event": "Unavailable",
                }.get(live_status, live_status.replace("_", " ").title())
            reasons = []
            priority = 40
            if pref_match:
                reasons.append("matches_preference")
                priority += 35
            if hours_label and hours_label.startswith("Open"):
                reasons.append("open_now")
                priority += 10
            if meal_period:
                reasons.append(f"{meal_period}_time")
                priority += 8
            candidates.append({
                "type": "restaurant_recommendation", "priority": priority,
                "reason_codes": reasons,
                "card": {
                    "type": "restaurant", "title": str(restaurant.get("name") or "Dining"),
                    "subtitle": " · ".join(part for part in (cuisine, str(restaurant.get("location") or "")) if part),
                    "status": hours_label, "description": str(restaurant.get("description") or ""),
                    "restaurant_id": restaurant.get("restaurant_id"), "personalized": pref_match,
                    "actions": [
                        {"label": "View menu", "action": "menu", "restaurant_id": restaurant.get("restaurant_id")},
                        *([{"label": "Directions", "action": "directions", "facility_id": restaurant.get("facility_id")}] if restaurant.get("facility_id") else []),
                    ],
                },
            })

        for event in context.get("hotel_events", []):
            candidates.append({
                "type": "event", "priority": 68, "reason_codes": ["upcoming_event"],
                "resource": event,
                "card": {
                    "type": "event", "title": event.get("title", ""),
                    "subtitle": datetime.fromtimestamp(event["starts_at"], now.tzinfo).strftime("%a, %-I:%M %p"),
                    "description": event.get("description", ""), "event_id": event.get("event_id"),
                    "facility_id": event.get("facility_id"), "cta": event.get("cta") or "View event",
                },
            })

        for recommendation in context.get("recommendations", []):
            candidates.append({
                "type": "recommendation", "priority": 46, "reason_codes": ["configured_recommendation"],
                "resource": recommendation,
                "card": {
                    "type": "recommendation", "title": recommendation.get("name", ""),
                    "subtitle": recommendation.get("category", ""),
                    "description": recommendation.get("description") or recommendation.get("address", ""),
                    "recommendation_id": recommendation.get("recommendation_id"),
                    "map_url": recommendation.get("map_url", ""),
                },
            })

        candidates.sort(key=lambda item: (-item["priority"], item["type"], str(item["card"].get("title", "")).casefold()))
        selected = candidates[:5]
        primary = selected[0]["card"] if selected else None
        if primary and primary["type"] == "request":
            next_action = {"label": "Track your request", "view": "requests"}
        elif primary and primary["type"] == "event":
            next_action = {"label": primary.get("cta") or "View event", "view": "explore", "event_id": primary.get("event_id")}
        elif primary and primary["type"] == "restaurant":
            next_action = {"label": "Explore dining", "view": "explore"}
        elif "service_request.create" in context.get("available_actions", []):
            next_action = {"label": "Request something", "view": "requests"}
        elif context.get("restaurant_recommendations"):
            next_action = {"label": "Explore dining", "view": "explore"}
        else:
            next_action = None

        services_available = "service_request.create" in context.get("available_actions", [])
        quick_actions = []
        if context.get("restaurant_recommendations"):
            quick_actions.append({"label": "Dining", "view": "explore"})
        if services_available:
            quick_actions.append({"label": "Request something", "view": "requests"})
        if context.get("facilities") or context.get("hotel_events") or context.get("recommendations"):
            quick_actions.append({"label": "Explore", "view": "explore"})
        quick_actions.append({"label": "My Stay", "view": "stay"})

        phase = context["stay"]["phase"]
        if phase == "morning":
            prompts = ["Plan my morning", "Show me dining options"]
        elif phase in {"evening", "late_night"}:
            prompts = ["Show me dining options", "What is happening tonight?"]
        elif phase == "arrival":
            prompts = ["Show me the guest services", "What can I explore?"]
        else:
            prompts = ["Show me dining options", "What can I explore?"]
        return {
            "greeting": context["time_context"].get("greeting", "Welcome"),
            "stay": context["stay"],
            "primary_action": next_action,
            "primary_card": primary,
            "cards": [item["card"] for item in selected],
            "active_requests": context.get("active_requests", []),
            "events": context.get("hotel_events", [])[:4],
            "quick_actions": quick_actions,
            "suggested_prompts": prompts,
            "inventory": {
                "restaurants": context.get("restaurant_recommendations", []),
                "facilities": context.get("facilities", []),
                "events": context.get("hotel_events", []),
                "promotions": context.get("promotions", []),
                "menu_items": context.get("menu_items", []),
                "recommendations": context.get("recommendations", []),
            },
        }
