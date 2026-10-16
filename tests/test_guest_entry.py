from __future__ import annotations

import asyncio
import base64
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.admin_auth import AdminPrincipal
from app.guest_entry import (
    canonical_guest_entry_url,
    guest_entry_qr_svg,
    signed_wayfinding_entry_url,
    verify_wayfinding_start_signature,
)
from app.guest_identity import GuestIdentityStore
import app.main as main_module
from app.properties import PropertyRecord
import app.zones as zones_module
from app.zones import ZoneStore


def test_canonical_guest_entry_url_requires_enabled_https_origin():
    property_record = PropertyRecord(
        property_id="guest-entry-test",
        hotel_name="Guest Entry Test",
        domain="concierge.example.test",
        app_settings={
            "deployment": {
                "guest_access_enabled": True,
                "https_required": True,
                "public_base_url": "https://concierge.example.test/",
            }
        },
    )
    assert canonical_guest_entry_url(property_record) == "https://concierge.example.test"

    property_record.app_settings["deployment"]["public_base_url"] = "https://concierge.example.test:8443"
    assert canonical_guest_entry_url(property_record) == "https://concierge.example.test:8443"

    property_record.app_settings["deployment"]["guest_access_enabled"] = False
    assert canonical_guest_entry_url(property_record) is None

    property_record.app_settings["deployment"]["guest_access_enabled"] = True
    property_record.app_settings["deployment"]["https_required"] = False
    assert canonical_guest_entry_url(property_record) is None


def test_canonical_guest_entry_url_rejects_non_origin_and_foreign_hosts():
    property_record = PropertyRecord(
        property_id="guest-entry-test",
        hotel_name="Guest Entry Test",
        domain="concierge.example.test",
        app_settings={"deployment": {"public_base_url": "https://other.example.test/guest"}},
    )
    assert canonical_guest_entry_url(property_record) is None

    property_record.app_settings["deployment"]["public_base_url"] = "https://user@concierge.example.test"
    assert canonical_guest_entry_url(property_record) is None


def test_guest_entry_qr_svg_is_generated():
    svg = guest_entry_qr_svg("https://concierge.example.test")
    assert "<svg" in svg
    assert "<path" in svg
    assert len(svg) > 200


def test_guest_entry_qr_endpoint_serves_only_configured_scoped_https_url(admin_client, request):
    property_id = f"guest-entry-{uuid.uuid4().hex[:10]}"
    record = PropertyRecord(
        property_id=property_id,
        hotel_name="Guest Entry Endpoint Test",
        domain="concierge.example.test",
        app_settings={
            "deployment": {
                "guest_access_enabled": True,
                "https_required": True,
                "public_base_url": "https://concierge.example.test",
            }
        },
    )
    main_module.properties.upsert(record)
    request.addfinalizer(lambda: main_module.properties.delete(property_id))

    response = admin_client.get(f"/api/admin/properties/{property_id}/guest-entry/qr.svg")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "<svg" in response.text

    deployment = dict(record.app_settings["deployment"])
    deployment["guest_access_enabled"] = False
    record.app_settings["deployment"] = deployment
    main_module.properties.upsert(record)
    disabled = admin_client.get(f"/api/admin/properties/{property_id}/guest-entry/qr.svg")
    assert disabled.status_code == 409

    scoped_principal = AdminPrincipal(
        user_id="scoped-admin",
        username="scoped-admin",
        display_name="Scoped Admin",
        email=None,
        role_id="property-admin",
        role_name="Property Admin",
        role_slug="property-admin",
        property_id="another-property",
        department_id=None,
        status="active",
        permissions=frozenset({"network.view"}),
        session_id="session-test",
        csrf_token="csrf-test",
        force_password_change=False,
        expires_at=4_000_000_000,
    )
    request_scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": f"/api/admin/properties/{property_id}/guest-entry/qr.svg",
        "raw_path": f"/api/admin/properties/{property_id}/guest-entry/qr.svg".encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 443),
        "state": {"admin": scoped_principal},
    }
    with pytest.raises(HTTPException) as denied:
        asyncio.run(main_module.guest_entry_qr(property_id, Request(request_scope)))
    assert denied.value.status_code == 404


def test_wayfinding_signature_is_bound_to_property_and_node():
    record = PropertyRecord(
        property_id="wayfinding-property",
        hotel_name="Wayfinding Test",
        domain="concierge.example.test",
        app_settings={"deployment": {"public_base_url": "https://concierge.example.test"}},
    )
    secret = "test-property-secret"
    url = signed_wayfinding_entry_url(record, "node_abc123", secret)
    assert url
    query = parse_qs(urlsplit(url).query)
    signature = query["start_sig"][0]
    assert query["property_id"] == [record.property_id]
    assert query["start_node_id"] == ["node_abc123"]
    assert verify_wayfinding_start_signature(record.property_id, "node_abc123", signature, secret)
    assert not verify_wayfinding_start_signature(record.property_id, "node_other", signature, secret)
    assert not verify_wayfinding_start_signature("another-property", "node_abc123", signature, secret)
    assert not verify_wayfinding_start_signature(record.property_id, "node_abc123", "0" * 64, secret)


def test_wayfinding_qr_resolves_only_a_published_guest_visible_map_node(admin_client, tmp_path, request, monkeypatch):
    property_id = f"wayfinding-{uuid.uuid4().hex[:10]}"
    record = PropertyRecord(
        property_id=property_id,
        hotel_name="Wayfinding Endpoint Test",
        domain="concierge.example.test",
        guardrails={"directions_enabled": True},
        app_settings={
            "deployment": {
                "guest_access_enabled": True,
                "https_required": True,
                "public_base_url": "https://concierge.example.test",
            }
        },
    )
    main_module.properties.upsert(record)
    request.addfinalizer(lambda: main_module.properties.delete(property_id))

    store = ZoneStore(tmp_path / "wayfinding-zones.db")
    monkeypatch.setattr(main_module, "zones", store)
    monkeypatch.setattr(zones_module, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(main_module, "guest_identities", GuestIdentityStore(tmp_path / "guest-identities.db"))

    building = store.create_building(property_id, {"name": "Main Building"})
    floor = store.create_floor(property_id, {"building_id": building["building_id"], "name": "Lobby", "level": 0})
    zone = store.upsert_zone(property_id, {
        "floor_id": floor["floor_id"],
        "name": "Guest Lobby",
        "geometry": {"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10},
    })
    start = store.create_node(property_id, {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Lobby Entrance", "x": 1, "y": 1,
    })
    destination = store.create_node(property_id, {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Pool", "x": 8, "y": 8,
    })
    store.create_edge(property_id, {
        "from_node_id": start["node_id"], "to_node_id": destination["node_id"], "distance": 7,
    })
    store.save_floor_map(property_id, floor["floor_id"], {
        "filename": "lobby.svg",
        "content_type": "image/svg+xml",
        "content_base64": base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>').decode("ascii"),
        "width": 10,
        "height": 10,
    })
    draft = store.create_map_revision(property_id)
    store.publish_map_revision(property_id, draft["revision_id"])

    qr = admin_client.get(f"/api/admin/properties/{property_id}/navigation/nodes/{start['node_id']}/wayfinding-qr.svg")
    assert qr.status_code == 200, qr.text
    assert qr.headers["content-type"].startswith("image/svg+xml")
    assert qr.headers["cache-control"] == "no-store"
    assert qr.headers["x-content-type-options"] == "nosniff"
    assert "<svg" in qr.text

    guest_url = qr.headers["x-concierge-wayfinding-url"]
    query = parse_qs(urlsplit(guest_url).query)
    assert urlsplit(guest_url).scheme == "https"
    assert query["property_id"] == [property_id]
    assert query["start_node_id"] == [start["node_id"]]

    params = {key: values[0] for key, values in query.items()}
    opened = admin_client.get("/api/guest/wayfinding/start", params=params)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["starting_node"]["label"] == "Lobby Entrance"
    assert body["map"]["starting_node_id"] == start["node_id"]
    assert body["map"]["focused_marker_id"] == start["node_id"]
    assert body["map"]["directions_enabled"] is True

    tampered = admin_client.get("/api/guest/wayfinding/start", params={
        **params, "start_sig": "0" * 64,
    })
    assert tampered.status_code == 404
    cross_property = admin_client.get("/api/guest/wayfinding/start", params={
        **params, "property_id": f"other-{property_id}",
    })
    assert cross_property.status_code == 404

    store.update_node(property_id, start["node_id"], {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Lobby Entrance", "guest_visible": False,
    })
    private_draft = store.create_map_revision(property_id)
    store.publish_map_revision(property_id, private_draft["revision_id"])
    hidden_start = admin_client.get("/api/guest/wayfinding/start", params=params)
    assert hidden_start.status_code == 404
    hidden_qr = admin_client.get(f"/api/admin/properties/{property_id}/navigation/nodes/{start['node_id']}/wayfinding-qr.svg")
    assert hidden_qr.status_code == 409
