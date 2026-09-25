from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.ai_providers import AIProviderStore
from app.hospitality import HospitalityStore
from app.main import app
from app.operations import OperationsStore
from app.observability import ObservabilityStore
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


class AllowLimiter:
    @staticmethod
    def allow(*_args, **_kwargs):
        return True


def _scoped_stores(database: Path):
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="testserver"))
    hospitality = HospitalityStore(database)
    housekeeping = hospitality.upsert_department(
        "hotel-a", {"department_id": "housekeeping", "name": "Housekeeping"}
    )
    front_desk = hospitality.upsert_department(
        "hotel-a", {"department_id": "front-desk", "name": "Front Desk"}
    )
    room_service = hospitality.upsert_service(
        "hotel-a", {"service_id": "hk-service", "name": "Extra towels", "department_id": housekeeping["department_id"]}
    )
    concierge = hospitality.upsert_service(
        "hotel-a", {"service_id": "fd-service", "name": "Late checkout", "department_id": front_desk["department_id"]}
    )
    hk_request = hospitality.create_service_request(
        "hotel-a", {"description": "Please bring towels", "department": "Housekeeping", "service_id": room_service["service_id"]}
    )
    fd_request = hospitality.create_service_request(
        "hotel-a", {"description": "Please arrange checkout", "department": "Front Desk", "service_id": concierge["service_id"]}
    )
    return properties, hospitality, housekeeping, room_service, hk_request, fd_request


def test_department_manager_is_scoped_to_its_department_on_request_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    database = tmp_path / "department-rbac.db"
    properties, hospitality, housekeeping, room_service, hk_request, fd_request = _scoped_stores(database)
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "DepartmentRoot123!")
    _, root = auth.login("root", "DepartmentRoot123!", "127.0.0.1", "department-scope")
    manager = auth.create_user(
        {
            "username": "housekeeping.manager",
            "display_name": "Housekeeping Manager",
            "password": "Housekeeping123!",
            "role_id": "role-department-manager",
            "property_id": "hotel-a",
            "department_id": housekeeping["department_id"],
            "status": "active",
        },
        root,
    )
    foreign_manager = auth.create_user(
        {
            "username": "frontdesk.manager",
            "display_name": "Front Desk Manager",
            "password": "FrontDesk123!",
            "role_id": "role-department-manager",
            "property_id": "hotel-a",
            "department_id": "front-desk",
            "status": "active",
        },
        root,
    )

    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", AllowLimiter())
    monkeypatch.setattr(main_module, "store", SessionStore(database))
    monkeypatch.setattr(main_module, "operations", OperationsStore(database))
    monkeypatch.setattr(main_module, "ai_provider_store", AIProviderStore(database))
    monkeypatch.setattr(main_module, "observability", ObservabilityStore(database))

    async def no_webhooks(*_args, **_kwargs):
        return None

    monkeypatch.setattr(main_module, "_dispatch_webhooks", no_webhooks)
    with TestClient(app) as client:
        login = client.post(
            "/api/admin/auth/login",
            json={"username": manager["username"], "password": "Housekeeping123!"},
        )
        assert login.status_code == 200
        csrf = login.json()["user"]["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf

        catalog = client.get("/api/admin/properties/hotel-a/service-catalog")
        assert catalog.status_code == 200
        assert [item["service_id"] for item in catalog.json()["services"]] == [room_service["service_id"]]
        assert [item["department_id"] for item in catalog.json()["departments"]] == [housekeeping["department_id"]]

        assert client.get(
            f"/api/admin/properties/hotel-a/service-requests/{fd_request['request_id']}/history"
        ).status_code == 403
        assert client.put(
            f"/api/admin/properties/hotel-a/service-requests/{fd_request['request_id']}/status",
            json={"status": "in_progress"},
        ).status_code == 403
        assert client.put(
            f"/api/admin/properties/hotel-a/service-requests/{fd_request['request_id']}",
            json={"department": "Housekeeping", "priority": "high"},
        ).status_code == 403
        assert client.post(
            "/api/admin/properties/hotel-a/feedback",
            json={"data": {"request_id": fd_request["request_id"], "resolution": "yes"}},
        ).status_code == 403
        assert client.post(
            "/api/admin/properties/hotel-a/feedback",
            json={"data": {"resolution": "yes"}},
        ).status_code == 403
        assert client.put(
            "/api/admin/properties/hotel-a/departments",
            json={"data": {"department_id": "front-desk", "name": "Other Department"}},
        ).status_code == 403
        assert client.post(
            "/api/admin/properties/hotel-a/notifications/rules",
            json={"data": {"name": "Property wide rule"}},
        ).status_code == 403

        missing_csrf = client.post(
            "/api/admin/properties/hotel-a/service-requests",
            headers={"X-CSRF-Token": "invalid"},
            json={"data": {"description": "A scoped write"}},
        )
        assert missing_csrf.status_code == 403

        wrong_service = client.post(
            "/api/admin/properties/hotel-a/service-requests",
            json={"data": {"service_id": "fd-service", "description": "Cross department"}},
        )
        assert wrong_service.status_code == 403
        wrong_department = client.post(
            "/api/admin/properties/hotel-a/service-requests",
            json={"data": {"department": "Front Desk", "description": "Cross department"}},
        )
        assert wrong_department.status_code == 403

        allowed = client.put(
            f"/api/admin/properties/hotel-a/service-requests/{hk_request['request_id']}/status",
            json={"status": "in_progress"},
        )
        assert allowed.status_code == 200, allowed.text
        wrong_assignee = client.put(
            f"/api/admin/properties/hotel-a/service-requests/{hk_request['request_id']}",
            json={"assigned_to": foreign_manager["id"]},
        )
        assert wrong_assignee.status_code == 403
        overview = client.get("/api/admin/properties/hotel-a/hospitality")
        assert overview.status_code == 403  # hospitality overview requires restaurant.view
        created = client.post(
            "/api/admin/properties/hotel-a/service-requests",
            json={"data": {"service_id": "hk-service", "description": "Another towel request"}},
        )
        assert created.status_code == 200, created.text
        assert created.json()["department"] == "Housekeeping"

        dashboard = client.get("/api/admin/properties/hotel-a/operations/dashboard")
        assert dashboard.status_code == 200, dashboard.text
        dashboard_data = dashboard.json()
        assert dashboard_data["analytics"]["summary"]["service_requests"] == 2
        assert dashboard_data["analytics"]["summary"]["guests_assisted"] == 0
        assert dashboard_data["analytics"]["ai"]["requests"] == 0
        assert dashboard_data["health"]["providers"] == []
        assert dashboard_data["integrations"]["antlabs"]["status"] == "restricted"
        assert all(not values for values in dashboard_data["histories"].values())


def test_department_analytics_do_not_expose_property_wide_metrics(tmp_path: Path):
    database = tmp_path / "department-analytics.db"
    _, hospitality, housekeeping, _, _, _ = _scoped_stores(database)
    sessions = SessionStore(database)
    sessions.create("hotel-a", "guest-session")
    observability = ObservabilityStore(database)

    scoped = observability.property_analytics("hotel-a", "24h", housekeeping["department_id"])
    unscoped = observability.property_analytics("hotel-a", "24h")

    assert scoped["summary"]["service_requests"] == 1
    assert scoped["summary"]["guests_assisted"] == 0
    assert scoped["summary"]["ai_conversations"] == 0
    assert scoped["ai"]["requests"] == 0
    assert scoped["guest_auth"]["attempts"] == 0
    assert scoped["top_questions"] == []
    assert {row["name"] for row in scoped["requests_by_department"]} == {"Housekeeping"}
    assert unscoped["summary"]["service_requests"] == 2

    with pytest.raises(ValueError, match="Department scope is not valid"):
        observability.property_analytics("hotel-a", "24h", "department-from-another-property")


def test_department_manager_assignment_must_belong_to_the_same_property(tmp_path: Path):
    database = tmp_path / "department-assignment.db"
    hospitality = HospitalityStore(database)
    foreign = hospitality.upsert_department(
        "hotel-b", {"department_id": "foreign-department", "name": "Foreign Department"}
    )
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "DepartmentRoot123!")
    _, root = auth.login("root", "DepartmentRoot123!", "127.0.0.1", "department-scope")

    with pytest.raises(ValueError, match="department in the user's property"):
        auth.create_user(
            {
                "username": "misassigned.manager",
                "display_name": "Misassigned Manager",
                "password": "Misassigned123!",
                "role_id": "role-department-manager",
                "property_id": "hotel-a",
                "department_id": foreign["department_id"],
                "status": "active",
            },
            root,
        )
