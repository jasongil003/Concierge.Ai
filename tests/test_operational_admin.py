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
