from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.hospitality import HospitalityStore
from app.main import app
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


def test_restaurant_manager_and_staff_are_limited_to_assigned_restaurants(tmp_path: Path, monkeypatch):
    database = tmp_path / "restaurant-workflows.db"
    property_store = PropertyStore(database)
    property_store.upsert(PropertyRecord(
        property_id="hotel-a", hotel_name="Hotel A", domain="testserver",
        ai_settings={"private_provider_note": "not for restaurant users"},
        antlabs_config={"private_gateway_note": "not for restaurant users"},
        guardrails={"antlabs_signature_secret": "must-not-leak"},
    ))
    hospitality = HospitalityStore(database)
    grill = hospitality.create_restaurant("hotel-a", {"name": "The Grill", "internal_notes": "staff note"})
    cafe = hospitality.create_restaurant("hotel-a", {"name": "Lobby Cafe", "internal_notes": "another staff note"})
    pending = hospitality.create_menu("hotel-a", grill["restaurant_id"], {"name": "Dinner"}, actor_user_id="manager")
    hospitality.create_menu_item("hotel-a", pending["menu_id"], {"name": "Steak"}, actor_user_id="manager")
    hospitality.create_promotion("hotel-a", cafe["restaurant_id"], {"title": "Cafe offer"}, actor_user_id="manager")

    sessions = SessionStore(database)
    assigned_session = sessions.create("hotel-a", "guest-assigned")
    hidden_session = sessions.create("hotel-a", "guest-hidden")
    sessions.escalate_conversation(assigned_session.session_id, "hotel-a", grill["restaurant_id"], "Menu question")
    sessions.escalate_conversation(hidden_session.session_id, "hotel-a", cafe["restaurant_id"], "Cafe question")

    auth = AdminAuthStore(database)
    manager = auth.create_user({
        "username": "grill.manager", "display_name": "Grill Manager", "password": "ManagerPass123!",
        "role_id": "role-restaurant-manager", "property_id": "hotel-a", "status": "active",
        "restaurant_ids": [grill["restaurant_id"]],
    }, actor=None)
    staff = auth.create_user({
        "username": "grill.staff", "display_name": "Grill Staff", "password": "StaffMember123!",
        "role_id": "role-restaurant-staff", "property_id": "hotel-a", "status": "active",
        "restaurant_ids": [grill["restaurant_id"]],
    }, actor=None)

    monkeypatch.setattr(main_module, "properties", property_store)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", type("AllowLimiter", (), {"allow": lambda self, *args: True})())
    monkeypatch.setattr(main_module, "security_audit", type("NullAudit", (), {"record": lambda self, *args, **kwargs: None})())

    with TestClient(app) as manager_client:
        manager_login = manager_client.post("/api/admin/auth/login", json={"username": manager["username"], "password": "ManagerPass123!"})
        assert manager_login.status_code == 200
        manager_client.headers["X-CSRF-Token"] = manager_login.json()["user"]["csrf_token"]

        restaurants = manager_client.get("/api/admin/properties/hotel-a/restaurants").json()["restaurants"]
        assert [item["restaurant_id"] for item in restaurants] == [grill["restaurant_id"]]
        assert "internal_notes" not in restaurants[0]
        overview = manager_client.get("/api/admin/properties/hotel-a/hospitality").json()
        assert [item["restaurant_id"] for item in overview["restaurants"]] == [grill["restaurant_id"]]
        assert {item["session_id"] for item in manager_client.get("/api/admin/properties/hotel-a/conversations").json()["conversations"]} == {assigned_session.session_id}

        assert manager_client.get(f"/api/admin/properties/hotel-a/restaurants/{cafe['restaurant_id']}/menus").status_code == 403
        assert manager_client.get(f"/api/admin/properties/hotel-a/restaurants/{cafe['restaurant_id']}/promotions").status_code == 403
        assert manager_client.post(f"/api/admin/properties/hotel-a/conversations/{hidden_session.session_id}/accept").status_code == 403
        assert manager_client.get("/api/admin/properties/hotel-a/sessions").status_code == 403
        assert manager_client.get("/api/admin/properties/hotel-a/operations/dashboard").status_code == 403
        safe_property = manager_client.get("/api/admin/properties/hotel-a").json()
        assert not ({"ai_settings", "antlabs_config", "guardrails"} & set(safe_property))
        assert manager_client.get("/api/admin/properties/other-hotel").status_code == 403

        guest_escalation_session = sessions.create("hotel-a", "guest-escalation")
        guest_escalation = manager_client.post(
            f"/api/guest/conversations/{guest_escalation_session.session_id}/escalate",
            json={"restaurant_id": grill["restaurant_id"], "reason": "Please confirm an allergy question."},
        )
        assert guest_escalation.status_code == 200, guest_escalation.text
        assert guest_escalation.json()["status"] == "waiting_for_staff"

        assignable = manager_client.get(f"/api/admin/properties/hotel-a/restaurants/{grill['restaurant_id']}/staff").json()["staff"]
        assert {item["user_id"] for item in assignable} == {manager["id"], staff["id"]}
        item_id = hospitality.restaurant_menus("hotel-a", grill["restaurant_id"])[0]["items"][0]["item_id"]
        edited = manager_client.put(
            f"/api/admin/properties/hotel-a/menu-items/{item_id}",
            json={"data": {"name": "Steak", "price": "49"}},
        )
        assert edited.status_code == 200, edited.text
        assigned = manager_client.post(
            f"/api/admin/properties/hotel-a/conversations/{assigned_session.session_id}/assign",
            json={"user_id": staff["id"]},
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["assigned_user_id"] == staff["id"]
        assert assigned.json()["state"] == "assigned"
        duplicate_escalation = sessions.escalate_conversation(assigned_session.session_id, "hotel-a", grill["restaurant_id"], "Duplicate guest request")
        assert duplicate_escalation["state"] == "assigned"
        assert duplicate_escalation["assigned_user_id"] == staff["id"]

    with TestClient(app) as staff_client:
        staff_login = staff_client.post("/api/admin/auth/login", json={"username": staff["username"], "password": "StaffMember123!"})
        assert staff_login.status_code == 200
        staff_client.headers["X-CSRF-Token"] = staff_login.json()["user"]["csrf_token"]
        accepted = staff_client.post(f"/api/admin/properties/hotel-a/conversations/{assigned_session.session_id}/accept")
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["state"] == "human_active"
        forbidden_edit = staff_client.put(
            f"/api/admin/properties/hotel-a/menu-items/{item_id}",
            json={"data": {"name": "Unauthorized change"}},
        )
        assert forbidden_edit.status_code == 403
        visible_menus = staff_client.get(f"/api/admin/properties/hotel-a/restaurants/{grill['restaurant_id']}/menus").json()["menus"]
        assert visible_menus == []
        assert staff_client.post(f"/api/admin/properties/hotel-a/menus/{pending['menu_id']}/approve").status_code == 403
        staff_reply = staff_client.post(
            f"/api/admin/properties/hotel-a/conversations/{assigned_session.session_id}/messages",
            json={"message": "I can help with that."},
        )
        assert staff_reply.status_code == 200, staff_reply.text
        assert sessions.staff_messages(assigned_session.session_id, "hotel-a")[0]["sender_user_id"] == staff["id"]
        guest_messages = staff_client.get(f"/api/guest/conversations/{assigned_session.session_id}/staff-messages")
        assert guest_messages.status_code == 200, guest_messages.text
        assert guest_messages.json()["messages"][0]["content"] == "I can help with that."
        paused_chat = staff_client.post("/api/chat", json={"session_id": assigned_session.session_id, "message": "Can I get another detail?", "mode": "fast"})
        assert paused_chat.status_code == 200, paused_chat.text
        assert paused_chat.json()["answer"] == ""
        assert paused_chat.json()["ai_paused"] is True
        resolved = staff_client.post(f"/api/admin/properties/hotel-a/conversations/{assigned_session.session_id}/resolve")
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["state"] == "resolved"


def test_conversation_takeover_is_atomic_and_ai_stays_paused(tmp_path: Path):
    store = SessionStore(tmp_path / "conversation-race.db")
    session = store.create("hotel-a", "guest")
    store.record_message(session.session_id, "hotel-a", "guest", "Please connect me to the restaurant.")
    store.escalate_conversation(session.session_id, "hotel-a", "restaurant-a", "Guest asked for staff")
    assert store.record_ai_message_if_active(session.session_id, "hotel-a", "AI can reply while staff request waits in queue")

    def accept() -> str:
        try:
            store.accept_conversation(session.session_id, "hotel-a", "staff-a")
            return "accepted"
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: accept(), range(2)))
    assert sorted(outcomes) == ["accepted", "conflict"]
    assert store.conversation_state(session.session_id, "hotel-a")["state"] == "human_active"
    assert not store.record_ai_message_if_active(session.session_id, "hotel-a", "AI must stay silent")
    store.return_conversation_to_ai(session.session_id, "hotel-a", "staff-a")
    assert store.record_ai_message_if_active(session.session_id, "hotel-a", "AI resumed")
    store.resolve_conversation(session.session_id, "hotel-a", "manager", allow_unassigned=True)
    assert not store.record_ai_message_if_active(session.session_id, "hotel-a", "AI after resolution")


def test_restaurant_schema_enforces_composite_foreign_keys(tmp_path: Path):
    database = tmp_path / "restaurant-integrity.db"
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    hospitality = HospitalityStore(database)
    restaurant = hospitality.create_restaurant("hotel-a", {"name": "The Grill"})
    menu = hospitality.create_menu("hotel-a", restaurant["restaurant_id"], {"name": "Dinner"})
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("admin", "ChangeMe123!")
    _, principal = auth.login("admin", "ChangeMe123!", "127.0.0.1", "integrity-test")

    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO menus(menu_id,property_id,restaurant_id,name,meal_period,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                ("cross-property-menu", "hotel-b", restaurant["restaurant_id"], "Invalid", "dinner", 1, 1),
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO menu_items(item_id,property_id,menu_id,name,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("cross-property-item", "hotel-b", menu["menu_id"], "Invalid", 1, 1),
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO restaurant_promotions(promotion_id,property_id,restaurant_id,title,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                ("cross-property-promotion", "hotel-b", restaurant["restaurant_id"], "Invalid", 1, 1),
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO user_restaurants(user_id,property_id,restaurant_id,created_at) VALUES(?,?,?,?)",
                (principal.user_id, "hotel-b", restaurant["restaurant_id"], 1),
            )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
