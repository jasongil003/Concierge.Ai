from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.intelligent_ui import GuestExperienceSettings, make_response, validate_guest_experience_settings


def _enable_property_ui(property_id: str = "test-property") -> None:
    record = main_module.properties.get(property_id)
    record.app_settings = {
        **(record.app_settings or {}),
        "guest_experience": {
            "intelligent_ui": {"enabled": True},
            "welcome_message": "Welcome to the test property.",
            "suggested_prompts": ["What time is the pool open?"],
        },
    }
    main_module.properties.upsert(record)


def test_intelligent_guest_settings_reject_unknown_or_loosely_typed_values():
    normalized = validate_guest_experience_settings({
        "intelligent_ui": {"enabled": True},
        "welcome_message": "  Welcome  ",
        "suggested_prompts": ["  Ask about the pool  "],
    })

    assert normalized["intelligent_ui"]["enabled"] is True
    assert normalized["welcome_message"] == "Welcome"
    assert normalized["suggested_prompts"] == ["Ask about the pool"]
    with pytest.raises(ValueError):
        GuestExperienceSettings.model_validate({"intelligent_ui": {"enabled": "true"}})
    with pytest.raises(ValueError):
        GuestExperienceSettings.model_validate({"unknown": "value"})
    with pytest.raises(ValueError):
        GuestExperienceSettings.model_validate({"suggested_prompts": ["x" * 161]})


def test_facility_hours_preserve_configured_meridiem_without_duplicate_suffixes():
    assert main_module._display_hours("6:00 AM to 10:00 PM") == "6:00 AM to 10:00 PM"
    assert main_module._display_hours("06:00 to 22:00") == "6:00 AM to 10:00 PM"


def test_protocol_requires_versioned_allowlisted_blocks_and_stable_ids():
    result = make_response("opaque-conversation", [
        {"id": "text-1", "type": "text", "content": "Pool hours are published as 6 AM to 10 PM."},
        {"id": "suggestions-1", "type": "suggestion_chips", "items": [{"label": "Directions", "prompt": "Where is the pool?"}]},
    ])
    assert result["schema_version"] == "1.0"
    assert result["conversation_id"] == "opaque-conversation"
    assert result["turn_id"]
    assert result["blocks"][0]["content"].startswith("Pool hours")

    with pytest.raises(ValueError):
        make_response("opaque-conversation", [{"id": "unsafe", "type": "script", "content": "alert(1)"}])
    with pytest.raises(ValueError):
        make_response("opaque-conversation", [{"id": "text-1", "type": "text", "content": "hello", "html": "<b>"}])


def test_global_switch_and_property_flag_gate_the_parallel_ui(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=False))

    with TestClient(main_module.app) as client:
        legacy = client.get("/?guest_experience=intelligent")
        assert legacy.status_code == 200
        assert "/static/styles.css" in legacy.text
        assert "/intelligent-ui/styles.css" not in legacy.text
        denied_asset = client.get("/intelligent-ui/styles.css")
        assert denied_asset.status_code == 404
        session = client.post("/api/session/start", json={"client_id": "ui-flag-off", "property_id": "test-property"})
        assert session.status_code == 200, session.text
        denied_chat = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"], "message": "Hello",
        })
        assert denied_chat.status_code == 404

        monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
        enabled_page = client.get("/?experience=legacy")
        assert enabled_page.status_code == 200
        assert "/intelligent-ui/styles.css" in enabled_page.text
        assert client.get("/intelligent-ui/styles.css").status_code == 200
        assert client.get("/api/guest/intelligent-config").json()["welcome_message"] == "Welcome to the test property."

        # A global emergency disable immediately routes new page loads back to legacy.
        monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=False))
        assert "/static/styles.css" in client.get("/").text


def test_intelligent_chat_wraps_legacy_chat_and_only_adds_current_property_restaurants(
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    main_module.hospitality.create_restaurant(
        "test-property",
        {
            "name": "Property Dining Room",
            "cuisine": "Local cuisine",
            "location": "Lobby level",
            "opening_hours": {"display": "5:00 PM–10:00 PM"},
            "description": "Dining inside this hotel.",
        },
    )

    async def fake_existing_chat(_payload, _request):
        return {"answer": "<script>run()</script> Ask me about dinner.", "source": "ai", "places": []}

    monkeypatch.setattr(main_module, "chat", fake_existing_chat)
    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={"client_id": "ui-chat", "property_id": "test-property"})
        assert session.status_code == 200, session.text
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"],
            "message": "Where can I have dinner?",
        })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    text = next(block for block in payload["blocks"] if block["type"] == "text")
    assert text["content"] == "<script>run()</script> Ask me about dinner."
    collection = next(block for block in payload["blocks"] if block["type"] == "card_collection")
    assert [item["title"] for item in collection["cards"]] == ["Property Dining Room"]
    assert "external_reservation_url" not in str(collection)
    assert all("url" not in card for card in collection["cards"])
