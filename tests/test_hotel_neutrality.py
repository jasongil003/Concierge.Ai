from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.hospitality import HospitalityStore
from app.operations import OperationsStore
from app.properties import PropertyStore
from app.zones import ZoneStore


def test_first_property_onboarding_starts_empty(tmp_path: Path, monkeypatch, admin_client: TestClient):
    database = tmp_path / "onboarding.db"
    property_store = PropertyStore(database)
    monkeypatch.setattr(main_module, "properties", property_store)
    monkeypatch.setattr(main_module, "hospitality", HospitalityStore(database))
    monkeypatch.setattr(main_module, "zones", ZoneStore(database))
    monkeypatch.setattr(main_module, "operations", OperationsStore(database))

    assert admin_client.get("/api/admin/properties").json()["properties"] == []
    created = admin_client.put(
        "/api/admin/properties/test-property",
        json={"property_id": "test-property", "hotel_name": "Configured Test Property", "timezone": "Asia/Manila"},
    )
    assert created.status_code == 200, created.text
    property_record = property_store.get("test-property")
    assert property_record is not None
    assert property_record.hotel_name == "Configured Test Property"
    assert property_record.design_published["branding"]["hotelName"] == "Configured Test Property"
    assert property_record.design_published["suggestions"] == []

    hospitality = admin_client.get("/api/admin/properties/test-property/hospitality")
    assert hospitality.status_code == 200
    for key in ("facilities", "restaurants", "departments", "services", "recommendations"):
        assert hospitality.json()[key] == []
    zones = admin_client.get("/api/admin/properties/test-property/zones").json()
    assert all(zones[key] == [] for key in ("buildings", "floors", "maps", "zones"))
    knowledge = admin_client.get("/api/admin/properties/test-property/knowledge").json()
    assert all(knowledge[key] == [] for key in ("items", "documents", "faqs"))


def test_app_readiness_succeeds_without_a_property_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "properties", PropertyStore(tmp_path / "unconfigured.db"))
    with TestClient(main_module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["property_setup"] == "onboarding"
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
