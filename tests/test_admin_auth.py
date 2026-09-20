import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import (
    DEFAULT_ROLES,
    PERMISSIONS,
    AccountLockedError,
    AdminAuthStore,
    AuthenticationError,
    hash_password,
    normalize_username,
    verify_password,
)
from app.main import app


ADMIN_PASSWORD = "ChangeMe123!"


@pytest.fixture
def auth_store(tmp_path: Path) -> AdminAuthStore:
    store = AdminAuthStore(tmp_path / "admin-auth.db", session_ttl_minutes=30, lockout_attempts=3, lockout_minutes=10)
    store.ensure_bootstrap_admin("admin", ADMIN_PASSWORD, "Test Administrator")
    return store


@pytest.fixture
def auth_client(auth_store: AdminAuthStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    return TestClient(app)


def login(client: TestClient, username: str = "admin", password: str = ADMIN_PASSWORD) -> str:
    response = client.post(
        "/api/admin/auth/login",
        json={"username": username, "password": password, "remember_me": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]["csrf_token"]


def test_username_normalization_and_password_hashing():
    assert normalize_username("Jason.Gil") == "jason.gil"
    for invalid in ("two words", "bad@email", "x"):
        with pytest.raises(ValueError):
            normalize_username(invalid)

    encoded = hash_password(ADMIN_PASSWORD)
    assert ADMIN_PASSWORD not in encoded
    assert verify_password(ADMIN_PASSWORD, encoded)
    assert not verify_password("WrongPassword1!", encoded)


def test_admin_page_and_api_require_authentication(auth_client: TestClient):
    page = auth_client.get("/admin", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/admin/login"
    assert auth_client.get("/api/admin/properties").status_code == 401
    assert auth_client.get("/admin/login").status_code == 200


def test_login_logout_and_csrf(auth_client: TestClient):
    assert auth_client.post(
        "/api/admin/auth/login", json={"username": "missing", "password": "WrongPassword1!"}
    ).status_code == 401
    csrf = login(auth_client)
    assert auth_client.get("/admin", follow_redirects=False).status_code == 200
    assert auth_client.get("/api/admin/auth/me").json()["user"]["username"] == "admin"

    without_csrf = auth_client.post("/api/admin/auth/logout")
    assert without_csrf.status_code == 403
    logout = auth_client.post("/api/admin/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 200
    assert auth_client.get("/api/admin/auth/me").status_code == 401


def test_failed_logins_lock_account(auth_store: AdminAuthStore):
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            auth_store.login("admin", "WrongPassword1!", "10.0.0.5", "test")
    with pytest.raises(AccountLockedError):
        auth_store.login("admin", "WrongPassword1!", "10.0.0.5", "test")
    with pytest.raises(AccountLockedError):
        auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.6", "test")


def test_session_expiration(auth_store: AdminAuthStore):
    token, principal = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    assert auth_store.authenticate(token) is not None
    with auth_store._connect() as db:
        db.execute("UPDATE admin_sessions SET expires_at = ? WHERE session_id = ?", (int(time.time()) - 1, principal.session_id))
    assert auth_store.authenticate(token) is None


def test_default_roles_have_expected_permission_boundaries(auth_store: AdminAuthStore):
    assert set(DEFAULT_ROLES) == {
        "super-admin", "property-administrator", "property-manager", "concierge-front-desk",
        "content-manager", "viewer-auditor",
    }
    super_admin = auth_store.get_role("role-super-admin")
    assert set(super_admin["permissions"]) == set(PERMISSIONS)
    assert "properties.all" not in auth_store.get_role("role-property-administrator")["permissions"]
    assert "security.configure" not in auth_store.get_role("role-property-manager")["permissions"]
    assert "requests.manage" in auth_store.get_role("role-concierge-front-desk")["permissions"]
    assert "knowledge.edit" in auth_store.get_role("role-content-manager")["permissions"]
    assert "properties.edit" not in auth_store.get_role("role-viewer-auditor")["permissions"]


def test_user_custom_role_and_password_management(auth_client: TestClient):
    csrf = login(auth_client)
    role_response = auth_client.post(
        "/api/admin/roles",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Marketing",
            "description": "Property content and promotions",
            "property_id": "demo-hotel",
            "permissions": ["dashboard.view", "properties.view", "knowledge.view", "knowledge.edit"],
        },
    )
    assert role_response.status_code == 200, role_response.text
    role_id = role_response.json()["role"]["role_id"]

    create = auth_client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "marketing.manager",
            "display_name": "Marketing Manager",
            "password": "Temporary123!",
            "property_id": "demo-hotel",
            "role_id": role_id,
            "email": None,
            "status": "active",
            "force_password_change": True,
        },
    )
    assert create.status_code == 200, create.text
    user = create.json()["user"]
    assert user["email"] is None
    assert user["username"] == "marketing.manager"

    reset = auth_client.post(
        f"/api/admin/users/{user['id']}/reset-password",
        headers={"X-CSRF-Token": csrf},
        json={"password": "Replacement123!", "force_password_change": False},
    )
    assert reset.status_code == 200
    assert auth_client.post(
        f"/api/admin/users/{user['id']}/revoke-sessions", headers={"X-CSRF-Token": csrf}
    ).status_code == 200


def test_property_role_cannot_cross_tenant(auth_store: AdminAuthStore, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    super_token, super_principal = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    del super_token
    auth_store.create_user(
        {
            "username": "hotelmanager",
            "display_name": "Hotel Manager",
            "password": "PropertyPass123!",
            "property_id": "demo-hotel",
            "role_id": "role-property-administrator",
            "email": None,
            "status": "active",
        },
        super_principal,
    )
    client = TestClient(app)
    csrf = login(client, "hotelmanager", "PropertyPass123!")
    assert csrf
    listed = client.get("/api/admin/properties")
    assert listed.status_code == 200
    assert {item["property_id"] for item in listed.json()["properties"]} <= {"demo-hotel"}
    assert client.get("/api/admin/properties/another-hotel").status_code == 403
    assert client.put(
        "/api/admin/properties/another-hotel",
        headers={"X-CSRF-Token": csrf},
        json={"property_id": "another-hotel", "hotel_name": "Other Hotel"},
    ).status_code == 403


def test_audit_records_administrative_actions(auth_client: TestClient):
    csrf = login(auth_client)
    response = auth_client.get("/api/admin/audit")
    assert response.status_code == 200
    assert any(event["action"] == "auth.login_succeeded" for event in response.json()["events"])
    auth_client.post("/api/admin/auth/change-password", headers={"X-CSRF-Token": csrf}, json={
        "current_password": ADMIN_PASSWORD,
        "new_password": "UpdatedAdmin123!",
    })
    events = auth_client.get("/api/admin/audit").json()["events"]
    assert any(event["action"] == "auth.password_changed" for event in events)
