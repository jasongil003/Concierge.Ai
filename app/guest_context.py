"""Build a privacy-filtered, evidence-backed context for a guest turn."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class GuestContext:
    property_id: str
    authenticated: bool
    stay_id: str | None = None
    room: str | None = None
    preferred_language: str | None = None
    stay_stage: str = "pre_auth"
    check_in: str | None = None
    check_out: str | None = None
    preferences: list[str] | None = None
    conversation_summary: str = ""
    recent_messages: list[dict[str, str]] | None = None
    open_requests: list[dict[str, str]] | None = None
    recent_requests: list[dict[str, str]] | None = None
    current_zone: str | None = None
    relevant_journey_events: list[str] | None = None

    def prompt_data(self) -> dict[str, Any]:
        data = asdict(self)
        # Internal linkage IDs are deliberately kept out of model-visible context.
        data.pop("property_id", None)
        data.pop("stay_id", None)
        return data


def build_guest_context(property_id: str, session: Any, identities: Any, hospitality: Any, history: list[dict[str, Any]]) -> GuestContext:
    context = GuestContext(property_id=property_id, authenticated=bool(session.authenticated), recent_messages=[
        {"role": str(item.get("role", "")), "content": str(item.get("content", ""))[:1000]}
        for item in history[-8:]
    ], preferences=[], open_requests=[], recent_requests=[], relevant_journey_events=[])
    # A stay is private context and requires both an authenticated live session and
    # a property-scoped, explicit concierge-session association.
    if not session.authenticated:
        return context
    stay = identities.active_stay_for_session(property_id, session.session_id)
    if not stay:
        return context
    context.stay_id = stay["stay_id"]
    context.room = stay.get("room")
    context.stay_stage = "in_stay"
    memory = stay.get("memory_summary") or {}
    context.preferences = [str(item)[:120] for item in memory.get("preferences", []) if isinstance(item, str)][:20]
    context.conversation_summary = str(memory.get("conversation_summary") or "")[:1200]
    # Service request rows are property-filtered by the store and then restricted
    # to this authenticated session or its linked stay before model exposure.
    try:
        rows = hospitality.guest_requests_for_stay(property_id, {session.session_id, stay["stay_id"]})
    except (AttributeError, TypeError):
        rows = []
    safe_rows = [{"type": str(row.get("request_type", "request"))[:80],
                  "description": str(row.get("description", ""))[:240],
                  "status": str(row.get("status", "unknown"))[:40],
                  "updated_at": str(row.get("updated_at", ""))[:30]} for row in rows[:20]]
    context.open_requests = [row for row in safe_rows if row["status"] != "completed"]
    context.recent_requests = safe_rows
    return context
