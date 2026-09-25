from pathlib import Path
from types import SimpleNamespace

from app.personalization import PersonalizationStore, extract_preferences, preference_commands
from app.guest_identity import GuestIdentityStore
from app.hospitality import HospitalityStore
from app.session_store import SessionStore
import app.main as main_module


def test_guest_preferences_are_private_until_the_guest_opts_in(tmp_path: Path):
    store = PersonalizationStore(tmp_path / "personalization.db")
    state = store.guest_state("hotel-a", "session-a")
    assert state["enabled"] is False
    assert state["level"] == "private"
    assert state["suggested_level"] == "private"

    store.set_guest_state("hotel-a", "session-a", True, "stay")
    extracted = extract_preferences("I'm vegetarian and I normally prefer restaurants under ₱1,000/person.")
    assert [(item["category"], item["persistence"]) for item in extracted] == [("dietary", "stay"), ("budget", "stay")]
    for preference in extracted:
        store.save_preference("hotel-a", "session-a", **preference)

    context = store.context_for("hotel-a", "session-a", "Restaurant nearby?")
    assert context["personalization_level"] == "stay"
    assert {item["value"] for item in context["preferences"]} == {"vegetarian", "Under ₱1,000 per person"}
    assert store.guest_state("hotel-a", "session-b")["preferences"] == []
    assert store.guest_state("hotel-b", "session-a")["preferences"] == []

    store.set_guest_state("hotel-a", "session-a", False, "stay")
    assert store.context_for("hotel-a", "session-a", "Restaurant nearby?")["preferences"] == []
    assert len(store.guest_state("hotel-a", "session-a")["preferences"]) == 2


def test_temporary_preferences_expire_without_becoming_stay_preferences(tmp_path: Path, monkeypatch):
    import app.personalization as module

    store = PersonalizationStore(tmp_path / "temporary.db")
    store.set_guest_state("hotel-a", "session-a", True, "stay")
    preference = extract_preferences("Tonight I only want something cheap.")[0]
    assert preference["persistence"] == "temporary"
    saved = store.save_preference("hotel-a", "session-a", **preference)
    assert saved["source"] == "explicit"
    assert store.context_for("hotel-a", "session-a", "Dinner tonight?")["preferences"][0]["value"] == "Lower-priced options for this occasion"

    now = module._now()
    monkeypatch.setattr(module, "_now", lambda: now + 7 * 3600)
    assert store.list_preferences("hotel-a", "session-a") == []

    preferences = extract_preferences("I normally prefer affordable restaurants.")
    assert preferences and preferences[0]["persistence"] == "stay"


def test_memory_commands_and_explicit_family_context(tmp_path):
    assert preference_commands("What do you remember about me?")[0] == "show"
    assert preference_commands("Don't remember that.")[0] == "forget_last"
    assert preference_commands("Forget my restaurant preferences.") == ("forget_category", "restaurant")
    assert preference_commands("Turn off personalization.")[0] == "disable"
    assert preference_commands("Turn personalization back on.")[0] == "enable"

    family = extract_preferences("I'm traveling with my wife and two kids.")
    assert family == [{
        "category": "travel_party", "value": "Family, including children", "preference_key": "travel_party.current",
        "source": "explicit", "confidence": 1.0, "persistence": "stay",
    }]
    transport = extract_preferences("I normally prefer walking if it's less than 15 minutes.")
    assert transport[0]["category"] == "transportation"
    assert transport[0]["value"] == "Walking up to 15 minutes"

    store = PersonalizationStore(tmp_path / "personalization-planning-test.db")
    store.set_guest_state("hotel-planning", "session-family", True, "stay")
    for item in family + [{"category": "interests", "value": "Coffee", "preference_key": "interests.coffee", "source": "explicit", "confidence": 1.0, "persistence": "stay"}]:
        store.save_preference("hotel-planning", "session-family", **item)
    plan_context = store.context_for("hotel-planning", "session-family", "What can we do this afternoon?")
    assert {item["category"] for item in plan_context["preferences"]} == {"travel_party", "interests"}
    surprise_context = store.context_for("hotel-planning", "session-family", "Surprise me.")
    assert {item["category"] for item in surprise_context["preferences"]} == {"travel_party", "interests"}


def test_guest_controls_api_and_chat_context_respect_consent(admin_client, tmp_path, monkeypatch):
    database = tmp_path / "guest-control.db"
    sessions = SessionStore(database)
    identity_store = GuestIdentityStore(database)
    hospitality = HospitalityStore(database)
    memory_store = PersonalizationStore(database)
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "guest_identities", identity_store)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "personalization", memory_store)
    property_id = main_module.settings.property_id
    started = admin_client.post("/api/session/start", json={"client_id": "personalized-guest", "property_id": property_id})
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    resumed = admin_client.post("/api/session/resume", json={"client_id": "personalized-guest", "session_id": session_id})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["session_id"] == session_id
    wrong_client = admin_client.post("/api/session/resume", json={"client_id": "another-browser", "session_id": session_id})
    assert wrong_client.status_code == 401

    calls = []

    class ModelResult:
        provider = "local"
        model = "test-model"
        text = "Here are a few nearby options."

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return ModelResult()

    async def no_places(*args, **kwargs):
        return []

    monkeypatch.setattr(main_module.ai_models, "concierge_chat", fake_chat)
    monkeypatch.setattr(main_module.places, "search", no_places)

    private_turn = admin_client.post("/api/chat", json={"session_id": session_id, "message": "I'm vegetarian."})
    assert private_turn.status_code == 200, private_turn.text
    assert memory_store.guest_state(property_id, session_id)["preferences"] == []
    assert calls[-1]["guest_context"]["personalization_level"] == "private"
    assert calls[-1]["guest_context"]["preferences"] == []

    enabled = admin_client.put("/api/guest/personalization", json={"session_id": session_id, "enabled": True, "level": "stay"})
    assert enabled.status_code == 200, enabled.text
    learned = admin_client.post("/api/chat", json={"session_id": session_id, "message": "I'm vegetarian."})
    assert learned.status_code == 200, learned.text
    saved_preferences = memory_store.guest_state(property_id, session_id)["preferences"]
    assert any(item["value"] == "vegetarian" for item in saved_preferences), saved_preferences
    recommendation = admin_client.post("/api/chat", json={"session_id": session_id, "message": "Where should we eat?"})
    assert recommendation.status_code == 200, recommendation.text
    context = calls[-1]["guest_context"]
    assert context["personalization_level"] == "stay"
    assert any(item["value"] == "vegetarian" for item in context["personalization"]["preferences"])

    shown = admin_client.post("/api/chat", json={"session_id": session_id, "message": "What do you remember about me?"})
    assert "vegetarian" in shown.json()["answer"]
    disabled = admin_client.post("/api/chat", json={"session_id": session_id, "message": "Turn off personalization."})
    assert "off" in disabled.json()["answer"].casefold()
    assert memory_store.context_for(property_id, session_id, "Restaurant nearby?")["preferences"] == []
    enabled_again = admin_client.post("/api/chat", json={"session_id": session_id, "message": "Turn personalization back on."})
    assert "on" in enabled_again.json()["answer"].casefold()
    assert memory_store.context_for(property_id, session_id, "Restaurant nearby?")["preferences"]

    forgotten = admin_client.post("/api/chat", json={"session_id": session_id, "message": "Forget my dietary preference."})
    assert forgotten.status_code == 200, forgotten.text
    assert memory_store.guest_state(property_id, session_id)["preferences"] == []


def test_admin_personalization_policy_is_property_scoped(admin_client, tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "personalization", PersonalizationStore(tmp_path / "admin-personalization.db"))
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    saved = admin_client.put(
        f"/api/admin/properties/{property_id}/personalization",
        json={"data": {"enabled": True, "default_level": "stay", "allow_preference_learning": False, "allow_guest_profile": True}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["default_level"] == "stay"
    assert saved.json()["allow_preference_learning"] is False
