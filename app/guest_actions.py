"""Restricted guest action registry and signed service request proposals."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class GuestActionDefinition:
    name: str
    description: str
    accepted_schema: dict[str, Any]
    confirmation_required: bool
    required_capability: str
    property_scope: str
    rate_limit: tuple[int, int]
    audit_event: str
    executor: str


class GuestActionRegistry:
    """A fixed allowlist of guest capabilities; no model-provided function names."""

    def __init__(self) -> None:
        self._actions = {
            "service_request.create": GuestActionDefinition(
                "service_request.create", "Match a guest request to an active, guest-visible configured service.",
                {"type": "object", "required": ["query", "description"], "properties": {"query": {"type": "string", "maxLength": 300}, "description": {"type": "string", "maxLength": 1000}}},
                True, "service_catalog", "current_property", (10, 300), "guest.action.proposed", "propose_configured_service",
            ),
            "service_request.view": GuestActionDefinition(
                "service_request.view", "View requests belonging to the current guest session.",
                {"type": "object", "properties": {}}, False, "service_requests", "current_property_and_session", (60, 60), "guest.action.executed", "list_guest_requests",
            ),
            "service_request.cancel": GuestActionDefinition(
                "service_request.cancel", "Cancel a new request belonging to the current guest session.",
                {"type": "object", "required": ["request_id"], "properties": {"request_id": {"type": "string", "maxLength": 100}}},
                True, "service_requests", "current_property_and_session", (10, 300), "guest.action.confirmed", "cancel_guest_request",
            ),
            "restaurant.search": self._read_action("restaurant.search", "Search guest-visible restaurants.", "restaurants"),
            "restaurant.menu.search": self._read_action("restaurant.menu.search", "Search published menu items and configured dietary or allergen data.", "published_menus"),
            "restaurant.staff_request": self._write_action("restaurant.staff_request", "Request help from a configured restaurant team.", "restaurant_staff"),
            "facility.search": self._read_action("facility.search", "Search guest-visible facilities.", "facilities"),
            "facility.status": self._read_action("facility.status", "Read configured live facility status.", "facilities"),
            "navigation.route": self._read_action("navigation.route", "Find a route in the configured guest navigation graph.", "navigation"),
            "event.list": self._read_action("event.list", "List guest-visible hotel events.", "events"),
            "event.view": self._read_action("event.view", "View one guest-visible hotel event.", "events"),
            "promotion.list": self._read_action("promotion.list", "List published promotions valid now.", "promotions"),
            "recommendation.search": self._read_action("recommendation.search", "Search configured guest recommendations.", "recommendations"),
            "personalization.update": self._write_action("personalization.update", "Update an explicitly guest-approved preference.", "personalization"),
            "personalization.delete": self._write_action("personalization.delete", "Remove one or all preferences for the current guest session.", "personalization"),
            "human_handoff.request": self._write_action("human_handoff.request", "Request contact from a configured hotel department or service.", "human_handoff"),
        }

    @staticmethod
    def _read_action(name: str, description: str, capability: str) -> GuestActionDefinition:
        return GuestActionDefinition(name, description, {"type": "object", "properties": {"query": {"type": "string", "maxLength": 300}}}, False, capability, "current_property", (60, 60), "guest.action.executed", "search_configured_guest_data")

    @staticmethod
    def _write_action(name: str, description: str, capability: str) -> GuestActionDefinition:
        return GuestActionDefinition(name, description, {"type": "object", "properties": {"query": {"type": "string", "maxLength": 1000}}}, True, capability, "current_property_and_session", (10, 300), "guest.action.proposed", "execute_confirmed_guest_action")

    def get(self, action_name: str) -> GuestActionDefinition | None:
        return self._actions.get(action_name)

    def definitions(self) -> list[GuestActionDefinition]:
        return list(self._actions.values())

    @staticmethod
    def validate(definition: GuestActionDefinition, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Action arguments must be an object.")
        required = definition.accepted_schema.get("required", [])
        if any(key not in payload for key in required):
            raise ValueError("Action arguments are incomplete.")
        properties = definition.accepted_schema.get("properties", {})
        clean = {}
        for key, rule in properties.items():
            if key not in payload:
                continue
            value = payload[key]
            if not isinstance(value, str) or len(value) > int(rule.get("maxLength", 1000)):
                raise ValueError("Action arguments are invalid.")
            clean[key] = value.strip()
        if any(not clean.get(key) for key in required):
            raise ValueError("Action arguments are incomplete.")
        return clean

    @staticmethod
    def match_service(query: str, services: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        normalized = " ".join(re.findall(r"[a-z0-9]+", query.casefold()))
        if not normalized:
            return None, []
        matches = []
        for service in services:
            if not service.get("enabled") or service.get("archived"):
                continue
            name = str(service.get("name") or "")
            terms = [name, *(str(value) for value in service.get("keywords", []))]
            best = 0
            for index, term in enumerate(terms):
                normalized_term = " ".join(re.findall(r"[a-z0-9]+", term.casefold()))
                if not normalized_term:
                    continue
                if normalized_term == normalized:
                    # A guest selecting a catalog item should resolve by its exact
                    # configured name ahead of other services' matching keywords.
                    best = max(best, 110 if index == 0 else 100)
                elif normalized_term in normalized:
                    best = max(best, 94 if index == 0 else 80)
                elif normalized in normalized_term:
                    best = max(best, 76 if index == 0 else 68)
                else:
                    token_ratio = len(set(normalized_term.split()) & set(normalized.split())) / max(1, len(set(normalized_term.split())))
                    if token_ratio >= 0.75:
                        best = max(best, round(50 * token_ratio))
            if best:
                matches.append((best, service))
        matches.sort(key=lambda item: (-item[0], str(item[1].get("name", "")).casefold()))
        if not matches:
            return None, []
        top_score = matches[0][0]
        top = [item[1] for item in matches if item[0] == top_score]
        return (top[0], []) if len(top) == 1 else (None, top[:4])

    @staticmethod
    def make_service_proposal(secret: str, property_id: str, session_id: str, service: dict[str, Any], description: str, now: int | None = None) -> str:
        payload = {
            "action": "service_request.create", "property": property_id, "session": session_id,
            "service": str(service["service_id"]), "description": description[:1000],
            "issued_at": int(now if now is not None else time.time()), "nonce": secrets.token_urlsafe(18),
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    @staticmethod
    def read_service_proposal(secret: str, token: str, property_id: str, session_id: str, now: int | None = None) -> dict[str, Any]:
        try:
            encoded, signature = token.split(".", 1)
            expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except (ValueError, TypeError, json.JSONDecodeError, base64.binascii.Error) as exc:
            raise ValueError("The request confirmation expired. Please try again.") from exc
        moment = int(now if now is not None else time.time())
        if payload.get("action") != "service_request.create" or payload.get("property") != property_id or payload.get("session") != session_id:
            raise ValueError("The request confirmation is not valid for this stay.")
        issued = int(payload.get("issued_at") or 0)
        if issued > moment or moment - issued > 600:
            raise ValueError("The request confirmation expired. Please try again.")
        return payload
