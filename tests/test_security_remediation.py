from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.config import Settings, validate_production_settings
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
        antlabs_mode="live",
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


def test_development_can_use_explicit_demo_settings(tmp_path: Path):
    development = replace(
        _production_settings(tmp_path),
        app_environment="development",
        property_id="demo-hotel",
        antlabs_mode="mock",
        admin_cookie_secure=False,
        credential_encryption_secret="",
        allow_body_property_selection=True,
    )
    validate_production_settings(development)


def _tenant_stores(tmp_path: Path) -> tuple[PropertyStore, SessionStore]:
    property_store = PropertyStore(tmp_path / "tenants.db")
    property_store.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test"))
    property_store.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B", domain="b.example.test"))
    return property_store, SessionStore(tmp_path / "tenants.db")


def test_unknown_host_cannot_select_property():
    records = [PropertyRecord(property_id="hotel-a", hotel_name="Hotel A", domain="a.example.test")]
    with pytest.raises(PermissionError, match="not mapped"):
        PropertyGuard.resolve(records, "hotel-a", "unknown.example.test", "hotel-a")


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
        response = client.get(f"/api/guest/conversations/{session.session_id}/staff-messages")

    assert response.status_code == 403
    assert response.json()["policy"] == "property_isolation"


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
