from dataclasses import replace
import base64

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.intelligent_ui import GuestExperienceSettings, make_response, validate_guest_experience_settings
from app.operations import OperationsStore


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


def test_global_kill_switch_changes_immediately_through_admin_control(
    admin_client: TestClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "operations", OperationsStore(tmp_path / "dynamic-ui-flag.db"))
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))

    session = admin_client.post("/api/session/start", json={
        "client_id": "dynamic-flag-guest", "property_id": "test-property",
    })
    assert session.status_code == 200, session.text
    assert admin_client.get("/api/guest/intelligent-config").status_code == 200

    disabled = admin_client.put("/api/admin/system/intelligent-ui", json={"enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False
    assert "/static/styles.css" in admin_client.get("/").text
    assert admin_client.get("/intelligent-ui/styles.css").status_code == 404
    assert admin_client.get("/api/guest/intelligent-config").status_code == 404
    assert admin_client.post("/api/guest/intelligent-chat/stream", json={
        "session_id": session.json()["session_id"], "message": "hello",
    }).status_code == 404

    enabled = admin_client.put("/api/admin/system/intelligent-ui", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    assert admin_client.get("/api/guest/intelligent-config").status_code == 200


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
            "images": ["/uploads/property-dining-room.webp"],
            "reservation_available": True,
            "external_reservation_url": "https://reservations.example.test/book",
        },
    )

    async def fake_existing_chat(_payload, _request, **_kwargs):
        return {"answer": "<script>run()</script> Ask me about dinner.", "source": "ai", "places": []}

    monkeypatch.setattr(main_module, "_chat_response", fake_existing_chat)
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
    restaurant = collection["cards"][0]
    assert restaurant["resource_id"]
    assert restaurant["image_url"] == "/uploads/property-dining-room.webp"
    assert restaurant["location"] == "Lobby level"
    assert restaurant["opening_hours"] == "5:00 PM–10:00 PM"
    assert restaurant["reservation_url"] == "https://reservations.example.test/book"


def test_intelligent_facility_cards_use_only_published_property_facility_data(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    main_module.hospitality.upsert_facility_profile("test-property", {
        "name": "Rooftop Pool",
        "facility_type": "Pool",
        "description": "A heated rooftop swimming pool.",
        "opening_hours": {"display": "6:00 AM–10:00 PM"},
        "images": ["/uploads/rooftop-pool.webp"],
        "live_status": "open",
    })
    main_module.hospitality.upsert_facility_profile("other-property", {
        "name": "Other Property Pool",
        "facility_type": "Pool",
        "description": "Must remain property scoped.",
        "opening_hours": {"display": "24 hours"},
        "live_status": "open",
    })

    async def fake_existing_chat(_payload, _request, **_kwargs):
        return {"answer": "The pool is on the rooftop.", "source": "ai", "places": []}

    monkeypatch.setattr(main_module, "_chat_response", fake_existing_chat)
    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={"client_id": "ui-facility", "property_id": "test-property"})
        assert session.status_code == 200, session.text
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"],
            "message": "What are the pool hours?",
        })
    assert response.status_code == 200, response.text
    cards = next(block["cards"] for block in response.json()["blocks"] if block["type"] == "card_collection")
    titles = [card["title"] for card in cards]
    assert "Rooftop Pool" in titles
    assert "Other Property Pool" not in titles
    pool_card = next(card for card in cards if card["title"] == "Rooftop Pool")
    assert pool_card["opening_hours"] == "6:00 AM–10:00 PM"
    assert pool_card["image_url"] == "/uploads/rooftop-pool.webp"


def test_intelligent_map_uses_property_floor_plan_and_guest_visible_nodes(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    building = main_module.zones.create_building("test-property", {"name": "Main Building"})
    floor = main_module.zones.create_floor("test-property", {
        "building_id": building["building_id"], "name": "Level 3", "level": 3,
    })
    zone = main_module.zones.upsert_zone("test-property", {
        "floor_id": floor["floor_id"], "name": "Pool Deck", "geometry": {"type": "point", "points": [[100, 50]]},
    })
    raw_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="#eee"/></svg>'
    floor_map = main_module.zones.save_floor_map("test-property", floor["floor_id"], {
        "filename": "level-3.svg", "content_type": "image/svg+xml",
        "content_base64": base64.b64encode(raw_svg).decode(), "width": 200, "height": 100,
    })
    main_module.zones.create_node("test-property", {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"],
        "label": "Rooftop Pool", "x": 100, "y": 50, "node_type": "service", "guest_visible": True,
    })
    main_module.zones.create_node("test-property", {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"],
        "label": "Hidden Back Office", "x": 180, "y": 80, "node_type": "service", "guest_visible": False,
    })

    async def fake_existing_chat(_payload, _request, **_kwargs):
        return {"answer": "The pool is on Level 3.", "source": "ai", "places": []}

    monkeypatch.setattr(main_module, "_chat_response", fake_existing_chat)
    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={"client_id": "ui-map", "property_id": "test-property"})
        assert session.status_code == 200, session.text
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"], "message": "How do I get to the pool?",
        })
    assert response.status_code == 200, response.text
    map_block = next(block for block in response.json()["blocks"] if block["type"] == "map_view")
    assert floor_map["map_id"] in map_block["map_image_url"]
    assert "test-property" in map_block["map_image_url"]
    assert [(marker["label"], marker["x_percent"], marker["y_percent"]) for marker in map_block["markers"]] == [
        ("Rooftop Pool", 50.0, 50.0),
    ]
    text_block = next(block for block in response.json()["blocks"] if block["type"] == "text")
    assert "verified route from your current room is not available" in text_block["content"]


def test_map_helper_returns_no_map_without_published_floor_map_or_markers():
    assert main_module._intelligent_guest_floor_map_block("empty-property", "How do I get to the pool?") is None


def test_map_component_rejects_untrusted_map_urls_and_invalid_markers():
    valid = {
        "id": "floor-map", "type": "map_view", "title": "Level 3",
        "map_image_url": "/api/guest/floor-maps/map-1/asset?property_id=test-property",
        "map_alt": "Floor plan with the pool marked.", "image_width": 200, "image_height": 100,
        "markers": [{"id": "pool-node", "label": "Pool", "x_percent": 50, "y_percent": 50}],
    }
    assert make_response("session", [valid])["blocks"][0]["map_image_url"] == valid["map_image_url"]
    with pytest.raises(ValueError):
        make_response("session", [{**valid, "map_image_url": "https://maps.example/floor.png"}])
    with pytest.raises(ValueError):
        make_response("session", [{**valid, "markers": [{"id": "bad", "label": "Bad", "x_percent": 150, "y_percent": 50}]}])


def test_streaming_route_orders_typed_events_and_server_restores_encrypted_idempotent_turn(
    monkeypatch: pytest.MonkeyPatch,
):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    calls = 0

    async def fake_composer(payload, _request, *, stream_callback=None):
        nonlocal calls
        calls += 1
        if stream_callback:
            await stream_callback("A" * 180)
        return make_response(payload.session_id, [
            {"id": "reply-text", "type": "text", "content": "A" * 180},
        ], payload.turn_id)

    monkeypatch.setattr(main_module, "_compose_intelligent_guest_response", fake_composer)
    with TestClient(main_module.app) as client:
        started = client.post("/api/session/start", json={
            "client_id": "streaming-ui-guest", "property_id": "test-property",
        })
        assert started.status_code == 200, started.text
        session_id = started.json()["session_id"]
        body = {
            "session_id": session_id,
            "turn_id": "stable-turn-1",
            "message": "Tell me something useful.",
        }
        streamed = client.post("/api/guest/intelligent-chat/stream", json=body)
        assert streamed.status_code == 200, streamed.text
        event_types = [
            line.removeprefix("event: ")
            for line in streamed.text.splitlines()
            if line.startswith("event: ")
        ]
        assert event_types[0] == "turn.started"
        assert event_types.count("text.delta") == 2
        assert event_types[-2:] == ["text.completed", "turn.completed"]
        event_ids = [line.removeprefix("id: ") for line in streamed.text.splitlines() if line.startswith("id: ")]
        assert event_ids == [f"stable-turn-1:{number}" for number in range(1, len(event_ids) + 1)]

        history = client.get("/api/guest/intelligent-history", headers={"X-Concierge-Session": session_id})
        assert history.status_code == 200, history.text
        assert history.json()["turns"][0]["message"] == body["message"]
        assert history.json()["turns"][0]["response"]["blocks"][0]["content"] == "A" * 180

        duplicate = client.post("/api/guest/intelligent-chat", json=body)
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["turn_id"] == body["turn_id"]
        assert calls == 1
        mismatch = client.post("/api/guest/intelligent-chat", json={**body, "message": "A different request"})
        assert mismatch.status_code == 409

        with main_module.store._connect() as db:
            saved = db.execute(
                "SELECT encrypted_message,encrypted_response FROM guest_ui_turns WHERE session_id=? AND turn_id=?",
                (session_id, body["turn_id"]),
            ).fetchone()
            saved_transcript = db.execute(
                "SELECT content FROM conversation_messages WHERE session_id=? AND role='guest' ORDER BY created_at,message_id LIMIT 1",
                (session_id,),
            ).fetchone()
        assert body["message"] not in saved["encrypted_message"]
        assert "A" * 30 not in saved["encrypted_response"]
        assert saved_transcript["content"].startswith("fernet:v1:")
        assert body["message"] not in saved_transcript["content"]
        assert main_module.store.recent_messages(session_id, "test-property", limit=2)[0]["content"] == body["message"]

        ended = client.post("/api/session/end", json={
            "client_id": "streaming-ui-guest", "session_id": session_id,
        })
        assert ended.status_code == 200, ended.text
        second = client.post("/api/session/start", json={
            "client_id": "another-stream-guest", "property_id": "test-property",
        })
        assert second.status_code == 200, second.text
        denied_other_guest = client.get(
            "/api/guest/intelligent-history", headers={"X-Concierge-Session": session_id},
        )
        assert denied_other_guest.status_code in {401, 403}
        main_module.store.revoke_guest_credentials(second.json()["session_id"])
        denied_revoked = client.get(
            "/api/guest/intelligent-history",
            headers={"X-Concierge-Session": second.json()["session_id"]},
        )
        assert denied_revoked.status_code in {401, 403}


@pytest.mark.parametrize("message", [
    "Could someone bring me two extra towels?",
    "We are running out of shampoo.",
    "Please arrange housekeeping after lunch.",
    "Can I get three pillows?",
    "I need someone to check the air conditioning.",
])
def test_natural_service_request_phrases_use_confirmed_action_path(message: str):
    assert main_module._is_guest_service_request(message)


@pytest.mark.parametrize("message", [
    "Where can I eat with my family?",
    "I want dinner for two tomorrow.",
    "What restaurants are still open?",
    "Can I get breakfast at 7?",
])
def test_dining_questions_are_not_routed_as_hotel_service_actions(message: str):
    assert not main_module._is_guest_service_request(message)
