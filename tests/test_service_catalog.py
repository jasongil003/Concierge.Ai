from pathlib import Path

import app.main as main_module
from app.hospitality import HospitalityStore
from app.properties import PropertyRecord, PropertyStore


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
        json={"session_id": session["session_id"], "service_id": service.json()["service_id"], "description": "Please send a crib", "room": "412", "confirmed": True},
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


def test_guest_service_request_is_idempotent(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "idempotent-requests.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    service = hospitality.upsert_service(property_id, {"name": "Spa booking", "keywords": ["spa"]})
    session = admin_client.post("/api/session/start", json={"client_id": "idempotent-guest"}).json()
    payload = {
        "session_id": session["session_id"],
        "service_id": service["service_id"],
        "description": "Please book a spa treatment",
        "client_request_id": "spa-request-12345",
        "confirmed": True,
    }
    first = admin_client.post("/api/guest/service-requests", json=payload)
    second = admin_client.post("/api/guest/service-requests", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "created"
    assert second.json()["status"] == "existing"
    assert second.json()["request"]["request_id"] == first.json()["request"]["request_id"]
    assert len(hospitality.overview(property_id)["service_requests"]) == 1


def test_facility_hours_answer_combines_every_requested_facility(monkeypatch):
    record = PropertyRecord(
        property_id="lunara-test",
        hotel_name="Lunara",
        pool={"name": "Infinity Pool", "location": "Level 3", "hours": "06:00-22:00"},
        gym={"name": "Fitness Center", "location": "Level 3", "hours": "24 hours"},
        spa={"name": "Lunara Spa", "location": "Level 3", "hours": "10:00-22:00"},
    )
    answer = main_module._property_fast_answer(record, "What are the pool, gym, and spa hours?")
    assert answer == (
        "Infinity Pool: Level 3; 6:00 AM-10:00 PM. "
        "Fitness Center: Level 3; 24 hours. "
        "Lunara Spa: Level 3; 10:00 AM-10:00 PM."
    )


def test_facility_hours_answer_uses_saved_facility_profiles(tmp_path: Path, monkeypatch):
    store = HospitalityStore(tmp_path / "facility-profiles.db")
    for name, facility_type, hours in (
        ("Infinity Pool", "pool", "06:00-22:00"),
        ("Fitness Center", "fitness", "24 hours"),
        ("Lunara Spa", "spa", "10:00-22:00"),
    ):
        store.upsert_facility_profile("lunara-test", {
            "name": name,
            "facility_type": facility_type,
            "description": f"{name}, Level 3.",
            "opening_hours": {"display": hours},
            "live_status": "open",
        })
    monkeypatch.setattr(main_module, "hospitality", store)
    record = PropertyRecord(property_id="lunara-test", hotel_name="Lunara")

    answer = main_module._property_fast_answer(record, "What are the pool, gym, and spa hours?")

    assert answer is not None
    assert "Infinity Pool" in answer and "6:00 AM-10:00 PM" in answer
    assert "Fitness Center" in answer and "24 hours" in answer
    assert "Lunara Spa" in answer and "10:00 AM-10:00 PM" in answer


def test_follow_up_query_resolves_recent_facility_context():
    history = [
        {"role": "guest", "content": "Where is the pool?"},
        {"role": "assistant", "content": "The pool is on Level 3."},
    ]
    assert main_module._contextual_query("What time does it close?", history).endswith("(follow-up about pool)")


def test_security_and_emergency_answers_are_deterministic():
    assert "emergency services" in main_module._safety_fast_answer("Help, there's a fire.")
    assert "can’t provide" in main_module._safety_fast_answer("What room is John Smith staying in?")


def test_disabled_service_cannot_be_requested(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "disabled.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    service = hospitality.upsert_service(property_id, {"name": "Unavailable", "enabled": False})
    session = admin_client.post("/api/session/start", json={"client_id": "guest-device-2"}).json()
    response = admin_client.post(
        "/api/guest/service-requests",
        json={"session_id": session["session_id"], "service_id": service["service_id"], "description": "Try it", "confirmed": True},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "The selected service is not available."


def test_department_property_isolation(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "isolation.db")
    properties = PropertyStore(tmp_path / "isolation.db")
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "properties", properties)

    dept_a = hospitality.upsert_department("hotel-a", {"name": "Housekeeping"})
    dept_b = hospitality.upsert_department("hotel-b", {"name": "Concierge"})

    catalog_a = hospitality.catalog("hotel-a")
    catalog_b = hospitality.catalog("hotel-b")
    assert len(catalog_a["departments"]) == 1
    assert catalog_a["departments"][0]["name"] == "Housekeeping"
    assert len(catalog_b["departments"]) == 1
    assert catalog_b["departments"][0]["name"] == "Concierge"

    service = hospitality.upsert_service("hotel-a", {"name": "Towels", "department_id": dept_a["department_id"]})
    catalog_a = hospitality.catalog("hotel-a")
    assert len(catalog_a["services"]) == 1
    assert catalog_a["services"][0]["name"] == "Towels"
    catalog_b = hospitality.catalog("hotel-b")
    assert len(catalog_b["services"]) == 0


def test_recommendation_property_isolation(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "rec_isolation.db")
    properties = PropertyStore(tmp_path / "rec_isolation.db")
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "properties", properties)

    hospitality.upsert_recommendation("hotel-a", {"name": "Museum", "category": "attraction"})
    hospitality.upsert_recommendation("hotel-b", {"name": "Beach", "category": "nature"})

    recs_a = hospitality.recommendations("hotel-a")
    recs_b = hospitality.recommendations("hotel-b")
    assert len(recs_a) == 1
    assert recs_a[0]["name"] == "Museum"
    assert len(recs_b) == 1
    assert recs_b[0]["name"] == "Beach"

    assert hospitality.delete_recommendation("hotel-a", recs_a[0]["recommendation_id"])
    assert len(hospitality.recommendations("hotel-a")) == 0
    assert len(hospitality.recommendations("hotel-b")) == 1


def test_service_request_cross_property_access_rejected(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "req_isolation.db")
    properties = PropertyStore(tmp_path / "req_isolation.db")
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "properties", properties)

    service_a = hospitality.upsert_service("hotel-a", {"name": "Towels"})
    session = admin_client.post("/api/session/start", json={"client_id": "guest-cross", "property_id": "hotel-b"}).json()
    response = admin_client.post(
        "/api/guest/service-requests",
        json={"session_id": session["session_id"], "service_id": service_a["service_id"], "description": "Send towels", "confirmed": True},
    )
    assert response.status_code == 422
    assert "not available" in response.json()["detail"].lower()
