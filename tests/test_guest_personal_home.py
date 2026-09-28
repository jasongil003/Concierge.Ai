from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import app.main as main_module
from app.assistant_decisions import AssistantDecisionEngine, _open_status
from app.guest_actions import GuestActionRegistry
from app.guest_context import build_guest_context
from app.guest_identity import GuestIdentityStore
from app.hospitality import HospitalityStore
from app.personalization import PersonalizationStore
from app.properties import PropertyRecord
from app.session_store import SessionRecord
from app.stay_context import StayContextEngine


def test_stay_context_uses_property_timezone_and_guest_scoped_data(tmp_path: Path):
    hospitality = HospitalityStore(tmp_path / "stay-context.db")
    personalization = PersonalizationStore(tmp_path / "stay-context.db")
    identities = GuestIdentityStore(tmp_path / "stay-context.db")
    hospitality.create_service_request("hotel-a", {
        "request_type": "Configured Service", "description": "Submitted by this guest", "stay_id": "guest-session-a",
    })
    hospitality.create_service_request("hotel-a", {
        "request_type": "Another Guest Service", "description": "Private request", "stay_id": "guest-session-b",
    })
    hospitality.upsert_facility_profile("hotel-a", {
        "name": "Configured Lounge", "facility_type": "lounge", "description": "Guest lounge.",
    })
    hospitality.create_event("hotel-a", {
        "title": "Guest Event", "starts_at": int(datetime(2026, 9, 28, 12, tzinfo=timezone.utc).timestamp()),
        "audience": "all_guests",
    })
    session = SessionRecord("guest-session-a", "hotel-a", "device-a", {}, True, 0, 0)
    property_record = PropertyRecord(property_id="hotel-a", hotel_name="Property A", timezone="Asia/Manila")
    now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)

    context = StayContextEngine().build(property_record, session, hospitality, identities, personalization, now=now)

    assert context["property"] == {"name": "Property A", "timezone": "Asia/Manila"}
    assert context["time_context"]["local_datetime"].startswith("2026-09-28T20:00")
    assert context["time_context"]["greeting"] == "Good evening"
    assert context["stay"]["phase"] == "evening"
    assert [item["name"] for item in context["active_requests"]] == ["Configured Service"]
    assert [item["name"] for item in context["facilities"]] == ["Configured Lounge"]
    assert context["hotel_events"][0]["title"] == "Guest Event"
    assert "room" not in context["stay"]

    prompt_context = StayContextEngine.prompt_context(context)
    serialized = str(prompt_context)
    assert "property_id" not in serialized
    assert "request_id" not in serialized
    assert "guest-session-a" not in serialized
    assert "Private request" not in serialized


def test_stay_context_only_uses_consented_preferences(tmp_path: Path):
    store = PersonalizationStore(tmp_path / "personalization.db")
    property_record = PropertyRecord(property_id="hotel-a", hotel_name="A")
    session = SessionRecord("guest-session", "hotel-a", "device", {}, False, 0, 0)
    store.set_guest_state("hotel-a", session.session_id, True, "stay")
    store.save_preference("hotel-a", session.session_id, "food", "Japanese cuisine", preference_key="food.jp")
    context = StayContextEngine().build(property_record, session, None, None, store)
    assert context["preferences"] == [{"category": "food", "value": "Japanese cuisine"}]

    store.set_guest_state("hotel-a", session.session_id, False, "stay")
    private_context = StayContextEngine().build(property_record, session, None, None, store)
    assert private_context["preferences"] == []


def test_assistant_decision_ranks_requests_and_does_not_claim_unknown_hours():
    context = {
        "time_context": {"local_datetime": "2026-09-28T19:00+08:00"},
        "stay": {"phase": "evening"},
        "preferences": [{"category": "food", "value": "Japanese"}],
        "active_requests": [{"name": "Configured service", "department": "Guest Services", "status": "new", "request_id": "req-1", "cancellable": True}],
        "restaurant_recommendations": [
            {"name": "Configured Dining", "restaurant_id": "rest-1", "cuisine": "Japanese", "opening_hours": {}, "status": "open"},
            {"name": "Closed Dining", "restaurant_id": "rest-2", "cuisine": "Other", "opening_hours": {"monday": "09:00-17:00"}, "status": "closed"},
        ],
        "hotel_events": [], "recommendations": [], "facilities": [],
        "available_actions": ["service_request.create"],
    }
    result = AssistantDecisionEngine().decide(context)
    assert result["primary_card"]["type"] == "request"
    assert result["primary_action"] == {"label": "Track your request", "view": "requests"}
    dining = next(item for item in result["cards"] if item["type"] == "restaurant")
    assert dining["personalized"] is True
    assert dining["status"] is None
    assert _open_status({}, datetime(2026, 9, 28, 19, tzinfo=timezone.utc)) is None


def test_guest_action_registry_is_fixed_and_signed_proposals_are_scoped():
    registry = GuestActionRegistry()
    service = {"service_id": "service-a", "name": "Extra Towels", "keywords": ["towel", "towels"], "enabled": True, "archived": False}
    matched, alternatives = registry.match_service("I need two towels", [service])
    assert matched == service
    assert alternatives == []
    assert registry.match_service("Where is my towel request", [service])[0] == service
    overlapping = [
        {**service, "name": "Extra Towels"},
        {**service, "service_id": "service-b", "name": "Towels"},
    ]
    assert registry.match_service("Towels", overlapping)[0] == overlapping[1]
    assert registry.get("admin.configuration.update") is None
    assert all(item.executor and item.property_scope and item.required_capability for item in registry.definitions())

    token = registry.make_service_proposal("property-secret", "hotel-a", "session-a", service, "I need two towels", now=100)
    proposal = registry.read_service_proposal("property-secret", token, "hotel-a", "session-a", now=120)
    assert proposal["service"] == "service-a"
    for property_id, session_id in (("hotel-b", "session-a"), ("hotel-a", "session-b")):
        try:
            registry.read_service_proposal("property-secret", token, property_id, session_id, now=120)
        except ValueError:
            pass
        else:
            raise AssertionError("Proposal tokens must be scoped to the active property and session.")


def test_guest_home_and_request_endpoints_are_property_and_session_scoped(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "guest-home.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    department = hospitality.upsert_department(property_id, {"name": "Configured Team"})
    service = hospitality.upsert_service(property_id, {
        "name": "Extra Towels", "department_id": department["department_id"], "keywords": ["towel", "towels"],
    })
    hospitality.create_restaurant(property_id, {"name": "Configured Dining", "cuisine": "Japanese"})
    session_a = admin_client.post("/api/session/start", json={"client_id": "guest-a"}).json()["session_id"]
    session_b = admin_client.post("/api/session/start", json={"client_id": "guest-b"}).json()["session_id"]

    home = admin_client.get(f"/api/guest/home?session_id={session_a}")
    assert home.status_code == 200, home.text
    assert home.json()["inventory"]["restaurants"][0]["name"] == "Configured Dining"
    assert home.json()["primary_card"]["type"] == "restaurant"
    assert "restaurant_id" not in str(home.json()["stay"])

    proposal = admin_client.post("/api/guest/actions/propose", json={"session_id": session_a, "message": "I need two towels"})
    assert proposal.status_code == 200, proposal.text
    proposal_data = proposal.json()
    assert proposal_data["status"] == "proposed"
    assert proposal_data["card"]["title"] == "Extra Towels"
    created = admin_client.post("/api/guest/actions/confirm", json={"session_id": session_a, "proposal_token": proposal_data["proposal_token"]})
    assert created.status_code == 200, created.text
    request_id = created.json()["request"]["request_id"]
    assert created.json()["request"]["department"] == "Configured Team"

    visible_to_owner = admin_client.get(f"/api/guest/requests?session_id={session_a}").json()["requests"]
    visible_to_other = admin_client.get(f"/api/guest/requests?session_id={session_b}").json()["requests"]
    assert [item["request_id"] for item in visible_to_owner] == [request_id]
    assert visible_to_other == []
    assert "stay_id" not in str(visible_to_owner)

    cancelled = admin_client.post(
        f"/api/guest/requests/{request_id}/cancel",
        json={"session_id": session_a, "confirmed": True},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["request"]["status"] == "cancelled"
    assert admin_client.get(f"/api/guest/requests?session_id={session_a}").json()["requests"][0]["status"] == "cancelled"
    cross_cancel = admin_client.post(
        f"/api/guest/requests/{request_id}/cancel",
        json={"session_id": session_b, "confirmed": True},
    )
    assert cross_cancel.status_code == 404

    unavailable = admin_client.post("/api/guest/actions/propose", json={"session_id": session_b, "message": "Bring a unicorn"})
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unmatched"
