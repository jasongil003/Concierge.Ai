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


def test_selection_form_protocol_accepts_typed_fields_and_rejects_unsafe_shapes():
    response = make_response("conversation", [{
        "id": "dining-preferences",
        "type": "selection_form",
        "title": "Dining preferences",
        "fields": [
            {"id": "date", "label": "Date", "input_type": "date", "required": True},
            {"id": "time", "label": "Time", "input_type": "time", "required": True},
            {"id": "quantity", "label": "Quantity", "input_type": "quantity", "minimum": 1, "maximum": 8},
            {"id": "party", "label": "Party size", "input_type": "party_size", "minimum": 1, "maximum": 10},
            {"id": "service", "label": "Preference", "input_type": "service_option", "options": [
                {"label": "Indoor", "value": "indoor"},
                {"label": "Patio", "value": "patio"},
            ]},
        ],
    }], "turn")
    form = response["blocks"][0]
    assert [field["input_type"] for field in form["fields"]] == [
        "date", "time", "quantity", "party_size", "service_option",
    ]
    assert form["options"] == []

    invalid_forms = [
        {"id": "missing-fields", "type": "selection_form", "title": "Choose"},
        {"id": "missing-options", "type": "selection_form", "title": "Choose", "fields": [
            {"id": "service", "label": "Service", "input_type": "service_option"},
        ]},
        {"id": "invalid-range", "type": "selection_form", "title": "Choose", "fields": [
            {"id": "quantity", "label": "Quantity", "input_type": "quantity", "minimum": 8, "maximum": 2},
        ]},
        {"id": "duplicate-fields", "type": "selection_form", "title": "Choose", "fields": [
            {"id": "same", "label": "Date", "input_type": "date"},
            {"id": "same", "label": "Time", "input_type": "time"},
        ]},
        {"id": "unsafe-id", "type": "selection_form", "title": "Choose", "fields": [
            {"id": "service/id", "label": "Service", "input_type": "date"},
        ]},
        {"id": "duplicate-options", "type": "selection_form", "title": "Choose", "fields": [
            {"id": "service", "label": "Service", "input_type": "service_option", "options": [
                {"label": "Indoor", "value": "same"}, {"label": "Patio", "value": "same"},
            ]},
        ]},
    ]
    for form in invalid_forms:
        with pytest.raises(ValueError):
            make_response("conversation", [form], "turn")


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


def test_guest_conversation_intents_route_greetings_and_request_tracking_without_fact_fallbacks():
    assert main_module._is_intelligent_guest_greeting("Hi!")
    assert main_module._is_intelligent_guest_greeting("Good evening")
    assert main_module._is_intelligent_guest_greeting("How are you?")
    assert not main_module._is_intelligent_guest_greeting("Hi, where is the pool?")
    assert main_module._is_intelligent_request_status_request("Where is my service request?")
    assert main_module._is_intelligent_request_status_request("Any update on my request?")
    assert not main_module._is_intelligent_request_status_request("Can I have extra towels?")


def test_request_status_and_directions_are_typed_structured_components():
    response = make_response("conversation", [
        {
            "id": "status-1", "type": "request_status", "title": "Your recent service requests",
            "items": [{
                "name": "Towels", "description": "Two bath towels", "department": "Housekeeping",
                "status": "new", "updated_at": 1791945600,
            }],
        },
        {
            "id": "directions-1", "type": "directions", "title": "Published directions",
            "steps": [
                {"label": "Lobby", "source_ids": ["guest:test-property:map_node:lobby"]},
                {"label": "Pool", "source_ids": ["guest:test-property:map_node:pool"]},
            ],
        },
    ], "turn")
    assert [block["type"] for block in response["blocks"]] == ["request_status", "directions"]
    with pytest.raises(ValueError):
        make_response("conversation", [{
            "id": "bad-status", "type": "request_status", "title": "Requests",
            "items": [{"name": "Towels", "status": "mystery"}],
        }], "turn")


def test_guest_directions_use_only_named_guest_visible_map_nodes(monkeypatch: pytest.MonkeyPatch):
    nodes = [
        {"node_id": "lobby", "label": "Lobby", "guest_visible": True},
        {"node_id": "pool", "label": "Rooftop Pool", "guest_visible": True},
        {"node_id": "private", "label": "Staff Office", "guest_visible": False},
    ]
    monkeypatch.setattr(main_module.zones, "overview", lambda _property_id, guest: {"navigation_nodes": nodes} if guest else {})
    monkeypatch.setattr(main_module.zones, "route", lambda _property_id, start, end, guest: {
        "node_ids": [start, end], "labels": ["Lobby", "Rooftop Pool"], "distance": 12,
    })

    route = main_module._intelligent_guest_directions_block("test-property", "Directions from Lobby to Rooftop Pool")
    assert route is not None
    assert route["type"] == "directions"
    assert [step["label"] for step in route["steps"]] == ["Lobby", "Rooftop Pool"]
    assert route["steps"][1]["source_ids"] == ["guest:test-property:map_node:pool"]
    assert main_module._intelligent_guest_directions_block("test-property", "Where is the pool?") is None
    assert main_module._intelligent_guest_directions_block(
        "test-property", "Directions from Lobby to Rooftop Pool", enabled=False,
    ) is None


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
            "meal_periods": ["dinner"],
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
    assert restaurant["source_ids"] == [
        f"guest:test-property:restaurant:{restaurant['resource_id']}"
    ]
    assert restaurant["resource_id"]
    assert restaurant["image_url"] == "/uploads/property-dining-room.webp"
    assert restaurant["location"] == "Lobby level"
    assert restaurant["opening_hours"] == "5:00 PM–10:00 PM"
    assert restaurant["reservation_url"] == "https://reservations.example.test/book"


def test_dining_cards_match_configured_meal_period_and_show_closed_status(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    restaurants = [
        {"restaurant_id": "breakfast-room", "name": "Breakfast Room", "meal_periods": ["breakfast"], "status": "open"},
        {"restaurant_id": "dinner-room", "name": "Dinner Room", "meal_periods": ["dinner"], "status": "temporarily_closed"},
        {"restaurant_id": "unconfigured-room", "name": "Unconfigured Room", "meal_periods": [], "status": "open"},
        {"restaurant_id": "disabled-room", "name": "Disabled Room", "meal_periods": ["dinner"], "status": "disabled"},
    ]
    monkeypatch.setattr(main_module.hospitality, "guest_facilities", lambda _property_id: {
        "restaurants": restaurants, "menu_items": [],
    })

    async def fake_existing_chat(_payload, _request, **_kwargs):
        return {"answer": "Here are the hotel's published dining choices.", "source": "ai", "places": []}

    monkeypatch.setattr(main_module, "_chat_response", fake_existing_chat)
    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={"client_id": "meal-filter", "property_id": "test-property"})
        assert session.status_code == 200, session.text
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"],
            "message": "Where can I have dinner?",
        })

    assert response.status_code == 200, response.text
    collection = next(block for block in response.json()["blocks"] if block["type"] == "card_collection")
    assert [card["title"] for card in collection["cards"]] == ["Dinner Room"]
    assert "Temporarily closed" in collection["cards"][0]["detail"]
    assert collection["cards"][0]["source_ids"] == ["guest:test-property:restaurant:dinner-room"]


def test_unverified_meal_price_uses_honest_fallback_instead_of_breakfast_hours(monkeypatch: pytest.MonkeyPatch):
    record = main_module.properties.get("test-property")
    record.contact_details = {**(record.contact_details or {}), "breakfast": "Breakfast is served from 7:00 AM."}
    monkeypatch.setattr(main_module.hospitality, "guest_facilities", lambda _property_id: {
        "restaurants": [{"restaurant_id": "breakfast-room", "name": "Breakfast Room", "meal_periods": ["breakfast"]}],
        "menu_items": [],
    })

    fast_answer = main_module._property_fast_answer_with_sources(record, "How much does breakfast cost?")
    grounded = main_module._grounded_hotel_fact_answer(
        "test-property", record, "How much does breakfast cost?", [],
    )

    assert fast_answer is None
    assert "don't have verified pricing" in grounded["answer"]
    assert grounded["claims"] == []


def test_dining_claims_and_menu_sources_stay_with_requested_meal_period(monkeypatch: pytest.MonkeyPatch):
    restaurants = [
        {"restaurant_id": "breakfast-room", "name": "Breakfast Room", "meal_periods": ["breakfast"], "status": "open"},
        {"restaurant_id": "dinner-room", "name": "Dinner Room", "meal_periods": ["dinner"], "status": "open"},
    ]
    menu_items = [
        {"menu_item_id": "breakfast-buffet", "restaurant_id": "breakfast-room", "name": "Breakfast Buffet", "price": "PHP 500"},
        {"menu_item_id": "dinner-menu", "restaurant_id": "dinner-room", "name": "Dinner Set", "price": "PHP 900"},
    ]
    monkeypatch.setattr(main_module.hospitality, "guest_facilities", lambda _property_id: {
        "restaurants": restaurants, "menu_items": menu_items,
    })
    monkeypatch.setattr(main_module.hospitality, "catalog", lambda *_args, **_kwargs: {"services": []})

    dinner_options = main_module._grounded_hotel_fact_answer(
        "test-property", None, "Where can I have dinner?", [],
    )
    dinner_menu = main_module._grounded_hotel_fact_answer(
        "test-property", None, "What is on the dinner menu?", [],
    )

    assert "Dinner Room" in str(dinner_options["claims"])
    assert "Breakfast Room" not in str(dinner_options["claims"])
    assert "menu_item" not in str(dinner_options["claims"])
    assert "Dinner Set" in str(dinner_menu["claims"])
    assert "Breakfast Buffet" not in str(dinner_menu["claims"])
    assert dinner_menu["claims"][-1]["source_ids"] == ["guest:test-property:menu_item:dinner-menu"]


def test_intelligent_menu_shows_only_published_items_and_their_prices(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    restaurant = main_module.hospitality.create_restaurant("test-property", {
        "name": "Harbor Dining", "meal_periods": ["dinner"], "status": "open",
    })
    menu = main_module.hospitality.create_menu("test-property", restaurant["restaurant_id"], {
        "name": "Dinner Menu", "meal_period": "dinner",
    }, actor_user_id="test-admin")
    published_item = main_module.hospitality.create_menu_item("test-property", menu["menu_id"], {
        "name": "Grilled Salmon", "description": "Served with local vegetables.", "price": "PHP 850",
    }, actor_user_id="test-admin")
    hidden_item = main_module.hospitality.create_menu_item("test-property", menu["menu_id"], {
        "name": "Unpublished Dessert", "price": "PHP 1", "available": False,
    }, actor_user_id="test-admin")
    # Adding an item moves a published menu back to review; publish this complete
    # version, leaving the item's availability control as the guest filter.
    main_module.hospitality.approve_menu("test-property", menu["menu_id"], "test-admin")
    main_module.hospitality.publish_menu("test-property", menu["menu_id"], "test-admin")

    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={
            "client_id": "published-menu-guest", "property_id": "test-property",
        })
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"], "message": "What is on the dinner menu?",
        })

    assert response.status_code == 200, response.text
    payload = response.json()
    panel = next(block for block in payload["blocks"] if block["type"] == "details_panel")
    assert [(field["label"], field["value"]) for field in panel["fields"]] == [
        ("Grilled Salmon", "Served with local vegetables. · Price: PHP 850"),
    ]
    claims = [block["content"] for block in payload["blocks"] if block["type"] == "grounded_claim"]
    assert any("Grilled Salmon" in claim and "PHP 850" in claim for claim in claims)
    assert "Unpublished Dessert" not in str(payload)
    assert f"guest:test-property:menu_item:{published_item['item_id']}" in str(payload)


def test_published_knowledge_survives_missing_inventory_and_conflicts_fail_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module.hospitality, "guest_facilities", lambda _property_id: {
        "restaurants": [], "menu_items": [], "facilities": [],
    })
    monkeypatch.setattr(main_module.hospitality, "catalog", lambda *_args, **_kwargs: {"services": []})
    published = [{
        "title": "Dinner menu", "answer": "The published menu lists vegetable curry.",
        "item_id": "menu-faq", "_grounding_type": "knowledge",
    }]
    answer = main_module._grounded_hotel_fact_answer(
        "test-property", None, "What is on the dinner menu?", published,
    )
    assert answer["claims"][0]["content"] == published[0]["answer"]

    conflicting = [
        {**published[0], "answer": "Check-in starts at 2 PM."},
        {**published[0], "answer": "Check-in starts at 3 PM."},
    ]
    answer = main_module._grounded_hotel_fact_answer(
        "test-property", None, "What is the hotel check-in time?", conflicting,
    )
    assert "conflicting published hotel information" in answer["answer"]
    assert answer["claims"] == []


def test_intelligent_response_rejects_fabricated_claims_with_valid_or_missing_sources(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    restaurant = main_module.hospitality.create_restaurant("test-property", {
        "name": "Harbor Dining", "meal_periods": ["dinner"], "status": "open",
        "opening_hours": {"display": "5:00 PM–10:00 PM"},
    })

    async def fabricated_claim(_payload, _request, **_kwargs):
        return {
            "answer": "The hotel pool is free until 11 PM.", "places": [],
            "grounded_claims": [{
                "content": "The hotel pool is free until 11 PM.",
                "source_ids": [f"guest:test-property:restaurant:{restaurant['restaurant_id']}"],
            }],
        }

    monkeypatch.setattr(main_module, "_chat_response", fabricated_claim)
    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={
            "client_id": "fabricated-claim-guest", "property_id": "test-property",
        })
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": session.json()["session_id"], "message": "Where can I have dinner?",
        })

    assert response.status_code == 200, response.text
    blocks = response.json()["blocks"]
    assert len(blocks) == 1 and blocks[0]["type"] == "text"
    assert "couldn't verify" in blocks[0]["content"]


def test_cached_intelligent_turn_does_not_replay_archived_inventory(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    restaurant = main_module.hospitality.create_restaurant("test-property", {
        "name": "Seasonal Dining", "meal_periods": ["dinner"], "status": "open",
    })

    async def current_restaurant_claim(_payload, _request, **_kwargs):
        return {
            "answer": "Here are the dining options currently listed for this hotel.", "places": [],
            "grounded_claims": [{
                "content": "Seasonal Dining", "source_ids": [
                    f"guest:test-property:restaurant:{restaurant['restaurant_id']}",
                ],
            }],
        }

    monkeypatch.setattr(main_module, "_chat_response", current_restaurant_claim)
    turn_id = "stale-turn-001"
    with TestClient(main_module.app) as client:
        session = client.post("/api/session/start", json={
            "client_id": "stale-turn-guest", "property_id": "test-property",
        })
        request_payload = {
            "session_id": session.json()["session_id"],
            "turn_id": turn_id,
            "message": "Where can I have dinner?",
        }
        first = client.post("/api/guest/intelligent-chat", json=request_payload)
        main_module.hospitality.archive_restaurant("test-property", restaurant["restaurant_id"])
        replay = client.post("/api/guest/intelligent-chat", json=request_payload)

    assert first.status_code == 200 and any(block["type"] == "card_collection" for block in first.json()["blocks"])
    assert replay.status_code == 200, replay.text
    blocks = replay.json()["blocks"]
    assert len(blocks) == 1 and "information can change" in blocks[0]["content"]


def test_intelligent_facility_cards_use_only_published_property_facility_data(monkeypatch: pytest.MonkeyPatch):
    _enable_property_ui()
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))
    main_module.hospitality.upsert_facility_profile("test-property", {
        "name": "Rooftop Pool",
        "facility_type": "Pool",
        "description": "A heated rooftop swimming pool.",
        "opening_hours": {"display": "6:00 AM–10:00 PM"},
        "images": ["/uploads/rooftop-pool.webp"],
        "policies": ["Children must be supervised.", "No glass containers."],
        "live_status": "open",
        "status_note": "Open to hotel guests until 10 PM.",
    })
    main_module.hospitality.upsert_facility_profile("other-property", {
        "name": "Other Property Pool",
        "facility_type": "Pool",
        "description": "Must remain property scoped.",
        "opening_hours": {"display": "24 hours"},
        "policies": ["Other-property-only policy."],
        "live_status": "open",
    })
    building = main_module.zones.create_building("test-property", {"name": "Main Building"})
    floor = main_module.zones.create_floor("test-property", {
        "building_id": building["building_id"], "name": "Level 3", "level": 3,
    })
    zone = main_module.zones.upsert_zone("test-property", {
        "floor_id": floor["floor_id"], "name": "Pool Deck",
        "geometry": {"type": "point", "points": [[100, 50]]},
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
    assert pool_card["source_ids"] == [
        f"guest:test-property:facility:{pool_card['resource_id']}"
    ]
    assert pool_card["opening_hours"] == "6:00 AM–10:00 PM"
    assert pool_card["image_url"] == "/uploads/rooftop-pool.webp"
    assert pool_card["policies"] == ["Children must be supervised.", "No glass containers."]
    assert pool_card["location"] == ""
    assert "Open to hotel guests until 10 PM." in pool_card["detail"]
    assert "Other-property-only policy." not in str(pool_card)
    actual_map = next(block for block in response.json()["blocks"] if block["type"] == "map_view")
    assert floor_map["map_id"] in actual_map["map_image_url"]
    assert "test-property" in actual_map["map_image_url"]
    assert [(marker["label"], marker["x_percent"], marker["y_percent"]) for marker in actual_map["markers"]] == [
        ("Rooftop Pool", 50.0, 50.0),
    ]


def test_legacy_published_hotel_claims_have_property_scoped_sources(monkeypatch, tmp_path):
    from app.operations import OperationsStore

    store = OperationsStore(tmp_path / "published-legacy-facts.db")
    store.save_knowledge("property-a", {
        "kind": "faq", "question": "What is the hotel check-in policy?",
        "answer": "Hotel check-in begins at 3 PM.", "enabled": True,
    })
    store.save_knowledge("property-a", {
        "kind": "faq", "question": "Private pool operations",
        "answer": "Pool maintenance starts at 11 PM.", "enabled": False,
    })
    monkeypatch.setattr(main_module, "operations", store)

    matches = store.search_knowledge("property-a", "hotel check-in policy", include_documents=False)
    other_property_matches = store.search_knowledge("property-b", "hotel check-in policy", include_documents=False)
    grounded = main_module._grounded_hotel_fact_answer(
        "property-a", None, "What is the hotel check-in policy?", [
            {**item, "_grounding_type": "legacy_knowledge"} for item in matches
        ],
    )

    assert len(matches) == 1
    assert other_property_matches == []
    assert "Pool maintenance" not in str(matches)
    assert grounded["claims"][0]["source_ids"] == [
        f"guest:property-a:legacy_knowledge:{matches[0]['item_id']}"
    ]


def test_hotel_information_is_a_sourced_property_panel_without_calling_the_model(monkeypatch):
    from app.properties import PropertyRecord

    property_id = "grounding-only-property"
    main_module.properties.upsert(PropertyRecord(property_id=property_id, hotel_name="Grounded House"))
    _enable_property_ui(property_id)
    record = main_module.properties.get(property_id)
    record.hotel_name = "Grounded House"
    record.description = "A quiet property beside the river."
    record.address = "1 Example Road"
    main_module.properties.upsert(record)
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, intelligent_guest_ui_global_enabled=True))

    async def unexpected_model_call(**_kwargs):
        raise AssertionError("Published hotel facts must not be delegated to the language model.")

    monkeypatch.setattr(main_module.ai_models, "concierge_chat", unexpected_model_call)
    with TestClient(main_module.app) as client:
        started = client.post("/api/session/start", json={
            "client_id": "grounded-house-guest", "property_id": property_id,
        })
        assert started.status_code == 200, started.text
        response = client.post("/api/guest/intelligent-chat", json={
            "session_id": started.json()["session_id"], "message": "Tell me about the hotel",
        })

    assert response.status_code == 200, response.text
    payload = response.json()
    panel = next(block for block in payload["blocks"] if block["type"] == "details_panel")
    values = {item["label"]: item["value"] for item in panel["fields"]}
    assert values["Hotel"] == "Grounded House"
    assert values["About"] == "A quiet property beside the river."
    assert values["Address"] == "1 Example Road"
    assert all(source.startswith(f"guest:{property_id}:") for source in panel["source_ids"])


def test_ai_cannot_release_an_unpublished_hotel_price_or_operating_claim(admin_client, monkeypatch):
    from app.properties import PropertyRecord

    property_id = main_module.settings.property_id
    record = main_module.properties.get(property_id) or PropertyRecord(property_id=property_id)
    record.hotel_name = "Synthetic Grounding Hotel"
    main_module.properties.upsert(record)
    session = admin_client.post("/api/session/start", json={
        "client_id": "unsupported-hotel-claims", "property_id": property_id,
    })
    assert session.status_code == 200, session.text

    class UnsupportedModelResult:
        provider = "test-provider"
        model = "test-model"
        text = "Our rooftop pool closes at 10 PM and day passes cost $45."

    async def fake_chat(**_kwargs):
        return UnsupportedModelResult()

    async def no_places(*_args, **_kwargs):
        return []

    monkeypatch.setattr(main_module.ai_models, "concierge_chat", fake_chat)
    monkeypatch.setattr(main_module.places, "search", no_places)

    response = admin_client.post("/api/chat", json={
        "session_id": session.json()["session_id"],
        "message": "Could you help me organize my thoughts?",
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "concierge_contact"
    assert "rooftop pool" not in payload["answer"].casefold()
    assert "$45" not in payload["answer"]


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
    assert "route from your current position is not available yet" in text_block["content"]


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
