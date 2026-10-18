from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

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

    session = admin_client.post("/api/session/start", json={
        "client_id": "guest-device", "property_id": property_id,
    }).json()
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
    assert overview["service_requests"] == []
    request_page = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=all")
    assert request_page.status_code == 200, request_page.text
    assert request_page.json()["service_requests"][0]["request_id"] == request_record["request_id"]
    hospitality.update_service_request(property_id, request_record["request_id"], {"note": "Staff-only follow-up detail."})
    guest_requests = admin_client.get(f"/api/guest/requests?session_id={session['session_id']}")
    assert "Staff-only follow-up detail." not in guest_requests.text
    assert "notes" not in guest_requests.json()["requests"][0]
    cancelled = admin_client.post(
        f"/api/guest/requests/{request_record['request_id']}/cancel",
        json={"session_id": session["session_id"], "confirmed": True},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert "notes" not in cancelled.json()["request"]
    history = admin_client.get(
        f"/api/admin/properties/{property_id}/service-requests/{request_record['request_id']}/history"
    ).json()["history"]
    assert any(event["action"] == "created" for event in history)
    assert any(event["detail"].get("note") == "Staff-only follow-up detail." for event in history)


def test_admin_service_requests_are_filtered_and_paginated_across_the_property(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "paged-requests.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    created = []
    for index in range(55):
        created.append(hospitality.create_service_request(property_id, {
            "description": "Unique Needle in the queue" if index == 0 else f"Routine request {index}",
            "room": "Needle Room" if index == 0 else str(400 + index),
            "department": "Housekeeping",
        }))
    hospitality.update_service_request(property_id, created[0]["request_id"], {"assigned_to": "admin", "priority": "urgent"})
    hospitality.update_service_request(property_id, created[1]["request_id"], {"assigned_to": "Front Desk"})
    completed = hospitality.update_service_status(property_id, created[-1]["request_id"], "completed")
    hospitality.create_service_request("other-property", {"description": "Other property must stay hidden"})

    first = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?limit=10&offset=0&status=all")
    second = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?limit=10&offset=10&status=all")
    assert first.status_code == second.status_code == 200
    first_page, second_page = first.json(), second.json()
    assert first_page["total"] == first_page["all_total"] == 55
    assert len(first_page["service_requests"]) == len(second_page["service_requests"]) == 10
    assert first_page["offset"] == 0 and second_page["offset"] == 10
    expected = sorted(created, key=lambda item: (item["created_at"], item["request_id"]), reverse=True)
    assert [item["request_id"] for item in first_page["service_requests"] + second_page["service_requests"]] == [item["request_id"] for item in expected[:20]]
    assert not ({item["request_id"] for item in first_page["service_requests"]} & {item["request_id"] for item in second_page["service_requests"]})

    searched = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=all&q=unique%20needle")
    assert searched.status_code == 200
    assert searched.json()["total"] == 1
    assert searched.json()["service_requests"][0]["request_id"] == created[0]["request_id"]

    open_page = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=open")
    completed_today = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=completed_today")
    assert open_page.json()["total"] == 54
    assert open_page.json()["summary"]["open"] == 54
    assert completed_today.json()["total"] == 1
    assert completed_today.json()["service_requests"][0]["request_id"] == completed["request_id"]
    assert completed_today.json()["summary"]["completed_today"] == 1
    unassigned = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=all&queue_view=unassigned")
    mine = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=all&queue_view=mine")
    urgent = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=all&queue_view=urgent")
    completed_view = admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=all&queue_view=completed")
    assert unassigned.status_code == mine.status_code == urgent.status_code == completed_view.status_code == 200
    assert unassigned.json()["total"] == 53
    assert mine.json()["total"] == 1 and mine.json()["service_requests"][0]["request_id"] == created[0]["request_id"]
    assert urgent.json()["total"] == 1 and urgent.json()["service_requests"][0]["request_id"] == created[0]["request_id"]
    assert completed_view.json()["total"] == 1 and completed_view.json()["service_requests"][0]["request_id"] == completed["request_id"]
    assert admin_client.get(f"/api/admin/properties/{property_id}/service-requests?limit=101").status_code == 422
    assert admin_client.get(f"/api/admin/properties/{property_id}/service-requests?status=made_up").status_code == 422
    assert admin_client.get(f"/api/admin/properties/{property_id}/service-requests?queue_view=made_up").status_code == 422


def test_overdue_escalations_are_bounded_scoped_and_idempotent(tmp_path: Path):
    store = HospitalityStore(tmp_path / "service-escalations.db")
    store.upsert_department("hotel-a", {"name": "Housekeeping", "escalation_target": "Duty Manager"})
    store.upsert_department("hotel-a", {"name": "Front Desk", "escalation_target": ""})
    store.upsert_department("hotel-a", {"name": "Engineering", "escalation_target": "Chief Engineer", "enabled": False})
    store.upsert_department("hotel-b", {"name": "Housekeeping", "escalation_target": "Hotel B Manager"})

    eligible = store.create_service_request("hotel-a", {"department": "Housekeeping", "description": "Late towels"})
    other_property = store.create_service_request("hotel-b", {"department": "Housekeeping", "description": "Late towels at B"})
    no_target = store.create_service_request("hotel-a", {"department": "Front Desk", "description": "Unrouted"})
    disabled = store.create_service_request("hotel-a", {"department": "Engineering", "description": "Disabled route"})
    future = store.create_service_request("hotel-a", {"department": "Housekeeping", "description": "Not due yet"})
    terminal = store.create_service_request("hotel-a", {"department": "Housekeeping", "description": "Already completed"})
    now = max(item["created_at"] for item in (eligible, other_property, no_target, disabled, future, terminal)) + 600
    with store._connect() as db:
        for request, due_at in (
            (eligible, now - 600),
            (other_property, now - 500),
            (no_target, now - 400),
            (disabled, now - 300),
            (future, now + 60),
            (terminal, now - 100),
        ):
            db.execute("UPDATE service_requests SET due_at=? WHERE property_id=? AND request_id=?", (due_at, request["property_id"], request["request_id"]))
    store.update_service_status("hotel-a", terminal["request_id"], "completed")

    assert store.queue_overdue_service_request_escalations(limit=1, now=now) == 1
    page_a = store.service_request_page("hotel-a", status="all")
    by_id_a = {item["request_id"]: item for item in page_a["service_requests"]}
    assert by_id_a[eligible["request_id"]]["escalation"] == {
        "request_id": eligible["request_id"],
        "target": "Duty Manager",
        "due_at": now - 600,
        "scheduled_at": now,
        "status": "queued",
    }
    assert by_id_a[no_target["request_id"]]["escalation"] is None
    assert by_id_a[disabled["request_id"]]["escalation"] is None
    assert by_id_a[future["request_id"]]["escalation"] is None
    assert by_id_a[terminal["request_id"]]["escalation"] is None
    assert [event["action"] for event in store.request_history("hotel-a", eligible["request_id"])] == [
        "created", "overdue_escalation_queued",
    ]

    assert store.queue_overdue_service_request_escalations(limit=10, now=now) == 1
    page_b = store.service_request_page("hotel-b", status="all")
    assert page_b["service_requests"][0]["request_id"] == other_property["request_id"]
    assert page_b["service_requests"][0]["escalation"]["target"] == "Hotel B Manager"
    assert store.queue_overdue_service_request_escalations(now=now) == 0


def test_concurrent_overdue_escalation_workers_queue_one_event(tmp_path: Path):
    store = HospitalityStore(tmp_path / "concurrent-service-escalations.db")
    store.upsert_department("hotel-a", {"name": "Housekeeping", "escalation_target": "Duty Manager"})
    request = store.create_service_request("hotel-a", {"department": "Housekeeping", "description": "One overdue request"})
    now = request["created_at"] + 600
    with store._connect() as db:
        db.execute("UPDATE service_requests SET due_at=? WHERE property_id=? AND request_id=?", (now - 1, "hotel-a", request["request_id"]))
    barrier = Barrier(8)

    def schedule():
        barrier.wait(timeout=5)
        return store.queue_overdue_service_request_escalations(now=now)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: schedule(), range(8)))

    assert sum(results) == 1
    assert [event["action"] for event in store.request_history("hotel-a", request["request_id"])] == [
        "created", "overdue_escalation_queued",
    ]


def test_guest_service_request_is_idempotent(admin_client, tmp_path: Path, monkeypatch):
    hospitality = HospitalityStore(tmp_path / "idempotent-requests.db")
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    property_id = admin_client.get("/api/admin/properties").json()["properties"][0]["property_id"]
    service = hospitality.upsert_service(property_id, {"name": "Spa booking", "keywords": ["spa"]})
    session = admin_client.post("/api/session/start", json={
        "client_id": "idempotent-guest", "property_id": property_id,
    }).json()
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


def test_concurrent_service_request_retries_return_one_ticket(tmp_path: Path):
    hospitality = HospitalityStore(tmp_path / "concurrent-idempotent-requests.db")
    barrier = Barrier(8)
    payload = {
        "description": "Please send an extra pillow",
        "stay_id": "stay-concurrent",
        "client_request_id": "pillow-request-12345",
    }

    def submit():
        barrier.wait(timeout=5)
        return hospitality.create_service_request("hotel-a", payload)

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(lambda _: submit(), range(8)))

    assert len({response["request_id"] for response in responses}) == 1
    assert sum(bool(response.get("idempotent_replay")) for response in responses) == 7
    assert len(hospitality.overview("hotel-a")["service_requests"]) == 1


def test_facility_hours_answer_combines_every_requested_facility(monkeypatch):
    record = PropertyRecord(
        property_id="property-test",
        hotel_name="Example Hotel",
        pool={"name": "Configured Pool", "location": "Level 3", "hours": "06:00-22:00"},
        gym={"name": "Fitness Center", "location": "Level 3", "hours": "24 hours"},
        spa={"name": "Garden Spa", "location": "Level 3", "hours": "10:00-22:00"},
    )
    answer = main_module._property_fast_answer(record, "What are the pool, gym, and spa hours?")
    assert answer == (
        "Configured Pool: Level 3; 6:00 AM-10:00 PM. "
        "Fitness Center: Level 3; 24 hours. "
        "Garden Spa: Level 3; 10:00 AM-10:00 PM."
    )


def test_facility_hours_answer_uses_saved_facility_profiles(tmp_path: Path, monkeypatch):
    store = HospitalityStore(tmp_path / "facility-profiles.db")
    for name, facility_type, hours in (
        ("Configured Pool", "pool", "06:00-22:00"),
        ("Fitness Center", "fitness", "24 hours"),
        ("Garden Spa", "spa", "10:00-22:00"),
    ):
        store.upsert_facility_profile("property-test", {
            "name": name,
            "facility_type": facility_type,
            "description": f"{name}, Level 3.",
            "opening_hours": {"display": hours},
            "live_status": "open",
        })
    monkeypatch.setattr(main_module, "hospitality", store)
    record = PropertyRecord(property_id="property-test", hotel_name="Example Hotel")

    answer = main_module._property_fast_answer(record, "What are the pool, gym, and spa hours?")

    assert answer is not None
    assert "Configured Pool" in answer and "6:00 AM-10:00 PM" in answer
    assert "Fitness Center" in answer and "24 hours" in answer
    assert "Garden Spa" in answer and "10:00 AM-10:00 PM" in answer


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
