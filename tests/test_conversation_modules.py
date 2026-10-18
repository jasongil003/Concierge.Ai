from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.hospitality import HospitalityStore
from app.properties import PropertyRecord, PropertyStore


def _module_api(property_id: str) -> str:
    return f"/api/admin/properties/{property_id}/conversation-modules"


def _config(name: str, prompt: str) -> dict:
    return {
        "name": name,
        "description": "Synthetic test action",
        "icon": "sparkles",
        "category": "Support",
        "group": "Concierge",
        "display_style": "suggestion_chip",
        "order": 0,
        "enabled": True,
        "action": {"type": "prompt", "prompt": prompt},
    }


@pytest.fixture
def isolated_module_property(tmp_path, monkeypatch):
    store = PropertyStore(tmp_path / "module-properties.db")
    store.upsert(PropertyRecord(property_id="test-property", hotel_name="Synthetic Property"))
    monkeypatch.setattr(main_module, "properties", store)
    return store


def test_module_drafts_publish_versions_and_rollback_are_property_scoped(admin_client: TestClient, isolated_module_property):
    property_id = "test-property"
    root = _module_api(property_id)
    created = admin_client.post(root, json={"config": _config("Dining help", "Help me explore dining.")})
    assert created.status_code == 200, created.text
    module = created.json()["module"]
    module_id = module["id"]
    assert module["status"] == "draft"
    assert module["published_version"] == 0
    assert all(item["id"] != module_id for item in main_module.properties.get(property_id).public_profile["guest_modules"])

    published = admin_client.post(f"{root}/{module_id}/publish", json={"expected_revision": module["revision"]})
    assert published.status_code == 200, published.text
    module = published.json()["module"]
    assert module["status"] == "published"
    assert module["published_version"] == 1
    profile_module = next(item for item in main_module.properties.get(property_id).public_profile["guest_modules"] if item["id"] == module_id)
    assert profile_module["action"] == {"type": "prompt", "prompt": "Help me explore dining."}

    updated = admin_client.put(
        f"{root}/{module_id}",
        json={"config": _config("Dining help", "Show me the property dining options."), "expected_revision": module["revision"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["module"]["status"] == "draft"
    assert next(item for item in main_module.properties.get(property_id).public_profile["guest_modules"] if item["id"] == module_id)["action"]["prompt"] == "Help me explore dining."

    republished = admin_client.post(f"{root}/{module_id}/publish", json={"expected_revision": updated.json()["module"]["revision"]})
    assert republished.status_code == 200, republished.text
    module = republished.json()["module"]
    assert module["published_version"] == 2
    assert module["history"][0]["version"] == 1

    restored = admin_client.post(
        f"{root}/{module_id}/rollback",
        json={"version": 1, "expected_revision": module["revision"]},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["module"]["status"] == "draft"
    assert restored.json()["module"]["action"]["prompt"] == "Help me explore dining."
    assert next(item for item in main_module.properties.get(property_id).public_profile["guest_modules"] if item["id"] == module_id)["action"]["prompt"] == "Show me the property dining options."

    other_id = "other-test-property"
    main_module.properties.upsert(PropertyRecord(property_id=other_id, hotel_name="Other Synthetic Property"))
    assert admin_client.get(_module_api(other_id)).json()["modules"] == []
    assert admin_client.put(
        f"{_module_api(other_id)}/{module_id}",
        json={"config": _config("Cross property", "Not allowed."), "expected_revision": 1},
    ).status_code == 404


def test_module_validation_rejects_unknown_actions_and_unapproved_urls(admin_client: TestClient, isolated_module_property):
    root = _module_api("test-property")
    invalid_type = _config("Invalid action", "Hello")
    invalid_type["action"] = {"type": "admin_operation", "operation": "delete_guest"}
    assert admin_client.post(root, json={"config": invalid_type}).status_code == 422

    unsafe_url = _config("Unsafe link", "Open the map")
    unsafe_url["action"] = {"type": "external_url", "url": "javascript:alert(1)"}
    assert admin_client.post(root, json={"config": unsafe_url}).status_code == 422

    unknown_setting = _config("Unknown field", "Hello")
    unknown_setting["backend_operation"] = "delete"
    assert admin_client.post(root, json={"config": unknown_setting}).status_code == 422


def test_incomplete_configuration_saves_privately_but_cannot_publish(admin_client: TestClient, isolated_module_property):
    root = _module_api("test-property")
    config = _config("Request service", "")
    config["action"] = {"type": "service_request"}
    created = admin_client.post(root, json={"config": config})
    assert created.status_code == 200, created.text
    module = created.json()["module"]
    assert module["status"] == "draft"
    assert module["action"] == {"type": "service_request"}
    publish = admin_client.post(f"{root}/{module['id']}/publish", json={"expected_revision": module["revision"]})
    assert publish.status_code == 422
    assert all(item["id"] != module["id"] for item in main_module.properties.get("test-property").public_profile["guest_modules"])


def test_service_action_requires_an_enabled_service_from_the_same_property(admin_client: TestClient, isolated_module_property, tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "hospitality", HospitalityStore(tmp_path / "module-catalog.db"))
    property_id = "test-property"
    department = admin_client.put(
        f"/api/admin/properties/{property_id}/departments",
        json={"data": {"name": "Housekeeping", "default_sla_minutes": 20}},
    )
    assert department.status_code == 200, department.text
    service = admin_client.put(
        f"/api/admin/properties/{property_id}/service-catalog",
        json={"data": {"name": "Extra pillows", "department_id": department.json()["department_id"], "sla_minutes": 20}},
    )
    assert service.status_code == 200, service.text
    root = _module_api(property_id)
    summaries = admin_client.get(root).json()["services"]
    assert summaries == [{"service_id": service.json()["service_id"], "name": "Extra pillows", "department": "Housekeeping"}]

    config = _config("Extra pillows", "")
    config["action"] = {"type": "service_request", "service_id": "service_elsewhere"}
    assert admin_client.post(root, json={"config": config}).status_code == 422
    config["action"]["service_id"] = service.json()["service_id"]
    created = admin_client.post(root, json={"config": config})
    assert created.status_code == 200, created.text
    published = admin_client.post(f"{root}/{created.json()['module']['id']}/publish", json={"expected_revision": 1})
    assert published.status_code == 200, published.text
    assert published.json()["module"]["action"] == {"type": "service_request", "service_id": service.json()["service_id"]}


def test_legacy_module_contract_is_readable_and_reconfigurable(admin_client: TestClient, isolated_module_property):
    property_id = "test-property"
    record = main_module.properties.get(property_id)
    record.guest_modules = [{"id": "legacy-shortcut", "name": "Old shortcut", "enabled": True, "order": 0}]
    main_module.properties.upsert(record)
    listing = admin_client.get(_module_api(property_id))
    assert listing.status_code == 200, listing.text
    module = listing.json()["modules"][0]
    assert module["id"] == "legacy-shortcut"
    assert module["needs_configuration"] is True
    saved = admin_client.put(
        f"{_module_api(property_id)}/legacy-shortcut",
        json={"config": _config("Reconfigured shortcut", "Tell me about the hotel."), "expected_revision": module["revision"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["module"]["status"] == "draft"
    assert main_module.properties.get(property_id).public_profile["guest_modules"] == []

