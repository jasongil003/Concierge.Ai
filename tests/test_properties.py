import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.antlabs as antlabs_module
import app.main as main_module
from app.hospitality import HospitalityStore
from app.main import app
from app.operations import OperationsStore
from app.guardrails import GuestHostnameConflict
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


def test_property_store_centrally_rejects_normalized_hostname_and_ip_collisions(tmp_path: Path):
    store = PropertyStore(tmp_path / "hostname-ownership.db")
    store.upsert(
        PropertyRecord(
            property_id="owner",
            hotel_name="Owner",
            domain="XN--MAANA-PTA.EXAMPLE.",
            guardrails={"guest_access_hosts": ["2001:db8::1"]},
        )
    )

    with pytest.raises(GuestHostnameConflict):
        store.upsert(
            PropertyRecord(
                property_id="conflict-idna",
                hotel_name="Conflict IDNA",
                guardrails={"guest_access_hosts": ["mañana.example"]},
            )
        )
    with pytest.raises(GuestHostnameConflict):
        store.upsert(
            PropertyRecord(
                property_id="conflict-ipv6",
                hotel_name="Conflict IPv6",
                domain="2001:0db8:0:0:0:0:0:1",
            )
        )

    duplicate = store.upsert(
        PropertyRecord(
            property_id="owner",
            hotel_name="Owner",
            domain="xn--maana-pta.example",
            guardrails={"guest_access_hosts": ["2001:0db8:0:0:0:0:0:1", "2001:db8::1"]},
        )
    )
    assert duplicate.guardrails["guest_access_hosts"] == ["2001:db8::1"]
    assert store.get("conflict-idna") is None
    assert store.get("conflict-ipv6") is None


def test_concurrent_property_writes_cannot_claim_the_same_guest_host(tmp_path: Path):
    store = PropertyStore(tmp_path / "concurrent-host-ownership.db")

    def claim(property_id: str):
        try:
            store.upsert(
                PropertyRecord(
                    property_id=property_id,
                    hotel_name=property_id,
                    guardrails={"guest_access_hosts": ["race.example.test"]},
                )
            )
            return "saved"
        except GuestHostnameConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("race-a", "race-b")))

    assert sorted(results) == ["conflict", "saved"]
    owners = [record.property_id for record in store.list() if "race.example.test" in record.guardrails.get("guest_access_hosts", [])]
    assert len(owners) == 1


def test_property_logo_upload_is_scoped_validated_and_immediately_saved(admin_client: TestClient):
    property_id = "test-property"
    record = main_module.properties.get(property_id)
    original_logo = record.logo_url
    original_draft = copy.deepcopy(record.design_draft)
    logo = "data:image/png;base64," + base64.b64encode(
        b"\x89PNG\r\n\x1a\nlogo-test"
    ).decode("ascii")

    try:
        response = admin_client.put(
            f"/api/admin/properties/{property_id}/logo",
            json={"logo_url": logo},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"logo_url": logo}
        saved = main_module.properties.get(property_id)
        assert saved.logo_url == logo
        assert saved.design_draft == original_draft

        rejected = admin_client.put(
            f"/api/admin/properties/{property_id}/logo",
            json={"logo_url": "data:image/png;base64," + base64.b64encode(b"not a PNG").decode("ascii")},
        )
        assert rejected.status_code == 422

        removed = admin_client.put(f"/api/admin/properties/{property_id}/logo", json={"logo_url": ""})
        assert removed.status_code == 200
        assert main_module.properties.get(property_id).logo_url == ""
    finally:
        restored = main_module.properties.get(property_id)
        restored.logo_url = original_logo
        main_module.properties.upsert(restored)


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
    assert profile["authentication"]["enabled"] is True
    assert [item["id"] for item in enabled] == ["pms", "access_code"]
    assert enabled[0]["fields"] == ["room", "last_name"]
    assert enabled[1]["fields"] == ["access_code"]


def test_authentication_master_switch_hides_methods_without_erasing_configuration(tmp_path: Path):
    store = PropertyStore(tmp_path / "auth-master.db")
    store.upsert(PropertyRecord(
        property_id="auth-master-hotel",
        hotel_name="Auth Master Hotel",
        antlabs_config={
            "authentication_enabled": False,
            "authentication_types": {"pms": {"label": "PMS / Room Login", "enabled": True}},
        },
    ))

    loaded = store.get("auth-master-hotel")
    assert loaded.public_profile["authentication"] == {"enabled": False, "enabled_types": []}
    assert loaded.antlabs_config["authentication_types"]["pms"]["enabled"] is True

    loaded.antlabs_config["authentication_enabled"] = True
    store.upsert(loaded)
    enabled_profile = store.get("auth-master-hotel").public_profile["authentication"]
    assert enabled_profile["enabled"] is True
    assert [item["id"] for item in enabled_profile["enabled_types"]] == ["pms"]


def test_live_guest_profile_and_auth_api_match_sg5_builtin_processor(tmp_path: Path, monkeypatch):
    store = PropertyStore(tmp_path / "live-auth.db")
    store.upsert(PropertyRecord(
        property_id="test-property",
        hotel_name="SG5 Test Property",
        antlabs_config={
            "authentication_enabled": True,
            "authentication_types": {
                "pms": {"label": "PMS / Room Login", "enabled": True},
                "global_code": {"label": "Global Code", "enabled": True},
            },
        },
    ))
    live_settings = replace(
        main_module.settings,
        antlabs_mode="browser_handoff",
        antlabs_auth_url="https://sg5.example.test/login/main.ant?c=proc",
        antlabs_auth_method="POST",
    )
    monkeypatch.setattr(main_module, "properties", store)
    monkeypatch.setattr(main_module, "settings", live_settings)
    monkeypatch.setattr(
        antlabs_module,
        "settings",
        replace(
            antlabs_module.settings,
            antlabs_mode="browser_handoff",
            antlabs_auth_url="https://sg5.example.test/login/main.ant?c=proc",
            antlabs_auth_method="POST",
            antlabs_room_field="uid",
            antlabs_last_name_field="pwd",
            antlabs_session_field="",
            antlabs_session_context_key="",
            antlabs_passthrough_fields=(),
        ),
    )

    with TestClient(app) as client:
        profile = client.get("/api/hotel")
        assert profile.status_code == 200
        assert [item["id"] for item in profile.json()["authentication"]["enabled_types"]] == ["pms"]

        session = client.post(
            "/api/session/start",
            json={"client_id": "sg5-live-handoff-test", "property_id": "test-property"},
        )
        assert session.status_code == 200
        session_id = session.json()["session_id"]

        handoff = client.post(
            "/api/authenticate",
            json={
                "session_id": session_id,
                "auth_type": "pms",
                "credentials": {"room": "412", "last_name": "Smith"},
            },
        )
        assert handoff.status_code == 200
        assert handoff.json()["status"] == "handoff_required"
        assert handoff.json()["handoff"] == {
            "method": "POST",
            "url": "https://sg5.example.test/login/main.ant?c=proc",
            "fields": {"p": "pms", "uid": "412", "pwd": "Smith"},
        }

        unsupported = client.post(
            "/api/authenticate",
            json={"session_id": session_id, "auth_type": "global_code", "credentials": {"global_code": "sample"}},
        )
        assert unsupported.status_code == 422


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
