from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.network_access import (
    ManagementAccessGuard,
    find_network_overlaps,
    normalize_cidrs,
    normalize_management_access,
    unsafe_management_networks,
)
from app.operations import OperationsStore
from app.properties import PropertyRecord, PropertyStore
from app.main import app


def _config(allowed: list[str], proxies: list[str] | None = None, enabled: bool = True) -> dict:
    return normalize_management_access(
        {
            "management_access_enabled": enabled,
            "management_allowed_cidrs": allowed,
            "management_trusted_proxy_ranges": proxies or [],
        },
        default_allowed_cidrs=(),
        default_trusted_proxy_ranges=(),
    )


def _save_access(operations: OperationsStore, allowed: list[str], proxies: list[str] | None = None) -> None:
    loopback = ["127.0.0.0/8", "::1/128"]
    operations.save_network_access_settings(_config([*allowed, *(item for item in loopback if item not in allowed)], proxies))


@pytest.fixture
def network_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    operations = OperationsStore(tmp_path / "network-operations.db")
    property_store = PropertyStore(tmp_path / "network-properties.db")
    property_store.upsert(
        PropertyRecord(
            property_id="test-property",
            hotel_name="Test Property",
            guardrails={"guest_network_only": True, "allowed_cidrs": ["10.50.0.0/16"]},
        )
    )
    monkeypatch.setattr(main_module, "operations", operations)
    monkeypatch.setattr(main_module, "properties", property_store)
    return operations, property_store


def test_management_guard_uses_ipv4_management_cidr():
    guard = ManagementAccessGuard()
    decision = guard.evaluate("10.10.10.25", {}, _config(["10.10.10.0/24"]))
    assert decision.allowed
    assert decision.matched_network == "10.10.10.0/24"


def test_management_guard_uses_ipv6_management_cidr():
    guard = ManagementAccessGuard()
    decision = guard.evaluate("fd12:3456::25", {}, _config(["fd12:3456::/64"]))
    assert decision.allowed
    assert decision.matched_network == "fd12:3456::/64"


def test_forged_forwarded_for_is_ignored_from_untrusted_peer():
    guard = ManagementAccessGuard()
    decision = guard.evaluate(
        "10.50.20.100",
        {"x-forwarded-for": "10.10.10.25"},
        _config(["10.10.10.0/24"], ["10.20.30.10/32"]),
    )
    assert not decision.allowed
    assert decision.client_ip == "10.50.20.100"
    assert not decision.trusted_proxy


def test_trusted_proxy_forwarding_resolves_the_real_client():
    guard = ManagementAccessGuard()
    decision = guard.evaluate(
        "10.20.30.10",
        {"x-forwarded-for": "10.10.10.25"},
        _config(["10.10.10.0/24"], ["10.20.30.10/32"]),
    )
    assert decision.allowed
    assert decision.client_ip == "10.10.10.25"
    assert decision.trusted_proxy


def test_malformed_forwarded_chain_fails_closed():
    guard = ManagementAccessGuard()
    decision = guard.evaluate(
        "10.20.30.10",
        {"x-forwarded-for": "10.10.10.25, not-an-ip"},
        _config(["10.10.10.0/24"], ["10.20.30.10/32"]),
    )
    assert not decision.allowed
    assert decision.client_ip == ""


def test_invalid_management_cidrs_are_rejected():
    with pytest.raises(ValueError, match="Invalid CIDR"):
        normalize_cidrs(["10.20.0.0/99"], "management_allowed_cidrs")


def test_duplicate_management_cidrs_are_rejected_after_normalization():
    with pytest.raises(ValueError, match="Duplicate CIDR"):
        normalize_cidrs(["10.20.0.0/24", "10.20.0.5/24"], "management_allowed_cidrs")


def test_unsafe_management_networks_are_reported():
    assert unsafe_management_networks(["0.0.0.0/0", "::/0", "10.0.0.0/8"]) == ["0.0.0.0/0", "::/0"]
    assert unsafe_management_networks(["8.8.8.8/32"]) == ["8.8.8.8/32"]


def test_guest_and_management_overlap_is_reported():
    assert find_network_overlaps(["10.50.0.0/16"], ["10.0.0.0/8"]) == [("10.50.0.0/16", "10.0.0.0/8")]
    assert find_network_overlaps(["2001:db8::/48"], ["10.0.0.0/8"]) == []


def test_guest_network_can_access_guest_api_but_an_outside_network_is_blocked(network_stores):
    operations, properties = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    record = properties.get("test-property")
    record.guardrails = {"guest_network_only": True, "allowed_cidrs": ["10.50.0.0/16"]}
    properties.upsert(record)

    with TestClient(app, base_url="https://testserver", client=("10.50.20.100", 50000)) as guest:
        assert guest.get("/").status_code == 200
        assert guest.get("/api/guest/zones").status_code == 200
    with TestClient(app, base_url="https://testserver", client=("10.60.20.100", 50000)) as outside:
        assert outside.get("/api/guest/zones").status_code == 403


def test_guest_network_receives_403_for_admin_and_metrics(network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    with TestClient(app, client=("10.50.20.100", 50000)) as guest:
        assert guest.get("/admin").status_code == 403
        assert guest.get("/api/admin/properties/test-property/network-access/status").status_code == 403
        assert guest.get("/metrics", headers={"Authorization": "Bearer test-token"}).status_code == 403


def test_guest_only_network_stays_blocked_when_it_overlaps_management_ranges(network_stores):
    operations, _ = network_stores
    # A broad private-network default can overlap a property's guest CIDR.
    # Guest-only ranges remain excluded from management endpoints in that case.
    _save_access(operations, ["10.0.0.0/8"])
    with TestClient(app, client=("10.50.20.100", 50000)) as guest:
        assert guest.get("/admin").status_code == 403
        assert guest.get("/api/admin/properties/test-property/network-access/status").status_code == 403
    with TestClient(app, client=("10.10.10.25", 50000)) as management:
        assert management.get("/admin").status_code == 200


def test_management_network_reaches_admin_then_normal_authentication_applies(network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    with TestClient(app, client=("10.10.10.25", 50000)) as management:
        assert management.get("/admin").status_code == 200
        assert management.get("/api/admin/auth/me").status_code == 401


def test_untrusted_forwarded_for_cannot_bypass_management_middleware(network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"], ["10.20.30.10/32"])
    with TestClient(app, client=("10.50.20.100", 50000)) as guest:
        response = guest.get("/admin", headers={"X-Forwarded-For": "10.10.10.25"})
        assert response.status_code == 403


def test_trusted_proxy_can_forward_management_client_to_admin(network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"], ["10.20.30.10/32"])
    with TestClient(app, client=("10.20.30.10", 50000)) as proxy:
        response = proxy.get("/admin", headers={"X-Forwarded-For": "10.10.10.25"})
        assert response.status_code == 200


def test_trusted_proxy_scheme_and_guest_address_use_guest_proxy_ranges(network_stores):
    operations, properties = network_stores
    _save_access(operations, ["10.10.0.0/16"], ["10.20.30.10/32"])
    record = properties.get("test-property")
    record.guardrails = {
        "guest_network_only": True,
        "allowed_cidrs": ["10.50.0.0/16"],
        "trusted_proxy_ranges": ["10.20.30.10/32"],
    }
    properties.upsert(record)
    with TestClient(app, client=("10.20.30.10", 50000)) as proxy:
        response = proxy.get(
            "/api/guest/zones",
            headers={"X-Forwarded-For": "10.50.20.100", "X-Forwarded-Proto": "https"},
        )
        assert response.status_code == 200, response.text


def test_management_and_guest_settings_require_explicit_warning_confirmations(admin_client: TestClient, network_stores):
    operations, properties = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    response = admin_client.put(
        "/api/admin/properties/test-property/network-access/management",
        json={"management_access_enabled": True, "management_allowed_cidrs": ["0.0.0.0/0", "10.50.0.0/16"]},
    )
    assert response.status_code == 409
    assert {"confirm_unsafe", "confirm_overlap"} <= set(response.json()["detail"]["confirmations"])

    response = admin_client.put(
        "/api/admin/properties/test-property/network-access/management",
        json={
            "management_access_enabled": True,
            "management_allowed_cidrs": ["0.0.0.0/0", "10.50.0.0/16"],
            "confirm_unsafe": True,
            "confirm_overlap": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["management"]["status"] == "unprotected"

    _save_access(operations, ["10.10.0.0/16"])
    guest = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_domain": "", "allowed_cidrs": ["10.50.0.0/16"]},
    )
    assert guest.status_code == 200, guest.text
    properties_record = properties.get("test-property")
    assert properties_record.guardrails["allowed_cidrs"] == ["10.50.0.0/16"]


def test_management_save_warns_when_it_would_lock_out_current_administrator(admin_client: TestClient, network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.0.0.0/8"])
    with TestClient(
        app,
        client=("10.10.10.25", 50000),
        cookies=admin_client.cookies,
        headers={"X-CSRF-Token": admin_client.headers["X-CSRF-Token"]},
    ) as client:
        body = {"management_access_enabled": True, "management_allowed_cidrs": ["10.20.0.0/16"]}
        blocked = client.put("/api/admin/properties/test-property/network-access/management", json=body)
        assert blocked.status_code == 409
        assert "confirm_lockout" in blocked.json()["detail"]["confirmations"]
        saved = client.put(
            "/api/admin/properties/test-property/network-access/management",
            json={**body, "confirm_lockout": True},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["rollback_pending"] is True
        saved_config = operations.get_network_access_settings({})
        assert saved_config["_rollback_deadline"] > 0


def test_guest_settings_reject_invalid_domain_cidrs_and_mismatched_https_url(admin_client: TestClient, network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.0.0.0/8"])
    invalid_domain = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_domain": "https://hotelabc.com", "allowed_cidrs": ["10.50.0.0/16"]},
    )
    assert invalid_domain.status_code == 422
    invalid_cidr = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_domain": "concierge.hotelabc.com", "allowed_cidrs": ["10.50.0.0/99"]},
    )
    assert invalid_cidr.status_code == 422
    mismatch = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={
            "guest_domain": "concierge.hotelabc.com",
            "guest_url": "https://elsewhere.example.com",
            "allowed_cidrs": ["10.50.0.0/16"],
        },
    )
    assert mismatch.status_code == 422


def test_guest_management_overlap_requires_confirmation(admin_client: TestClient, network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.50.0.0/16"])
    body = {"guest_domain": "concierge.hotelabc.com", "allowed_cidrs": ["10.50.0.0/16"]}
    response = admin_client.put("/api/admin/properties/test-property/network-access/guest", json=body)
    assert response.status_code == 409
    assert response.json()["detail"]["confirmations"] == ["confirm_overlap"]
    confirmed = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={**body, "confirm_overlap": True},
    )
    assert confirmed.status_code == 200, confirmed.text


def test_network_access_view_permission_does_not_grant_manage_permission(admin_client: TestClient, network_stores, tmp_path: Path):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    property_record = main_module.properties.get("test-property")
    property_record.guardrails["guest_access_hosts"] = ["192.168.50.20"]
    main_module.properties.upsert(property_record)
    auth: AdminAuthStore = main_module.admin_auth
    user = auth.create_user(
        {
            "username": "hotel.manager",
            "display_name": "Hotel Manager",
            "password": "HotelManagerPass123!",
            "role_id": "role-property-manager",
            "property_id": "test-property",
        },
        auth.authenticate(admin_client.cookies.get("concierge_admin_session")),
    )
    with TestClient(app, client=("10.10.10.25", 50000)) as manager:
        login = manager.post("/api/admin/auth/login", json={"username": user["username"], "password": "HotelManagerPass123!"})
        assert login.status_code == 200, login.text
        manager.headers.update({"X-CSRF-Token": login.json()["user"]["csrf_token"]})
        status = manager.get("/api/admin/properties/test-property/network-access/status")
        assert status.status_code == 200
        assert "guest_access_hosts" not in status.json()["guest"]
        property_view = manager.get("/api/admin/properties/test-property")
        assert property_view.status_code == 200
        assert "192.168.50.20" not in property_view.text
        update = manager.put(
            "/api/admin/properties/test-property/network-access/guest",
            json={"guest_domain": "concierge.hotelabc.com", "guest_access_hosts": ["192.168.60.20"], "allowed_cidrs": ["10.50.0.0/16"]},
        )
        assert update.status_code == 403


def test_guest_access_hosts_save_exact_hosts_and_reject_invalid_entries(admin_client: TestClient, network_stores):
    _, properties = network_stores
    response = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_domain": "", "guest_access_hosts": ["192.168.50.20", "guest.hotel.local", "2001:db8::1234"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["guest"]["guest_access_hosts"] == ["192.168.50.20", "guest.hotel.local", "2001:db8::1234"]
    assert properties.get("test-property").guardrails["guest_access_hosts"] == ["192.168.50.20", "guest.hotel.local", "2001:db8::1234"]

    legacy_client_update = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_domain": ""},
    )
    assert legacy_client_update.status_code == 200
    assert legacy_client_update.json()["guest"]["guest_access_hosts"] == ["192.168.50.20", "guest.hotel.local", "2001:db8::1234"]

    invalid = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_access_hosts": ["192.168.50.20:8080"]},
    )
    assert invalid.status_code == 422


def test_property_admin_cannot_change_another_property_network_access(admin_client: TestClient, network_stores):
    operations, properties = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    properties.upsert(PropertyRecord(property_id="other-property", hotel_name="Other Property"))
    auth: AdminAuthStore = main_module.admin_auth
    root = auth.authenticate(admin_client.cookies.get("concierge_admin_session"))
    user = auth.create_user(
        {
            "username": "property.admin",
            "display_name": "Property Admin",
            "password": "PropertyAdminPass123!",
            "role_id": "role-property-administrator",
            "property_id": "test-property",
        },
        root,
    )
    with TestClient(app, client=("10.10.10.25", 50000)) as manager:
        login = manager.post("/api/admin/auth/login", json={"username": user["username"], "password": "PropertyAdminPass123!"})
        assert login.status_code == 200, login.text
        manager.headers.update({"X-CSRF-Token": login.json()["user"]["csrf_token"]})
        denied = manager.put(
            "/api/admin/properties/other-property/network-access/guest",
            json={"guest_domain": "other.example.com", "allowed_cidrs": ["10.60.0.0/16"]},
        )
        assert denied.status_code == 403


def test_guest_access_switch_blocks_guest_entrypoints(admin_client: TestClient, network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    saved = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_access_enabled": False, "guest_domain": "", "allowed_cidrs": ["10.50.0.0/16"]},
    )
    assert saved.status_code == 200, saved.text
    with TestClient(app, client=("10.50.20.100", 50000)) as guest:
        assert guest.get("/").status_code == 403
        assert guest.post("/api/session/start", json={"client_id": "guest-1", "property_id": "test-property"}).status_code == 403


def test_production_documentation_configuration_disables_public_docs():
    assert main_module.documentation_options("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert main_module.documentation_options("staging") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    production_app = FastAPI(**main_module.documentation_options("production"))
    with TestClient(production_app, client=("10.50.20.100", 50000)) as guest:
        for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            assert guest.get(path).status_code == 404


def test_network_access_status_uses_unavailable_when_host_address_cannot_be_detected(admin_client: TestClient, network_stores, monkeypatch: pytest.MonkeyPatch):
    operations, _ = network_stores
    _save_access(operations, ["10.0.0.0/8"])
    monkeypatch.setattr(main_module, "detected_server_network", lambda: {"server_ip": "", "network_interface": ""})
    response = admin_client.get("/api/admin/properties/test-property/network-access/status")
    assert response.status_code == 200
    assert response.json()["management"]["server_ip"] == ""
    assert response.json()["management"]["admin_url"] == ""


def test_public_guest_domain_uses_the_resolved_address_for_tls_verification(monkeypatch: pytest.MonkeyPatch):
    resolved_address = "93.184.216.34"
    record = PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="concierge.hotelabc.com")
    monkeypatch.setattr(
        main_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_address, 443))],
    )

    class FakeTlsSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def getpeercert(self):
            return {"notAfter": "Dec 31 23:59:59 2030 GMT", "issuer": ((('commonName', 'Hotel CA'),),)}

    class FakeContext:
        def wrap_socket(self, raw_socket, server_hostname):
            assert server_hostname == "concierge.hotelabc.com"
            return FakeTlsSocket()

    monkeypatch.setattr(main_module.ssl, "create_default_context", lambda: FakeContext())
    class FakeRawSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def create_connection(address, timeout):
        assert address == (resolved_address, 443)
        return FakeRawSocket()

    monkeypatch.setattr(main_module.socket, "create_connection", create_connection)
    result = asyncio.run(main_module._verify_deployment(record))
    assert result["domain_status"] == "verified"
    assert result["resolved_addresses"] == [resolved_address]
    assert result["ssl_status"] == "valid"


def test_network_configuration_audit_has_actor_property_and_old_new_values(admin_client: TestClient, network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    response = admin_client.put(
        "/api/admin/properties/test-property/network-access/guest",
        json={"guest_domain": "concierge.hotelabc.com", "allowed_cidrs": ["10.50.0.0/16"]},
    )
    assert response.status_code == 200, response.text
    audits = main_module.admin_auth.list_audit(
        main_module.admin_auth.authenticate(admin_client.cookies.get("concierge_admin_session")),
        {"property_id": "test-property", "action": "guest_domain_changed"},
    )
    assert audits
    assert audits[0]["property_id"] == "test-property"
    assert audits[0]["metadata"]["old_value"] == ""
    assert audits[0]["metadata"]["new_value"] == "concierge.hotelabc.com"


def test_management_network_changes_are_audited_with_old_and_new_values(admin_client: TestClient, network_stores):
    operations, _ = network_stores
    _save_access(operations, ["10.10.0.0/16"])
    response = admin_client.put(
        "/api/admin/properties/test-property/network-access/management",
        json={
            "management_access_enabled": True,
            "management_allowed_cidrs": ["10.20.0.0/16", "127.0.0.0/8", "::1/128"],
        },
    )
    assert response.status_code == 200, response.text
    actor = main_module.admin_auth.authenticate(admin_client.cookies.get("concierge_admin_session"))
    added = main_module.admin_auth.list_audit(actor, {"property_id": "test-property", "action": "management_network_added"})
    removed = main_module.admin_auth.list_audit(actor, {"property_id": "test-property", "action": "management_network_removed"})
    assert added[0]["metadata"] == {"old_value": "", "new_value": "10.20.0.0/16"}
    assert removed[0]["metadata"] == {"old_value": "10.10.0.0/16", "new_value": ""}
