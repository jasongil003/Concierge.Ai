from pathlib import Path

import app.main as main_module
from app.hospitality import HospitalityStore


def test_catalog_and_recommendations_are_property_scoped_and_persistent(tmp_path: Path):
    path = tmp_path / "hospitality.db"
    store = HospitalityStore(path)
    department = store.upsert_department("hotel-a", {"name": "Housekeeping", "default_sla_minutes": 20})
    service = store.upsert_service(
        "hotel-a",
        {
            "name": "Baby Crib",
            "department_id": department["department_id"],
            "keywords": ["crib", "baby bed"],
            "sla_minutes": 20,
            "confirmation_required": True,
        },
    )
    store.upsert_recommendation(
        "hotel-a",
        {"name": "Museum", "category": "attraction", "map_url": "https://maps.example/museum"},
    )

    reopened = HospitalityStore(path)
    catalog = reopened.catalog("hotel-a", guest=True)
    assert catalog["services"][0]["service_id"] == service["service_id"]
    assert catalog["services"][0]["keywords"] == ["crib", "baby bed"]
    assert reopened.catalog("hotel-b", guest=True) == {"departments": [], "services": []}
    assert reopened.recommendations("hotel-a", guest=True)[0]["name"] == "Museum"
    assert reopened.recommendations("hotel-b", guest=True) == []


def test_guest_confirmation_creates_trackable_request(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "requests.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]

    department = admin_client.put(
        f"/api/admin/properties/{property_id}/departments",
        json={"data": {"name": "Housekeeping", "default_sla_minutes": 20}},
    )
    assert department.status_code == 200, department.text
    service = admin_client.put(
        f"/api/admin/properties/{property_id}/service-catalog",
        json={"data": {"name": "Baby Crib", "department_id": department.json()["department_id"], "keywords": ["crib"], "sla_minutes": 20}},
    )
    assert service.status_code == 200, service.text

    session = admin_client.post("/api/session/start", json={"client_id": "guest-device"}).json()
    created = admin_client.post(
        "/api/guest/service-requests",
        json={"session_id": session["session_id"], "service_id": service.json()["service_id"], "description": "Please send a crib", "room": "412"},
    )
    assert created.status_code == 200, created.text
    request_record = created.json()["request"]
    assert request_record["request_id"].startswith("req_")
    assert request_record["department"] == "Housekeeping"
    assert request_record["sla_target_seconds"] == 1200

    overview = admin_client.get(f"/api/admin/properties/{property_id}/hospitality").json()
    assert overview["service_requests"][0]["request_id"] == request_record["request_id"]
    history = admin_client.get(
        f"/api/admin/properties/{property_id}/service-requests/{request_record['request_id']}/history"
    ).json()["history"]
    assert history[0]["action"] == "created"


def test_disabled_service_cannot_be_requested(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "disabled.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    service = hospitality.upsert_service(property_id, {"name": "Unavailable", "enabled": False})
    session = admin_client.post("/api/session/start", json={"client_id": "guest-device-2"}).json()
    response = admin_client.post(
        "/api/guest/service-requests",
        json={"session_id": session["session_id"], "service_id": service["service_id"], "description": "Try it"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "The selected service is not available."
