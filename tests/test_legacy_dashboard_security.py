"""Direct API regressions for the legacy dashboard's role projections."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.ai_providers import AIProviderStore
from app.hospitality import HospitalityStore
from app.main import app
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


@pytest.fixture
def dashboard_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = tmp_path / "dashboard-boundary.db"
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    hospitality = HospitalityStore(database)
    hospitality.upsert_department("hotel-a", {"department_id": "hk", "name": "Housekeeping"})
    for department in ("Housekeeping", "Front Desk"):
        hospitality.create_service_request("hotel-a", {"description": "Synthetic request", "department": department})
    sessions = SessionStore(database)
    session = sessions.create("hotel-a", "synthetic-client")
    sessions.issue_guest_credentials(session.session_id, ttl_seconds=300)
    sessions.record_message(session.session_id, "hotel-a", "assistant", "Synthetic answer", provider="private-provider", model="private-model", error="PRIVATE-ERROR-SENTINEL")
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "DashboardRoot123!")
    _, root = auth.login("root", "DashboardRoot123!", "127.0.0.1", "pytest")
    custom = auth.save_role({"name": "Dashboard Only", "property_id": "hotel-a", "permissions": ["dashboard.view"]}, root)
    ai_only = auth.save_role({"name": "AI Dashboard", "property_id": "hotel-a", "permissions": ["dashboard.view", "ai.view"]}, root)
    for role, role_id in (("department-manager", "role-department-manager"), ("content-manager", "role-content-manager"), ("property-manager", "role-property-manager"), ("property-administrator", "role-property-administrator"), ("dashboard-only", custom["role_id"]), ("ai-only", ai_only["role_id"])):
        auth.create_user({"username": role, "display_name": role, "password": "DashboardUser123!", "role_id": role_id, "property_id": "hotel-a", "department_id": "hk" if role == "department-manager" else None}, root)
    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "ai_provider_store", AIProviderStore(database))
    return session.session_id


@pytest.mark.parametrize("role", ["department-manager", "content-manager", "dashboard-only"])
def test_legacy_dashboard_does_not_disclose_protected_guest_or_configuration_data(dashboard_boundary, role):
    with TestClient(app) as client:
        login = client.post("/api/admin/auth/login", json={"username": role, "password": "DashboardUser123!"})
        assert login.status_code == 200, login.text
        response = client.get("/api/admin/properties/hotel-a/dashboard")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["active_guests"] is None
        assert payload["ai_requests_today"] is None
        assert payload["ai"] == {"availability": "restricted"}
        assert payload["antlabs"] == {"availability": "restricted"}
        assert payload["usage"] == {"availability": "restricted"}
        assert dashboard_boundary not in response.text
        assert "PRIVATE-ERROR-SENTINEL" not in response.text
        if role == "department-manager":
            assert payload["total_requests"] == 1
            assert payload["auth_attempts_today"] is None
            assert payload["auth_success_rate"] is None
        elif role == "dashboard-only":
            assert payload["total_requests"] is None
            assert payload["auth_attempts_today"] is None
        assert client.get("/api/admin/properties/hotel-b/dashboard").status_code == 403


@pytest.mark.parametrize("username,password", [("root", "DashboardRoot123!"), ("property-manager", "DashboardUser123!"), ("property-administrator", "DashboardUser123!")])
def test_legacy_dashboard_retains_authorized_property_metrics(dashboard_boundary, username, password):
    with TestClient(app) as client:
        login = client.post("/api/admin/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200, login.text
        response = client.get("/api/admin/properties/hotel-a/dashboard")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["active_guests"] == 1
        assert payload["total_requests"] == 2
        assert payload["ai_requests_today"] == 1
        assert "configured" in payload["antlabs"]
        assert payload["usage"]["providers"][0]["model"] == "private-model"
        assert payload["usage"]["recent_activity"][0]["session_id"] == dashboard_boundary


def test_ai_dashboard_permission_does_not_grant_guest_activity_access(dashboard_boundary):
    with TestClient(app) as client:
        assert client.post("/api/admin/auth/login", json={"username": "ai-only", "password": "DashboardUser123!"}).status_code == 200
        response = client.get("/api/admin/properties/hotel-a/dashboard")
        assert response.status_code == 200
        assert response.json()["usage"]["providers"][0]["model"] == "private-model"
        assert "recent_activity" not in response.json()["usage"]
        assert dashboard_boundary not in response.text
        assert "PRIVATE-ERROR-SENTINEL" not in response.text


def test_missing_department_assignment_fails_closed(dashboard_boundary):
    with main_module.hospitality._connect() as db:
        db.execute("DELETE FROM departments WHERE property_id=? AND department_id=?", ("hotel-a", "hk"))
    with TestClient(app) as client:
        assert client.post("/api/admin/auth/login", json={"username": "department-manager", "password": "DashboardUser123!"}).status_code == 200
        assert client.get("/api/admin/properties/hotel-a/dashboard").status_code == 403
