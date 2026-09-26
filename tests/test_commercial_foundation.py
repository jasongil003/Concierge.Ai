from pathlib import Path

from fastapi.testclient import TestClient

from app.hospitality import HospitalityStore
from app.main import app
from app.properties import PropertyRecord, PropertyStore
from app.wifi_location import MockWiFiLocationProvider, WiFiClientObservation


def _store(tmp_path: Path) -> HospitalityStore:
    db = tmp_path / "concierge.db"
    properties = PropertyStore(db)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    return HospitalityStore(db)


def test_facility_restaurant_menu_event_guest_visibility(tmp_path: Path):
    store = _store(tmp_path)
    facility = store.upsert_facility_profile(
        "hotel-a",
        {
            "name": "Pool",
            "facility_type": "pool",
            "opening_hours": {"daily": "07:00-21:00"},
            "capacity": 100,
            "live_status": "open",
            "booking_supported": False,
        },
    )
    restaurant = store.create_restaurant(
        "hotel-a",
        {
            "name": "Harbor Kitchen",
            "location": "Ground Floor",
            "meal_periods": ["breakfast", "dinner"],
            "reservation_available": True,
            "status": "open",
        },
    )
    menu = store.create_menu("hotel-a", restaurant["restaurant_id"], {"name": "Dinner", "meal_period": "dinner"})
    item = store.create_menu_item(
        "hotel-a",
        menu["menu_id"],
        {
            "name": "Garden Risotto",
            "price": "PHP 650",
            "dietary_tags": ["vegetarian", "gluten_free"],
            "allergens": ["dairy"],
        },
    )
    store.approve_menu("hotel-a", menu["menu_id"], "manager")
    store.publish_menu("hotel-a", menu["menu_id"], "manager")
    event = store.create_event("hotel-a", {"title": "Poolside Music", "starts_at": 2000, "facility_id": facility["facility_id"]})

    guest = store.guest_facilities("hotel-a")
    assert guest["facilities"][0]["name"] == "Pool"
    assert guest["restaurants"][0]["reservation_available"] is True
    assert guest["menu_items"][0]["name"] == item["name"]
    assert guest["events"][0]["event_id"] == event["event_id"]


def test_restaurant_content_requires_approval_before_guest_publication(tmp_path: Path):
    store = _store(tmp_path)
    restaurant = store.create_restaurant("hotel-a", {"name": "A", "internal_notes": "Never show guests"})
    menu = store.create_menu("hotel-a", restaurant["restaurant_id"], {"name": "Dinner"}, actor_user_id="editor")
    item = store.create_menu_item("hotel-a", menu["menu_id"], {"name": "Soup", "price": "PHP 200"}, actor_user_id="editor")
    assert menu["workflow_status"] == "pending_approval"
    assert store.guest_facilities("hotel-a")["menu_items"] == []
    store.approve_menu("hotel-a", menu["menu_id"], "manager")
    store.publish_menu("hotel-a", menu["menu_id"], "manager")
    assert store.guest_facilities("hotel-a")["menu_items"][0]["item_id"] == item["item_id"]
    assert "internal_notes" not in store.get_restaurant("hotel-a", restaurant["restaurant_id"], guest=True)


def test_menu_property_isolation(tmp_path: Path):
    store = _store(tmp_path)
    restaurant = store.create_restaurant("hotel-a", {"name": "A"})

    try:
        store.create_menu("hotel-b", restaurant["restaurant_id"], {"name": "Wrong"})
    except KeyError:
        pass
    else:
        raise AssertionError("Cross-property restaurant access should be rejected")


def test_service_request_sla_lifecycle_and_feedback(tmp_path: Path):
    store = _store(tmp_path)
    request = store.create_service_request(
        "hotel-a",
        {
            "stay_id": "stay_123",
            "room": "1503",
            "request_type": "towels",
            "description": "Please send two towels.",
            "department": "housekeeping",
            "sla_target_seconds": 900,
        },
    )
    assert request["status"] == "new"
    assert request["sla_state"] in {"within_sla", "warning"}

    delivered = store.update_service_status("hotel-a", request["request_id"], "delivered")
    assert delivered["status"] == "delivered"
    completed = store.update_service_status("hotel-a", request["request_id"], "completed")
    assert completed["completed_at"] is not None
    feedback = store.add_feedback("hotel-a", {"request_id": request["request_id"], "resolution": "yes", "rating": 5})
    assert feedback["resolution"] == "yes"


def test_notification_guardrails_suppress_unverified_or_ineligible_context(tmp_path: Path):
    store = _store(tmp_path)
    promo = store.create_notification_rule(
        "hotel-a",
        {
            "name": "Spa offer",
            "category": "promotional",
            "trigger_type": "manual",
            "template": "Visit the spa today.",
        },
    )
    suppressed = store.evaluate_notification(
        "hotel-a",
        promo["rule_id"],
        "stay_123",
        {"destination_zone_id": "spa", "facility_status": "open"},
        guest_preferences={"promotional_consent": False},
    )
    assert suppressed["allowed"] is False
    assert suppressed["reason"] == "promotional_opt_out"

    operational = store.create_notification_rule(
        "hotel-a",
        {"name": "Pool status", "category": "operational", "trigger_type": "facility_status", "template": "Pool update."},
    )
    closed = store.evaluate_notification(
        "hotel-a",
        operational["rule_id"],
        "stay_123",
        {"destination_zone_id": "pool", "facility_status": "closed"},
        guest_preferences={},
    )
    assert closed["allowed"] is False
    assert closed["reason"] == "facility_not_available"


def test_journey_events_and_wifi_provider_contract(tmp_path: Path):
    store = _store(tmp_path)
    event = store.record_journey_event("hotel-a", {"stay_id": "stay_123", "event_type": "directions.opened", "metadata": {"target": "spa"}})
    assert event["event_type"] == "directions.opened"
    assert event["metadata"]["target"] == "spa"

    provider = MockWiFiLocationProvider()
    provider.add_observation(
        WiFiClientObservation(
            property_id="hotel-a",
            client_identifier="AA:BB:CC:DD:EE:FF",
            access_point_identifier="ap-lobby",
            observed_at=100,
            rssi=-61,
            controller="mock-controller",
        )
    )
    assert provider.current_observations("hotel-a")[0].access_point_identifier == "ap-lobby"
    assert provider.current_observations("hotel-b") == []


def test_commercial_apis_property_scope_and_guest_facilities(admin_client: TestClient):
    client = admin_client
    properties = client.get("/api/admin/properties").json()["properties"]
    property_id = properties[0]["property_id"]

    facility = client.put(
        f"/api/admin/properties/{property_id}/hospitality/facilities",
        json={"data": {"name": "Configured Lounge", "facility_type": "lounge", "live_status": "open"}},
    )
    assert facility.status_code == 200
    guest = client.get("/api/guest/facilities")
    assert guest.status_code == 200
    assert any(item["name"] == "Configured Lounge" for item in guest.json()["facilities"])

    missing = client.put(
        "/api/admin/properties/missing-hotel/hospitality/facilities",
        json={"data": {"name": "Bad"}},
    )
    assert missing.status_code == 404
