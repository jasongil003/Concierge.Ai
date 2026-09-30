from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.hospitality import HospitalityStore
from app.operations import OperationsStore
from app.properties import PropertyStore
from app.zones import ZoneStore


def _install_isolated_app_stores(tmp_path: Path, monkeypatch):
    from dataclasses import replace
    from app.admin_auth import AdminAuthStore
    from app.guest_identity import GuestIdentityStore
    from app.knowledge_management import KnowledgeStore
    from app.personalization import PersonalizationStore
    from app.session_store import SessionStore

    database = tmp_path / "onboarding.db"
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, property_id=""))
    stores = {
        "properties": PropertyStore(database),
        "hospitality": HospitalityStore(database),
        "zones": ZoneStore(database),
        "operations": OperationsStore(database),
        "knowledge_management": KnowledgeStore(database, tmp_path / "uploads"),
        "store": SessionStore(database),
        "guest_identities": GuestIdentityStore(database),
        "personalization": PersonalizationStore(database),
    }
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("admin", "Onboarding-QA-Admin-123!", "QA Administrator")
    stores["admin_auth"] = auth
    for name, value in stores.items():
        monkeypatch.setattr(main_module, name, value)
    return database, stores


def _login(client, password="Onboarding-QA-Admin-123!"):
    response = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": password, "remember_me": False},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"X-CSRF-Token": response.json()["user"]["csrf_token"]})


def _assert_property_content_empty(client, database: Path, property_id: str):
    hospitality = client.get(f"/api/admin/properties/{property_id}/hospitality")
    assert hospitality.status_code == 200, hospitality.text
    data = hospitality.json()
    for key in (
        "facilities", "restaurants", "promotions", "events", "service_requests",
        "notification_rules", "departments", "services", "recommendations",
    ):
        assert data[key] == [], f"{key} unexpectedly contains property content"
    assert data["menus"] == {}

    catalog = client.get(f"/api/admin/properties/{property_id}/service-catalog")
    assert catalog.status_code == 200
    assert catalog.json() == {"departments": [], "services": []}
    zones = client.get(f"/api/admin/properties/{property_id}/zones").json()
    for key in ("buildings", "floors", "maps", "zones", "facilities", "access_points", "navigation_nodes", "navigation_edges"):
        assert zones[key] == [], f"{key} unexpectedly contains property content"
    knowledge = client.get(f"/api/admin/properties/{property_id}/knowledge").json()
    assert all(knowledge[key] == [] for key in ("items", "documents", "faqs"))
    sessions = client.get(f"/api/admin/properties/{property_id}/sessions").json()
    assert all(sessions[key] == [] for key in ("sessions", "stays", "guest_sessions", "devices"))

    profile = client.get(f"/api/admin/properties/{property_id}").json()
    assert profile["rooms"] == []
    assert profile["domain"] == ""
    assert profile["antlabs_config"] == {}
    antlabs = client.get(f"/api/admin/properties/{property_id}/antlabs/status").json()
    assert antlabs["property_authentication_enabled"] is False
    assert antlabs["property_authentication_types"] == []
    deployment = client.get(f"/api/admin/properties/{property_id}/deployment/status").json()
    assert deployment["domain"]["status"] == "not_configured"
    assert deployment["ssl"]["status"] == "not_configured"
    assert deployment["network"]["public_base_url"] == ""
    assert deployment["network"]["status"] == "configuration_required"
    personalization = client.get(f"/api/admin/properties/{property_id}/personalization").json()
    assert personalization["allow_pms_personalization"] is False

    import sqlite3
    counts = {
        "departments": "departments", "services": "service_catalog",
        "facilities": "facility_profiles", "restaurants": "restaurants", "menus": "menus",
        "menu_items": "menu_items", "promotions": "restaurant_promotions",
        "recommendations": "recommendations", "knowledge": "knowledge_items",
        "buildings": "buildings", "floors": "floors", "maps": "floor_maps", "zones": "zones",
        "zone_facilities": "facilities", "access_points": "access_points",
        "navigation_nodes": "navigation_nodes", "navigation_edges": "navigation_edges",
        "events": "hotel_events", "guest_journey_events": "guest_journey_events",
        "managed_knowledge_sources": "km_sources", "managed_knowledge_items": "km_items",
        "knowledge_chunks": "km_chunks", "knowledge_conflicts": "km_conflicts",
        "sessions": "sessions", "service_requests": "service_requests",
        "notification_rules": "notification_rules", "notifications": "notifications",
        "notification_deliveries": "notification_deliveries", "webhooks": "webhooks",
        "webhook_deliveries": "webhook_deliveries", "stays": "concierge_stays",
        "guest_sessions": "guest_sessions", "devices": "device_identities",
    }
    with sqlite3.connect(database) as connection:
        for label, table in counts.items():
            count = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE property_id=?", (property_id,)).fetchone()[0]
            assert count == 0, f"{table} contains {count} unexpected rows"


def test_fresh_install_and_new_property_remain_empty_across_restart(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient

    database, stores = _install_isolated_app_stores(tmp_path, monkeypatch)
    with TestClient(main_module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        _login(client)
        assert client.get("/api/admin/properties").json()["properties"] == []
        assert client.get("/api/hotel").status_code == 404

        created = client.put(
            "/api/admin/properties/qa-empty-property",
            json={"property_id": "qa-empty-property", "hotel_name": "QA Empty Property", "timezone": "Asia/Manila"},
        )
        assert created.status_code == 200, created.text
        property_record = stores["properties"].get("qa-empty-property")
        assert property_record is not None
        assert property_record.hotel_name == "QA Empty Property"
        assert property_record.timezone == "Asia/Manila"
        assert property_record.design_published["branding"]["hotelName"] == "QA Empty Property"
        assert property_record.design_published["suggestions"] == []
        assert property_record.rooms == []
        assert property_record.facilities == []
        assert property_record.dining == []
        assert property_record.policies == []
        assert property_record.contact_details == {}
        assert property_record.support_contacts == []
        assert property_record.quick_actions == []
        assert property_record.guest_modules == []
        assert property_record.personality == {}
        assert property_record.ai_settings == {}
        assert property_record.logo_url == ""
        assert property_record.antlabs_config == {}
        _assert_property_content_empty(client, database, "qa-empty-property")
        public_profile = client.get("/api/hotel")
        assert public_profile.status_code == 200, public_profile.text
        assert public_profile.json()["name"] == "QA Empty Property"
        assert public_profile.json()["rooms"] == []
        assert public_profile.json()["facilities"] == []
        assert public_profile.json()["dining"] == []
        assert public_profile.json()["authentication"]["enabled"] is False
        assert public_profile.json()["authentication"]["enabled_types"] == []

    # Re-entering the application lifespan against the same database models a restart.
    with TestClient(main_module.app) as restarted:
        _login(restarted)
        _assert_property_content_empty(restarted, database, "qa-empty-property")
        guest_session = restarted.post(
            "/api/session/start",
            json={"property_id": "qa-empty-property", "client_id": "qa-empty-guest"},
        )
        assert guest_session.status_code == 200, guest_session.text
        session_id = guest_session.json()["session_id"]
        home = restarted.get(f"/api/guest/home?session_id={session_id}")
        assert home.status_code == 200, home.text
        for key in ("restaurants", "facilities", "promotions", "menu_items", "recommendations"):
            assert home.json()["inventory"][key] == []
        assert home.json()["events"] == []
        assert home.json()["inventory"]["events"] == []
        assert all(card["type"] not in {"restaurant", "facility", "event", "promotion"} for card in home.json()["cards"])
        proposal = restarted.post(
            "/api/guest/actions/propose",
            json={"session_id": session_id, "message": "Can I get extra towels?"},
        )
        assert proposal.status_code == 200, proposal.text
        assert proposal.json()["status"] == "unmatched"
        assert proposal.json()["choices"] == []
        with stores["store"]._connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM service_requests WHERE property_id=?", ("qa-empty-property",)).fetchone()[0] == 0


def test_legacy_catalog_migration_preserves_existing_property_data(tmp_path: Path, monkeypatch):
    import importlib
    import sqlite3
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.admin_auth import AdminAuthStore
    from app.guest_identity import GuestIdentityStore
    from app.knowledge_management import KnowledgeStore
    from app.personalization import PersonalizationStore
    from app.properties import PropertyRecord
    from app.session_store import SessionStore

    database = tmp_path / "legacy-catalog.db"
    properties = PropertyStore(database)
    hospitality = HospitalityStore(database)
    operations = OperationsStore(database)
    ZoneStore(database)
    properties.upsert(PropertyRecord(property_id="legacy-property", hotel_name="Legacy Property"))
    department = hospitality.upsert_department("legacy-property", {"name": "Housekeeping"})
    hospitality.upsert_service("legacy-property", {
        "name": "Extra towels", "department_id": department["department_id"], "keywords": ["towels"],
    })
    custom = hospitality.upsert_service("legacy-property", {
        "name": "Administrator-created service", "keywords": ["custom"],
    })
    hospitality.upsert_facility_profile("legacy-property", {"name": "Configured facility", "facility_type": "amenity"})
    operations.save_knowledge("legacy-property", {"kind": "faq", "question": "Verified FAQ?", "answer": "Verified answer."})

    old_revision = importlib.import_module("migrations.versions.20260928_0001_service_catalog_seed_state")
    new_revision = importlib.import_module("migrations.versions.20260930_0001_remove_service_catalog_seed_state")
    from sqlalchemy import create_engine, text
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            old_revision.upgrade()
            connection.execute(text("INSERT INTO service_catalog_seed_state VALUES (:property_id, :initialized_at)"), {"property_id": "legacy-property", "initialized_at": 123})
            new_revision.upgrade()
        assert connection.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='service_catalog_seed_state'")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM departments WHERE property_id='legacy-property'")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM service_catalog WHERE property_id='legacy-property'")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM facility_profiles WHERE property_id='legacy-property'")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM knowledge_items WHERE property_id='legacy-property'")).scalar_one() == 1
    engine.dispose()

    reopened = HospitalityStore(database)
    assert {item["name"] for item in reopened.catalog("legacy-property")["services"]} == {
        "Extra towels", "Administrator-created service",
    }
    assert reopened.catalog("legacy-property")["departments"][0]["name"] == "Housekeeping"
    assert custom["name"] == "Administrator-created service"

    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("admin", "Legacy-QA-Admin-123!", "QA Administrator")
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, property_id="legacy-property"))
    for name, value in {
        "properties": properties,
        "hospitality": reopened,
        "operations": operations,
        "zones": ZoneStore(database),
        "store": SessionStore(database),
        "guest_identities": GuestIdentityStore(database),
        "personalization": PersonalizationStore(database),
        "knowledge_management": KnowledgeStore(database, tmp_path / "legacy-uploads"),
        "admin_auth": auth,
    }.items():
        monkeypatch.setattr(main_module, name, value)
    with TestClient(main_module.app) as client:
        _login(client, "Legacy-QA-Admin-123!")
        response = client.get("/api/admin/properties/legacy-property/service-catalog")
        assert response.status_code == 200, response.text
        assert {item["name"] for item in response.json()["services"]} == {
            "Extra towels", "Administrator-created service",
        }
        assert [item["name"] for item in response.json()["departments"]] == ["Housekeeping"]


def test_empty_property_guest_facts_are_not_invented(monkeypatch, tmp_path: Path):
    from app.llm import build_prompt
    from app.properties import PropertyRecord

    monkeypatch.setattr(main_module, "hospitality", HospitalityStore(tmp_path / "empty-guest.db"))
    record = PropertyRecord(property_id="qa-empty-property", hotel_name="QA Empty Property", timezone="Asia/Manila")
    assert main_module._property_fast_answer(record, "Where is the pool?") is None
    assert "verified answer" in main_module._concierge_fallback(record).lower()
    system, prompt = build_prompt("Where is the pool?", record.hotel_name, [], guest_context={"stay_context": {"facilities": []}})
    assert "Never invent hours, prices, availability, guest records, locations, or completed actions." in system
    assert "No matching verified hotel facts." in prompt


def test_property_a_content_stays_out_of_empty_property_b(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.properties import PropertyRecord

    database, stores = _install_isolated_app_stores(tmp_path, monkeypatch)
    for property_id, name in (("qa-property-a", "QA Property A"), ("qa-property-b", "QA Property B")):
        stores["properties"].upsert(PropertyRecord(property_id=property_id, hotel_name=name))
    department = stores["hospitality"].upsert_department("qa-property-a", {"name": "A Department"})
    service = stores["hospitality"].upsert_service("qa-property-a", {
        "name": "A Configured Service", "department_id": department["department_id"], "keywords": ["a-service"],
    })
    stores["hospitality"].upsert_facility_profile("qa-property-a", {"name": "A Facility", "facility_type": "amenity"})
    stores["hospitality"].create_restaurant("qa-property-a", {"name": "A Restaurant"})
    stores["operations"].save_knowledge("qa-property-a", {
        "kind": "faq", "question": "A verified question?", "answer": "A verified answer.",
    })

    with TestClient(main_module.app) as client:
        _login(client)
        for path in ("hospitality", "service-catalog"):
            payload = client.get(f"/api/admin/properties/qa-property-b/{path}").json()
            assert "A Department" not in str(payload)
            assert "A Configured Service" not in str(payload)
            assert "A Facility" not in str(payload)
            assert "A Restaurant" not in str(payload)
        assert client.get("/api/admin/properties/qa-property-b/knowledge").json()["faqs"] == []
        cross_delete = client.delete(f"/api/admin/properties/qa-property-b/service-catalog/{service['service_id']}")
        assert cross_delete.status_code == 404
        assert stores["hospitality"].catalog("qa-property-a")["services"][0]["service_id"] == service["service_id"]

        session_b = client.post("/api/session/start", json={
            "property_id": "qa-property-b", "client_id": "qa-b-guest",
        })
        assert session_b.status_code == 200, session_b.text
        session_id = session_b.json()["session_id"]
        home_b = client.get(f"/api/guest/home?session_id={session_id}")
        assert home_b.status_code == 200, home_b.text
        assert all(home_b.json()["inventory"][key] == [] for key in (
            "restaurants", "facilities", "events", "promotions", "menu_items", "recommendations",
        ))
        proposal = client.post("/api/guest/actions/propose", json={
            "session_id": session_id, "message": "Please send the A Configured Service",
        })
        assert proposal.status_code == 200
        assert proposal.json()["status"] == "unmatched"


def test_app_readiness_succeeds_without_a_property_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "properties", PropertyStore(tmp_path / "unconfigured.db"))
    with TestClient(main_module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert set(health.json()) == {"status", "checks"}
        assert client.get("/api/hotel").status_code == 404


def test_property_name_must_not_be_whitespace(admin_client: TestClient):
    response = admin_client.put(
        "/api/admin/properties/blank-name",
        json={"property_id": "blank-name", "hotel_name": "   ", "timezone": "UTC"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Property name is required."


def test_runtime_files_contain_no_retired_demo_property_identity():
    root = Path(__file__).resolve().parents[1]
    source_suffixes = {".css", ".html", ".js", ".json", ".md", ".py", ".toml", ".yaml", ".yml"}
    production_files = []
    for directory in ("app", "data", "scripts", "docs", ".github/workflows"):
        base = root / directory
        if base.exists():
            production_files.extend(path for path in base.rglob("*") if path.is_file() and path.suffix in source_suffixes)
    production_files.extend(root / name for name in (".env.example", "Dockerfile", "docker-compose.yml") if (root / name).exists())
    retired_values = (
        "lunara grand hotel",
        "lunara-mnl-001",
        "aurora bay",
        "88 meridian drive",
        "lunara-property-map",
        "demo-hotel",
        "demo hotel",
        "your-property-id",
        "unconfigured-property",
    )
    for path in production_files:
        contents = path.read_text(encoding="utf-8", errors="ignore").casefold()
        assert not any(value in contents for value in retired_values), f"Retired property data remains in {path.relative_to(root)}"

    runtime_python = [path for path in (root / "app").rglob("*.py") if path.is_file()]
    for path in runtime_python:
        assert "seed_starter_service_catalog" not in path.read_text(encoding="utf-8", errors="ignore"), (
            f"Obsolete catalog seeding remains in runtime module {path.relative_to(root)}"
        )
