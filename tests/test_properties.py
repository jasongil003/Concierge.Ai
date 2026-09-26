from pathlib import Path

from fastapi.testclient import TestClient

from app.hospitality import HospitalityStore
from app.main import app
from app.operations import OperationsStore
from app.properties import PropertyRecord, PropertyStore, default_design_config
from app.zones import ZoneStore


def test_clean_database_has_no_property_or_operational_seed_data(tmp_path: Path):
    database = tmp_path / "clean.db"
    properties = PropertyStore(database)
    hospitality = HospitalityStore(database)
    zones = ZoneStore(database)
    operations = OperationsStore(database)

    assert properties.list() == []
    overview = hospitality.overview("property-a")
    assert overview["facilities"] == []
    assert overview["restaurants"] == []
    assert overview["departments"] == []
    assert overview["services"] == []
    assert overview["recommendations"] == []
    zone_data = zones.overview("property-a")
    assert zone_data["buildings"] == []
    assert zone_data["floors"] == []
    assert zone_data["maps"] == []
    assert zone_data["zones"] == []
    assert operations.list_knowledge("property-a") == []


def test_property_round_trip_rich_configuration(tmp_path: Path):
    store = PropertyStore(tmp_path / "concierge.db")
    record = PropertyRecord(
        property_id="grand-hotel",
        hotel_name="Grand Hotel",
        description="Downtown business hotel",
        domain="concierge.grandhotel.test",
        deployment_mode="hybrid",
        timezone="Asia/Manila",
        latitude=14.55,
        longitude=121.02,
        address="Makati",
        contact_details={"phone": "+63 2 555 0100"},
        concierge_name="Maya",
        languages=["en", "fil"],
        facilities=[{"name": "Configured workspace"}],
        quick_actions=[{"label": "Checkout", "prompt": "What time is checkout?"}],
        ai_settings={"guest_mode_switch": True, "default_mode": "auto"},
        antlabs_config={"mode": "mock"},
        knowledge_sources=[{"type": "pdf", "name": "Guest directory"}],
    )

    store.upsert(record)
    loaded = store.get("grand-hotel")

    assert loaded is not None
    assert loaded.domain == "concierge.grandhotel.test"
    assert loaded.deployment_mode == "hybrid"
    assert loaded.contact_details["phone"] == "+63 2 555 0100"
    assert loaded.languages == ["en", "fil"]
    assert loaded.public_profile["quick_actions"][0]["label"] == "Checkout"


def test_public_profile_exposes_enabled_authentication_rules(tmp_path: Path):
    store = PropertyStore(tmp_path / "concierge.db")
    record = PropertyRecord(
        property_id="auth-hotel",
        hotel_name="Auth Hotel",
        antlabs_config={
            "authentication_types": {
                "pms": {"label": "PMS / Room Login", "enabled": True},
                "access_code": {"label": "Access Code", "enabled": True},
                "radius": {"label": "RADIUS", "enabled": False},
            }
        },
    )

    store.upsert(record)
    profile = store.get("auth-hotel").public_profile

    enabled = profile["authentication"]["enabled_types"]
    assert [item["id"] for item in enabled] == ["pms", "access_code"]
    assert enabled[0]["fields"] == ["room", "last_name"]
    assert enabled[1]["fields"] == ["access_code"]


def test_start_session_rejects_unknown_property():
    client = TestClient(app)

    response = client.post(
        "/api/session/start",
        json={"client_id": "test-client", "property_id": "missing-hotel"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Property not found."


def test_design_draft_publish_and_restore(tmp_path: Path):
    store = PropertyStore(tmp_path / "concierge.db")
    store.upsert(PropertyRecord(property_id="property-a", hotel_name="Property A"))

    draft = default_design_config(hotel_name="Draft Hotel", concierge_name="Maya")
    draft["welcome"]["headline"] = "Draft headline"
    draft["theme"]["accent"] = "#123456"

    record = store.save_design_draft("property-a", draft)
    assert record.design_draft["welcome"]["headline"] == "Draft headline"
    assert record.design_published["welcome"]["headline"] != "Draft headline"

    published = store.publish_design("property-a")
    assert published.design_published["theme"]["accent"] == "#123456"
    assert published.design_versions[-1]["version"] == 1

    second = default_design_config(hotel_name="Second Hotel", concierge_name="Maya")
    second["welcome"]["headline"] = "Second draft"
    store.save_design_draft("property-a", second)
    store.restore_design_version("property-a", 1)
    restored = store.get("property-a")

    assert restored is not None
    assert restored.design_draft["theme"]["accent"] == "#123456"


def test_design_validation_rejects_bad_theme(tmp_path: Path):
    store = PropertyStore(tmp_path / "concierge.db")
    store.upsert(PropertyRecord(property_id="property-a", hotel_name="Property A"))
    bad = default_design_config()
    bad["theme"]["accent"] = "purple"

    try:
        store.save_design_draft("property-a", bad)
    except ValueError as exc:
        assert "accent" in str(exc)
    else:
        raise AssertionError("Invalid color should be rejected")


def test_guest_hotel_api_uses_published_design(admin_client: TestClient):
    client = admin_client
    properties_response = client.get("/api/admin/properties")
    property_id = properties_response.json()["properties"][0]["property_id"]
    design_response = client.get(f"/api/admin/properties/{property_id}/design").json()
    original_published = design_response["published"]
    design = design_response["draft"]
    design["welcome"]["headline"] = "Draft only headline"

    try:
        draft_response = client.put(
            f"/api/admin/properties/{property_id}/design/draft",
            json={"config": design},
        )
        assert draft_response.status_code == 200
        assert client.get("/api/hotel").json()["design"]["welcome"]["headline"] != "Draft only headline"

        publish_response = client.post(f"/api/admin/properties/{property_id}/design/publish")
        assert publish_response.status_code == 200
        assert client.get("/api/hotel").json()["design"]["welcome"]["headline"] == "Draft only headline"
    finally:
        client.put(
            f"/api/admin/properties/{property_id}/design/draft",
            json={"config": original_published},
        )
        client.post(f"/api/admin/properties/{property_id}/design/publish")
