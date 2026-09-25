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
from app.hospitality import HospitalityStore
from app.properties import PropertyRecord, PropertyStore


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


def test_password_reset_request_is_throttled_without_exposing_username(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, int, int]] = []

    class DenyAccountLimiter:
        def allow(self, key: str, limit: int, seconds: int) -> bool:
            calls.append((key, limit, seconds))
            return not key.startswith("password-reset:account:")

    monkeypatch.setattr(main_module, "rate_limiter", DenyAccountLimiter())

    def should_not_continue(*args, **kwargs):
        raise AssertionError("throttled reset request continued into account or email processing")

    monkeypatch.setattr(main_module.admin_auth, "audit", should_not_continue)
    monkeypatch.setattr(main_module.operations, "get_email_settings", should_not_continue)
    client = TestClient(app)

    response = client.post("/api/admin/auth/password-reset/request", json={"username": "private.staff"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "If recovery is configured for this account, reset instructions will be sent."
    }
    assert len(calls) == 2
    assert calls[0][0].startswith("password-reset:ip:")
    assert calls[0][1:] == (12, 3600)
    assert calls[1][0].startswith("password-reset:account:")
    assert "private.staff" not in calls[1][0]
    assert calls[1][1:] == (3, 3600)


def test_password_reset_confirmation_is_throttled_with_hashed_token_key(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, int, int]] = []

    class DenyTokenLimiter:
        def allow(self, key: str, limit: int, seconds: int) -> bool:
            calls.append((key, limit, seconds))
            return not key.startswith("password-reset-confirm:token:")

    monkeypatch.setattr(main_module, "rate_limiter", DenyTokenLimiter())

    def should_not_consume(*args, **kwargs):
        raise AssertionError("throttled confirmation continued into token processing")

    monkeypatch.setattr(main_module.admin_auth, "consume_password_reset", should_not_consume)
    client = TestClient(app)

    response = client.post(
        "/api/admin/auth/password-reset/confirm",
        json={"token": "sensitive-reset-token-value", "new_password": "StrongReplacement123!"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many password reset attempts. Try again later."
    assert len(calls) == 2
    assert calls[0][0].startswith("password-reset-confirm:ip:")
    assert calls[0][1:] == (30, 3600)
    assert calls[1][0].startswith("password-reset-confirm:token:")
    assert "sensitive-reset-token-value" not in calls[1][0]
    assert calls[1][1:] == (10, 3600)


def test_password_reset_email_places_token_in_url_fragment(monkeypatch: pytest.MonkeyPatch):
    sent_urls: list[str] = []

    class AllowLimiter:
        def allow(self, key: str, limit: int, seconds: int) -> bool:
            return True

    monkeypatch.setattr(main_module, "rate_limiter", AllowLimiter())
    monkeypatch.setattr(main_module.admin_auth, "audit", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module.operations, "get_email_settings", lambda include_secret: {"enabled": True})
    monkeypatch.setattr(
        main_module.admin_auth,
        "create_password_reset",
        lambda username: {
            "token": "one-time-secret-reset-token",
            "email": "staff@example.test",
            "display_name": "Staff",
            "username": username,
        },
    )
    monkeypatch.setattr(main_module, "_send_password_reset_email", lambda config, reset, url: sent_urls.append(url))

    response = TestClient(app).post(
        "/api/admin/auth/password-reset/request", json={"username": "private.staff"}
    )

    assert response.status_code == 200
    assert len(sent_urls) == 1
    assert "?reset_token=" not in sent_urls[0]
    assert sent_urls[0].endswith("#reset_token=one-time-secret-reset-token")


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


def test_manual_account_lock_is_indefinite_until_unlocked(auth_store: AdminAuthStore):
    _, administrator = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    user = auth_store.create_user(
        {
            "username": "manual.lock",
            "display_name": "Manual Lock",
            "password": "InitialPass123!",
            "role_id": "role-super-admin",
            "property_id": None,
            "status": "active",
        },
        administrator,
    )
    auth_store.update_user(user["id"], {"status": "locked"}, administrator)
    with pytest.raises(AccountLockedError, match="Contact an administrator"):
        auth_store.login("manual.lock", "InitialPass123!", "10.0.0.9", "test")
    auth_store.update_user(user["id"], {"status": "active"}, administrator)
    assert auth_store.login("manual.lock", "InitialPass123!", "10.0.0.9", "test")[1].status == "active"


def test_disabled_users_and_revoked_sessions_are_rejected(auth_store: AdminAuthStore):
    _, administrator = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    user = auth_store.create_user(
        {
            "username": "disabled.user",
            "display_name": "Disabled User",
            "password": "DisabledPass123!",
            "role_id": "role-property-administrator",
            "property_id": "demo-hotel",
            "status": "active",
        },
        administrator,
    )
    token, principal = auth_store.login("disabled.user", "DisabledPass123!", "10.0.0.8", "test")
    auth_store.update_user(user["id"], {"status": "disabled"}, administrator)
    assert auth_store.authenticate(token) is None
    with pytest.raises(AuthenticationError, match="Invalid username or password"):
        auth_store.login("disabled.user", "DisabledPass123!", "10.0.0.8", "test")

    auth_store.update_user(user["id"], {"status": "active"}, administrator)
    token, principal = auth_store.login("disabled.user", "DisabledPass123!", "10.0.0.8", "test")
    assert auth_store.revoke_sessions(user["id"], administrator) == 1
    assert auth_store.authenticate(token) is None


def test_property_admin_cannot_delegate_global_permissions_even_with_spoofed_role_slug(auth_store: AdminAuthStore):
    _, global_admin = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    user = auth_store.create_user(
        {
            "username": "property.admin",
            "display_name": "Property Administrator",
            "password": "PropertyPass123!",
            "role_id": "role-property-administrator",
            "property_id": "demo-hotel",
            "status": "active",
        },
        global_admin,
    )
    _, property_admin = auth_store.login("property.admin", "PropertyPass123!", "10.0.0.2", "test")
    with pytest.raises(PermissionError, match="cannot delegate"):
        auth_store.save_role(
            {"name": "Escalated", "property_id": "demo-hotel", "permissions": ["properties.view", "properties.all"]},
            property_admin,
        )
    forged_role = {"role_id": "role-forged", "slug": "super-admin", "property_id": "demo-hotel", "permissions": ["system.configure"]}
    with pytest.raises(PermissionError, match="cannot delegate"):
        auth_store.assert_role_assignment_allowed(property_admin, forged_role, "demo-hotel")


def test_restaurant_assignments_cannot_be_widened_beyond_actor_scope(tmp_path: Path):
    database = tmp_path / "restaurant-assignments.db"
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    hospitality = HospitalityStore(database)
    grill = hospitality.create_restaurant("hotel-a", {"name": "The Grill"})
    cafe = hospitality.create_restaurant("hotel-a", {"name": "Lobby Cafe"})
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("admin", ADMIN_PASSWORD)
    _, super_admin = auth.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    manager = auth.create_user({
        "username": "grill.manager", "display_name": "Grill Manager", "password": "ManagerPass123!",
        "role_id": "role-restaurant-manager", "property_id": "hotel-a", "status": "active",
        "restaurant_ids": [grill["restaurant_id"]],
    }, super_admin)
    staff = auth.create_user({
        "username": "grill.staff", "display_name": "Grill Staff", "password": "StaffMember123!",
        "role_id": "role-restaurant-staff", "property_id": "hotel-a", "status": "active",
        "restaurant_ids": [grill["restaurant_id"]],
    }, super_admin)
    _, manager_principal = auth.login(manager["username"], "ManagerPass123!", "10.0.0.2", "test")
    with pytest.raises(PermissionError, match="assigned to you"):
        auth.update_user(staff["id"], {"restaurant_ids": [cafe["restaurant_id"]]}, manager_principal)
    assert auth.get_user(staff["id"])["restaurant_ids"] == [grill["restaurant_id"]]


def test_default_roles_have_expected_permission_boundaries(auth_store: AdminAuthStore):
    assert set(DEFAULT_ROLES) == {
        "super-admin", "property-administrator", "property-manager", "concierge-front-desk",
        "content-manager", "viewer-auditor", "department-manager", "restaurant-manager", "restaurant-staff",
    }
    super_admin = auth_store.get_role("role-super-admin")
    assert set(super_admin["permissions"]) == set(PERMISSIONS)
    assert "properties.all" not in auth_store.get_role("role-property-administrator")["permissions"]
    assert "security.configure" not in auth_store.get_role("role-property-manager")["permissions"]
    assert "requests.manage" in auth_store.get_role("role-concierge-front-desk")["permissions"]
    assert "knowledge.edit" in auth_store.get_role("role-content-manager")["permissions"]
    assert "properties.edit" not in auth_store.get_role("role-viewer-auditor")["permissions"]
    department_permissions = set(auth_store.get_role("role-department-manager")["permissions"])
    assert {"requests.view", "analytics.view", "assistant.use", "reports.export"} <= department_permissions
    assert "properties.all" not in department_permissions
    assert "infrastructure.view" not in department_permissions
    restaurant_manager = set(auth_store.get_role("role-restaurant-manager")["permissions"])
    assert {"restaurant.menu.edit", "restaurant.menu.approve", "restaurant.promotions.approve", "restaurant.analytics.view", "conversations.assign"} <= restaurant_manager
    assert not ({"properties.all", "system.configure", "security.configure", "users.create", "ai.configure", "dashboard.view", "analytics.view"} & restaurant_manager)
    restaurant_staff = set(auth_store.get_role("role-restaurant-staff")["permissions"])
    assert {"restaurant.view", "restaurant.menu.view", "conversations.takeover", "conversations.reply", "conversations.resolve"} <= restaurant_staff
    assert not ({"restaurant.manage", "restaurant.menu.edit", "restaurant.menu.approve", "restaurant.promotions.approve", "users.create", "roles.manage", "ai.configure"} & restaurant_staff)


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


def test_staff_cannot_export_or_run_infrastructure_tools(auth_store: AdminAuthStore, auth_client: TestClient):
    auth_store.create_user(
        {
            "username": "frontdesk",
            "display_name": "Front Desk",
            "password": "FrontDeskPass123!",
            "role_id": "role-concierge-front-desk",
            "property_id": "demo-hotel",
            "status": "active",
        },
        actor=None,
    )
    csrf = login(auth_client, "frontdesk", "FrontDeskPass123!")

    assert auth_client.get("/api/admin/properties/demo-hotel/reports/export.xlsx").status_code == 403
    diagnostic = auth_client.post(
        "/api/admin/properties/demo-hotel/assistant/query",
        headers={"X-CSRF-Token": csrf},
        json={"question": "Check the database", "period": "24h", "current_page": "overview"},
    )
    assert diagnostic.status_code == 403
    assert "infrastructure.view" in diagnostic.json()["detail"]


def test_property_viewer_does_not_receive_service_request_records(auth_store: AdminAuthStore, auth_client: TestClient):
    auth_store.create_user(
        {
            "username": "content-only",
            "display_name": "Content Only",
            "password": "ContentOnlyPass123!",
            "role_id": "role-content-manager",
            "property_id": "demo-hotel",
            "status": "active",
        },
        actor=None,
    )
    login(auth_client, "content-only", "ContentOnlyPass123!")

    response = auth_client.get("/api/admin/properties/demo-hotel/hospitality")

    assert response.status_code == 200
    assert "facilities" in response.json()
    assert "service_requests" not in response.json()
    assert "notification_rules" not in response.json()


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
