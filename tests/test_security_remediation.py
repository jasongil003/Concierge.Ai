from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.config import Settings, validate_antlabs_mode, validate_production_settings
from app.guardrails import PropertyGuard
from app.main import app
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


def _production_settings(tmp_path: Path, **overrides) -> Settings:
    safe = Settings(
        app_environment="production",
        property_id="hotel-a",
        db_path=tmp_path / "concierge.db",
        admin_bootstrap_password="ProductionOnly123!",
        admin_cookie_secure=True,
        credential_encryption_secret="a" * 32,
        antlabs_mode="browser_handoff",
        antlabs_auth_url="https://gateway.example.test/login/main.ant?c=proc",
        allow_body_property_selection=False,
        metrics_token="m" * 40,
        canonical_hosts=("concierge.example.test", "admin.example.test"),
        admin_allowed_cidrs=("198.51.100.14/32",),
        public_base_url="https://concierge.example.test",
        forwarded_allow_ips="172.29.0.2,172.29.0.1",
    )
    return replace(safe, **overrides)


def test_production_rejects_default_admin_password(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_PASSWORD"):
        validate_production_settings(
            _production_settings(tmp_path, admin_bootstrap_password="ChangeMe123!")
        )


def test_production_rejects_default_encryption_secret(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_SECRET"):
        validate_production_settings(
            _production_settings(tmp_path, credential_encryption_secret="change-me")
        )


def test_production_requires_secure_cookie(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_COOKIE_SECURE"):
        validate_production_settings(
            _production_settings(tmp_path, admin_cookie_secure=False)
        )


def test_production_requires_canonical_hosts_and_admin_network_restrictions(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CANONICAL_HOSTS"):
        validate_production_settings(_production_settings(tmp_path, canonical_hosts=()))
    with pytest.raises(RuntimeError, match="ADMIN_ALLOWED_CIDRS"):
        validate_production_settings(_production_settings(tmp_path, admin_allowed_cidrs=("0.0.0.0/0",)))
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        validate_production_settings(_production_settings(tmp_path, public_base_url="http://concierge.example.test"))
    with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
        validate_production_settings(_production_settings(tmp_path, forwarded_allow_ips="*"))


def test_staging_has_production_auth_and_gateway_requirements(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ANTLABS_MODE=mock"):
        validate_production_settings(
            _production_settings(tmp_path, app_environment="staging", antlabs_mode="mock"),
            check_filesystem=False,
        )


def test_production_allows_persistent_sqlite_without_external_database_services(tmp_path: Path):
    settings = _production_settings(
        tmp_path,
        metrics_token="m" * 40,
        database_url="",
        redis_url="",
    )
    validate_production_settings(settings)


def test_production_rejects_example_metrics_token(tmp_path: Path):
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        validate_production_settings(
            _production_settings(
                tmp_path,
                metrics_token="replace-with-a-random-token-of-at-least-32-characters",
            )
        )


def test_antlabs_mode_is_explicitly_validated(tmp_path: Path):
    assert validate_antlabs_mode("mock") == "mock"
    assert validate_antlabs_mode("browser_handoff") == "browser_handoff"
    with pytest.raises(ValueError, match="Unsupported ANTLABS_MODE"):
        validate_antlabs_mode("live")
    with pytest.raises(RuntimeError, match="ANTLABS_MODE"):
        validate_production_settings(_production_settings(tmp_path, antlabs_mode="live"), check_filesystem=False)
    with pytest.raises(RuntimeError, match="ANTLABS_AUTH_URL"):
        validate_production_settings(_production_settings(tmp_path, antlabs_auth_url=""), check_filesystem=False)


def test_production_requires_sg5_builtin_processor_endpoint_and_post(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ANTLABS_AUTH_URL must target the SG5 built-in processor"):
        validate_production_settings(
            _production_settings(tmp_path, antlabs_auth_url="https://gateway.example.test/custom-login"),
            check_filesystem=False,
        )
    with pytest.raises(RuntimeError, match="ANTLABS_AUTH_METHOD must be POST"):
        validate_production_settings(
            _production_settings(tmp_path, antlabs_auth_method="GET"),
            check_filesystem=False,
        )


def test_development_can_use_explicit_demo_settings(tmp_path: Path):
    development = replace(
        _production_settings(tmp_path),
        app_environment="development",
        property_id="tenant-a",
        antlabs_mode="mock",
        admin_cookie_secure=False,
        credential_encryption_secret="d" * 32,
        allow_body_property_selection=True,
    )
    validate_production_settings(development)


def test_every_environment_requires_explicit_bootstrap_and_encryption_secrets(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_PASSWORD must be explicitly set"):
        validate_production_settings(_production_settings(tmp_path, app_environment="development", admin_bootstrap_password=""))
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_SECRET must contain at least 32 characters"):
        validate_production_settings(_production_settings(tmp_path, app_environment="development", credential_encryption_secret=""))


def test_production_host_and_transport_boundary_reject_spoofing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    secure_settings = replace(
        main_module.settings,
        app_environment="production",
        canonical_hosts=("concierge.example.test",),
        admin_allowed_cidrs=("198.51.100.14/32",),
    )
    monkeypatch.setattr(main_module, "settings", secure_settings)

    with TestClient(app, base_url="http://concierge.example.test") as client:
        insecure = client.get("/api/hotel")
    with TestClient(app, base_url="https://concierge.example.test") as client:
        spoofed_ip = client.get(
            "/admin/login",
            headers={"X-Forwarded-For": "198.51.100.14"},
            follow_redirects=False,
        )
        bad_host = client.get("/admin/login", headers={"Host": "attacker.example"})

    assert insecure.status_code == 426
    assert insecure.headers["strict-transport-security"].startswith("max-age=")
    assert spoofed_ip.status_code == 403
    assert bad_host.status_code == 400


def test_production_allows_admin_only_from_configured_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    secure_settings = replace(
        main_module.settings,
        app_environment="production",
        canonical_hosts=("concierge.example.test",),
        admin_allowed_cidrs=("127.0.0.0/8",),
    )
    monkeypatch.setattr(main_module, "settings", secure_settings)
    with TestClient(app, base_url="https://concierge.example.test") as client:
        response = client.get("/admin/login")
    assert response.status_code == 200


def test_production_documents_are_disabled_but_remain_available_for_development():
    assert main_module.documentation_options("production") == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    assert main_module.documentation_options("staging")["openapi_url"] is None
    assert main_module.documentation_options("development")["openapi_url"] == "/openapi.json"


def test_password_recovery_link_uses_configured_public_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, public_base_url="https://concierge.example.test"),
    )
    request = Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/api/admin/auth/password-reset/request",
        "query_string": b"",
        "headers": [(b"host", b"attacker.example")],
        "server": ("attacker.example", 80),
        "client": ("127.0.0.1", 12345),
        "http_version": "1.1",
    })
    assert main_module._admin_password_reset_url(request, "opaque-token") == (
        "https://concierge.example.test/admin/login#reset_token=opaque-token"
    )


def test_password_recovery_link_fails_closed_without_public_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, public_base_url=""))
    request = Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/api/admin/auth/password-reset/request",
        "query_string": b"",
        "headers": [(b"host", b"attacker.example")],
        "server": ("attacker.example", 80),
        "client": ("127.0.0.1", 12345),
        "http_version": "1.1",
    })
    with pytest.raises(RuntimeError, match="PUBLIC_BASE_URL"):
        main_module._admin_password_reset_url(request, "opaque-token")


def test_deployment_verification_rejects_private_dns_answers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import asyncio
    import socket

    record = PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="hotel.example.test")
    monkeypatch.setattr(
        main_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )

    def unexpected_connection(*args, **kwargs):
        raise AssertionError("A non-public DNS answer must never receive a connection.")

    monkeypatch.setattr(main_module.socket, "create_connection", unexpected_connection)
    result = asyncio.run(main_module._verify_deployment(record))
    assert result["domain_status"] == "blocked"
    assert result["ssl_status"] == "not_checked"


def _tenant_stores(tmp_path: Path) -> tuple[PropertyStore, SessionStore]:
    property_store = PropertyStore(tmp_path / "tenants.db")
    property_store.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"))
    property_store.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B", domain="b.example.test"))
    return property_store, SessionStore(tmp_path / "tenants.db")


def test_unknown_host_cannot_select_property():
    records = [PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test")]
    with pytest.raises(PermissionError, match="not mapped"):
        PropertyGuard.resolve(records, "hotel-a", "unknown.example.test", "hotel-a")


def test_unknown_host_cannot_resolve_a_single_domain_mapped_property_without_default():
    records = [PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test")]
    with pytest.raises(PermissionError, match="not mapped"):
        PropertyGuard.resolve(records, "", "unknown.example.test")


def test_hotel_a_host_cannot_select_hotel_b():
    records = [
        PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"),
        PropertyRecord(property_id="hotel-b", hotel_name="Hotel B", domain="b.example.test"),
    ]
    with pytest.raises(PermissionError, match="does not match"):
        PropertyGuard.resolve(records, "hotel-a", "a.example.test", "hotel-b")


def test_hotel_a_guest_cannot_access_hotel_b_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    property_store, session_store = _tenant_stores(tmp_path)
    session = session_store.create("hotel-b", "hotel-b-guest")
    monkeypatch.setattr(main_module, "properties", property_store)
    monkeypatch.setattr(main_module, "store", session_store)
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, allow_body_property_selection=False),
    )

    with TestClient(app, base_url="http://a.example.test") as client:
        response = client.get(f"/api/guest/personalization?session_id={session.session_id}")

    assert response.status_code == 403
    assert response.json()["policy"] == "property_isolation"


def test_stolen_guest_session_id_replays_within_its_property_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    property_store = PropertyStore(tmp_path / "guest-replay.db")
    property_store.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"))
    session_store = SessionStore(tmp_path / "guest-replay.db")
    session = session_store.create("hotel-a", "original-browser-client")
    monkeypatch.setattr(main_module, "properties", property_store)
    monkeypatch.setattr(main_module, "store", session_store)
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, allow_body_property_selection=False))

    # Guest APIs treat the high-entropy session ID as a bearer credential; they do not
    # require the client_id that resume_session checks.
    with TestClient(app, base_url="http://a.example.test") as client:
        response = client.get(f"/api/guest/personalization?session_id={session.session_id}")

    assert response.status_code == 200


def test_hotel_a_admin_cannot_access_hotel_b_without_permission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth = AdminAuthStore(tmp_path / "admin-tenants.db")
    auth.ensure_bootstrap_admin("admin", "ChangeMe123!")
    _, super_admin = auth.login("admin", "ChangeMe123!", "127.0.0.1", "tests")
    auth.create_user(
        {
            "username": "hotel-a-admin",
            "display_name": "Hotel A Admin",
            "password": "HotelAOnly123!",
            "property_id": "hotel-a",
            "role_id": "role-property-administrator",
            "status": "active",
        },
        super_admin,
    )
    monkeypatch.setattr(main_module, "admin_auth", auth)
    with TestClient(app) as client:
        login = client.post(
            "/api/admin/auth/login",
            json={"username": "hotel-a-admin", "password": "HotelAOnly123!", "remember_me": False},
        )
        assert login.status_code == 200
        response = client.get("/api/admin/properties/hotel-b")
    assert response.status_code == 403


def test_super_admin_can_access_authorized_global_resource(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth = AdminAuthStore(tmp_path / "super-admin.db")
    auth.ensure_bootstrap_admin("admin", "ChangeMe123!")
    monkeypatch.setattr(main_module, "admin_auth", auth)
    with TestClient(app) as client:
        login = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "ChangeMe123!", "remember_me": False},
        )
        assert login.status_code == 200
        response = client.get("/api/admin/system/email")
    assert response.status_code == 200
