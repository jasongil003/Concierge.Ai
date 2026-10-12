import time
import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.hospitality import HospitalityStore
from app.operations import OperationsStore
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


def test_property_managed_rooms_modules_and_ai_policy_round_trip(tmp_path: Path):
    store = PropertyStore(tmp_path / "content.db")
    store.upsert(
        PropertyRecord(
            property_id="hotel-a",
            hotel_name="Hotel A",
            rooms=[{"id": "room_deluxe", "name": "Deluxe", "status": "available"}],
            guest_modules=[{"id": "module_info", "name": "Hotel Information", "enabled": True, "order": 1}],
            personality={"tone": "warm", "response_length": "concise"},
            guardrails={"unknown_answer": "escalate", "restricted_topics": ["payment card data"]},
            app_settings={"default_language": "en"},
        )
    )

    loaded = store.get("hotel-a")
    assert loaded is not None
    assert loaded.rooms[0]["name"] == "Deluxe"
    assert loaded.public_profile["guest_modules"][0]["id"] == "module_info"
    assert loaded.personality["tone"] == "warm"
    assert loaded.guardrails["unknown_answer"] == "escalate"


def test_conversation_retention_sessions_and_usage_are_property_scoped(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db", ttl_minutes=30)
    session_a = store.create("hotel-a", "guest-a")
    store.create("hotel-b", "guest-b")
    store.record_message(session_a.session_id, "hotel-a", "assistant", "Welcome", provider="local", model="qwen", latency_ms=42)

    assert store.set_retention("hotel-a", 14)["retention_days"] == 14
    assert store.retention("hotel-b")["retention_days"] == 30
    assert [item["session_id"] for item in store.sessions("hotel-a")] == [session_a.session_id]
    usage = store.operational_metrics("hotel-a", 7)
    assert usage["requests"] == 1
    assert usage["providers"][0]["model"] == "qwen"


def test_guest_activity_metrics_and_admin_status_follow_credential_expiry(tmp_path: Path):
    store = SessionStore(tmp_path / "guest-expiry.db", ttl_minutes=1)
    session = store.create("hotel-a", "guest-a")
    store.issue_guest_credentials(session.session_id, ttl_seconds=3600)
    now = int(time.time())
    with store._connect() as db:
        db.execute(
            "UPDATE sessions SET last_seen_at=?,guest_token_expires_at=? WHERE session_id=?",
            (now - 600, now + 600, session.session_id),
        )

    assert store.metrics("hotel-a")["active_guests"] == 1
    assert store.sessions("hotel-a")[0]["session_status"] == "active"

    with store._connect() as db:
        db.execute(
            "UPDATE sessions SET guest_token_expires_at=? WHERE session_id=?",
            (now - 1, session.session_id),
        )
    assert store.metrics("hotel-a")["active_guests"] == 0
    assert store.sessions("hotel-a")[0]["session_status"] == "expired"


def test_facility_restaurant_and_department_deletes_are_scoped(tmp_path: Path):
    db = tmp_path / "hospitality.db"
    properties = PropertyStore(db)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    store = HospitalityStore(db)

    department = store.upsert_department("hotel-a", {"name": "Housekeeping"})
    facility = store.upsert_facility_profile("hotel-a", {"name": "Pool", "live_status": "open"})
    restaurant = store.create_restaurant("hotel-a", {"name": "Bistro", "status": "open"})

    assert store.delete_department("hotel-b", department["department_id"]) is False
    assert store.delete_facility_profile("hotel-b", facility["facility_id"]) is False
    assert store.delete_restaurant("hotel-b", restaurant["restaurant_id"]) is False
    assert store.delete_department("hotel-a", department["department_id"]) is True
    assert store.delete_facility_profile("hotel-a", facility["facility_id"]) is True
    assert store.delete_restaurant("hotel-a", restaurant["restaurant_id"]) is True


def test_facility_policy_migration_is_additive_and_preserves_existing_records(tmp_path: Path):
    import sqlite3

    database_path = tmp_path / "legacy-hospitality.db"
    with sqlite3.connect(database_path) as database:
        database.execute("""CREATE TABLE facility_profiles (
            facility_id TEXT PRIMARY KEY, property_id TEXT NOT NULL, zone_id TEXT,
            building_id TEXT, floor_id TEXT, name TEXT NOT NULL, facility_type TEXT NOT NULL,
            opening_hours TEXT NOT NULL DEFAULT '{}', description TEXT NOT NULL DEFAULT '',
            images TEXT NOT NULL DEFAULT '[]', capacity INTEGER,
            booking_supported INTEGER NOT NULL DEFAULT 0, live_status TEXT NOT NULL DEFAULT 'open',
            status_note TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL, created_at INTEGER NOT NULL
        )""")
        database.execute("""INSERT INTO facility_profiles VALUES
            ('pool-1','hotel-a',NULL,NULL,NULL,'Main Pool','pool','{"display":"6 AM–10 PM"}',
             'Guest pool', '["/uploads/pool.webp"]', 30, 0, 'open', '', 100, 90)""")

    store = HospitalityStore(database_path)
    with sqlite3.connect(database_path) as database:
        legacy_columns = [row[1] for row in database.execute("PRAGMA table_info(facility_profiles)")]
        assert len(legacy_columns) == 16
        # A positional INSERT from the prior release still works after upgrade.
        database.execute("""INSERT INTO facility_profiles VALUES
            ('gym-legacy','hotel-a',NULL,NULL,NULL,'Legacy Gym','gym','{}','Existing record','[]',15,0,'open','',101,91)""")
    existing = next(item for item in store.guest_facilities("hotel-a")["facilities"] if item["facility_id"] == "pool-1")
    assert existing["facility_id"] == "pool-1"
    assert existing["opening_hours"] == {"display": "6 AM–10 PM"}
    assert existing["images"] == ["/uploads/pool.webp"]
    assert existing["policies"] == []
    legacy_gym = next(item for item in store.guest_facilities("hotel-a")["facilities"] if item["facility_id"] == "gym-legacy")
    assert legacy_gym["location"] == ""
    assert legacy_gym["policies"] == []

    updated = store.upsert_facility_profile("hotel-a", {
        "facility_id": "pool-1",
        "name": "Main Pool",
        "location": "Level 3, east wing",
        "images": ["/uploads/pool.webp", "https://images.example/pool.webp"],
        "policies": ["Children must be supervised."],
    })
    assert updated["location"] == "Level 3, east wing"
    assert updated["images"] == ["/uploads/pool.webp", "https://images.example/pool.webp"]
    assert updated["policies"] == ["Children must be supervised."]
    reloaded = next(item for item in store.guest_facilities("hotel-a")["facilities"] if item["facility_id"] == "pool-1")
    assert reloaded["facility_id"] == "pool-1"
    assert reloaded["description"] == "Guest pool"
    assert reloaded["location"] == "Level 3, east wing"
    assert reloaded["images"] == ["/uploads/pool.webp", "https://images.example/pool.webp"]
    assert reloaded["policies"] == ["Children must be supervised."]

    with pytest.raises(ValueError, match="identifier is unavailable"):
        store.upsert_facility_profile("hotel-b", {
            "facility_id": "pool-1", "name": "Cross-property overwrite", "policies": ["must not move"],
        })
    assert store.guest_facilities("hotel-b")["facilities"] == []
    pool_after_cross_property_attempt = next(
        item for item in store.guest_facilities("hotel-a")["facilities"] if item["facility_id"] == "pool-1"
    )
    assert pool_after_cross_property_attempt["policies"] == ["Children must be supervised."]

    with pytest.raises(ValueError, match="policies"):
        store.upsert_facility_profile("hotel-a", {
            "facility_id": "pool-1", "name": "Main Pool", "policies": "public access",
        })
    for unsafe_image in ("//attacker.example/image.png", "http://images.example/pool.png", "https://user:pass@images.example/pool.png"):
        with pytest.raises(ValueError, match="image URLs"):
            store.upsert_facility_profile("hotel-a", {
                "facility_id": "pool-1", "name": "Main Pool", "images": [unsafe_image],
            })


def test_operational_endpoints_return_truthful_status(admin_client: TestClient):
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]

    dashboard = admin_client.get(f"/api/admin/properties/{property_id}/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["application"]["version"]
    assert "configured" in dashboard.json()["antlabs"]
    assert "providers" in dashboard.json()["usage"]

    retention = admin_client.put(
        f"/api/admin/properties/{property_id}/conversations/retention",
        json={"retention_days": 21},
    )
    assert retention.status_code == 200
    assert retention.json()["retention_days"] == 21

    antlabs = admin_client.post(f"/api/admin/properties/{property_id}/antlabs/test")
    assert antlabs.status_code == 200
    assert antlabs.json()["status"] in {"simulation", "connected", "not_configured", "unreachable", "authentication_failure", "unsupported_mode"}


def test_operations_console_assistant_and_exports(admin_client: TestClient):
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]

    dashboard = admin_client.get(f"/api/admin/properties/{property_id}/operations/dashboard?period=24h")
    assert dashboard.status_code == 200, dashboard.text
    payload = dashboard.json()
    assert payload["profile"] == "platform"
    assert payload["health"]["components"]
    assert "api_latency_ms" in payload["histories"]
    assert "raw_requests" not in payload["analytics"]
    assert payload["analytics"]["ai"]["estimated_cost"] is None

    assistant = admin_client.post(
        f"/api/admin/properties/{property_id}/assistant/query",
        json={"question": "Restart the database", "period": "24h", "current_page": "system-health"},
    )
    assert assistant.status_code == 200, assistant.text
    assert assistant.json()["tool"] == "check_database"
    assert assistant.json()["confirmation_required"] is True
    assert assistant.json()["action_status"].startswith("No change was made")

    workbook = admin_client.get(f"/api/admin/properties/{property_id}/reports/export.xlsx?period=7d")
    assert workbook.status_code == 200
    assert workbook.content.startswith(b"PK")
    assert "spreadsheetml" in workbook.headers["content-type"]

    report = admin_client.get(f"/api/admin/properties/{property_id}/reports/export.pdf?period=7d")
    assert report.status_code == 200
    assert report.content.startswith(b"%PDF-1.4")


def test_new_operational_admin_and_guest_upload_endpoints(
    admin_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import socket

    monkeypatch.setattr(
        "app.guardrails.socket.getaddrinfo",
        lambda hostname, port, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
    )
    monkeypatch.setattr(main_module, "operations", OperationsStore(tmp_path / "api-operations.db"))
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]

    knowledge = admin_client.put(
        f"/api/admin/properties/{property_id}/knowledge",
        json={"kind": "faq", "question": "Is breakfast included?", "answer": "Check your booked rate."},
    )
    assert knowledge.status_code == 200
    assert admin_client.get(f"/api/admin/properties/{property_id}/knowledge").json()["faqs"][0]["question"] == "Is breakfast included?"

    webhook = admin_client.put(
        f"/api/admin/properties/{property_id}/webhooks",
        json={"name": "Operations", "endpoint_url": "https://example.com/hook", "events": ["guest.request.created"], "secret": "signing-key"},
    )
    assert webhook.status_code == 200
    assert webhook.json()["secret_configured"] is True
    assert "secret" not in webhook.json()

    deployment = admin_client.get(f"/api/admin/properties/{property_id}/deployment/status")
    assert deployment.status_code == 200
    assert deployment.json()["domain"]["status"] in {"not_configured", "invalid", "pending", "verified", "failed"}

    smtp = admin_client.put(
        "/api/admin/system/email",
        json={"host": "", "port": 587, "username": "", "password": "", "from_address": "", "security": "starttls", "enabled": False},
    )
    assert smtp.status_code == 200
    assert smtp.json()["enabled"] is False

    session = admin_client.post("/api/session/start", json={"client_id": "upload-test", "property_id": property_id, "gateway_context": {}})
    upload = admin_client.post(
        "/api/guest/uploads",
        json={
            "session_id": session.json()["session_id"],
            "filename": "note.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"Late arrival at 11 PM").decode(),
        },
    )
    assert upload.status_code == 200
    assert "Late arrival" in upload.json()["message_context"]
