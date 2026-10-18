import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
def auth_client(auth_store: AdminAuthStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    properties = PropertyStore(tmp_path / "auth-properties.db")
    properties.upsert(PropertyRecord(property_id="tenant-a", hotel_name="Test Tenant A"))
    monkeypatch.setattr(main_module, "properties", properties)
    return TestClient(app)


@pytest.fixture
def default_auth_store(tmp_path: Path) -> AdminAuthStore:
    store = AdminAuthStore(tmp_path / "default-admin-auth.db")
    store.ensure_bootstrap_admin("root", "admin")
    return store


@pytest.fixture
def default_auth_client(
    default_auth_store: AdminAuthStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    monkeypatch.setattr(main_module, "admin_auth", default_auth_store)
    properties = PropertyStore(tmp_path / "default-auth-properties.db")
    properties.upsert(PropertyRecord(property_id="tenant-a", hotel_name="Test Tenant A"))
    monkeypatch.setattr(main_module, "properties", properties)
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


def test_initial_root_admin_is_hashed_and_only_uses_default_password_state(default_auth_store: AdminAuthStore):
    with default_auth_store._connect() as db:
        row = db.execute(
            "SELECT password_hash, force_password_change, using_default_password, default_password_prompted FROM admin_users WHERE normalized_username='root'"
        ).fetchone()
    assert row["password_hash"] != "admin"
    assert verify_password("admin", row["password_hash"])
    assert row["force_password_change"] == 0
    assert row["using_default_password"] == 1
    assert row["default_password_prompted"] == 0

    _, principal = default_auth_store.login("root", "admin", "127.0.0.1", "pytest")
    assert principal.username == "root"
    assert principal.using_default_password is True
    assert principal.show_default_password_prompt is True
    assert principal.force_password_change is False
    with pytest.raises(ValueError, match="at least 12 characters"):
        hash_password("admin")


def test_bootstrap_does_not_add_or_reset_an_admin_when_one_already_exists(tmp_path: Path):
    store = AdminAuthStore(tmp_path / "existing-admin.db")
    store.ensure_bootstrap_admin("existing.owner", "Existing-Admin-123!")
    store.ensure_bootstrap_admin("root", "admin")

    with store._connect() as db:
        rows = db.execute("SELECT username FROM admin_users").fetchall()
    assert [row["username"] for row in rows] == ["existing.owner"]
    store.login("existing.owner", "Existing-Admin-123!", "127.0.0.1", "pytest")
    with pytest.raises(AuthenticationError):
        store.login("root", "admin", "127.0.0.1", "pytest")


def test_default_password_skip_keeps_access_and_warning(default_auth_client: TestClient):
    response = default_auth_client.post(
        "/api/admin/auth/login", json={"username": "root", "password": "admin"}
    )
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["using_default_password"] is True
    assert user["show_default_password_prompt"] is True
    assert user["force_password_change"] is False
    default_auth_client.headers.update({"X-CSRF-Token": user["csrf_token"]})

    assert default_auth_client.get("/api/admin/permissions").status_code == 200
    skipped = default_auth_client.post("/api/admin/auth/default-password-prompt/dismiss", json={})
    assert skipped.status_code == 200
    current = default_auth_client.get("/api/admin/auth/me").json()["user"]
    assert current["using_default_password"] is True
    assert current["show_default_password_prompt"] is False
    assert default_auth_client.get("/api/admin/permissions").status_code == 200
    assert "Default Administrator Password" in default_auth_client.get("/admin").text
    assert "Skip for Now" in default_auth_client.get("/admin").text


def test_default_password_change_enforces_policy_and_clears_warning(default_auth_client: TestClient):
    response = default_auth_client.post(
        "/api/admin/auth/login", json={"username": "root", "password": "admin"}
    )
    assert response.status_code == 200
    default_auth_client.headers.update({"X-CSRF-Token": response.json()["user"]["csrf_token"]})

    weak = default_auth_client.post(
        "/api/admin/auth/change-password",
        json={"current_password": "admin", "new_password": "weak"},
    )
    assert weak.status_code == 422
    wrong_current = default_auth_client.post(
        "/api/admin/auth/change-password",
        json={"current_password": "wrong", "new_password": "Secure-New-Password-123!"},
    )
    assert wrong_current.status_code == 422

    changed = default_auth_client.post(
        "/api/admin/auth/change-password",
        json={"current_password": "admin", "new_password": "Secure-New-Password-123!"},
    )
    assert changed.status_code == 200
    current = default_auth_client.get("/api/admin/auth/me").json()["user"]
    assert current["using_default_password"] is False
    assert current["show_default_password_prompt"] is False
    assert default_auth_client.get("/api/admin/permissions").status_code == 200
    with pytest.raises(AuthenticationError):
        main_module.admin_auth.login("root", "admin", "127.0.0.1", "pytest")
    _, principal = main_module.admin_auth.login("root", "Secure-New-Password-123!", "127.0.0.1", "pytest")
    assert principal.using_default_password is False


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
    monkeypatch.setattr(main_module, "settings", replace(main_module.settings, public_base_url="https://concierge.example.test"))

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


def test_parallel_password_reset_confirmation_consumes_token_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AdminAuthStore(tmp_path / "parallel-reset-consumption.db")
    store.ensure_bootstrap_admin("admin", ADMIN_PASSWORD, "Administrator")
    _, actor = store.login("admin", ADMIN_PASSWORD, "127.0.0.1", "pytest")
    user = store.list_users(actor)[0]
    store.update_user(user["id"], {"email": "admin@example.com"}, actor)
    reset = store.create_password_reset("admin")
    assert reset is not None

    barrier = threading.Barrier(2)
    original_token_hash = store._token_hash

    def synchronized_token_hash(token: str) -> str:
        if token == reset["token"]:
            # Both requests reach the claim operation before either can try to
            # consume the one-time token.
            barrier.wait(timeout=5)
        return original_token_hash(token)

    monkeypatch.setattr(store, "_token_hash", synchronized_token_hash)

    def consume(password: str) -> str:
        try:
            store.consume_password_reset(reset["token"], password)
            return "accepted"
        except AuthenticationError:
            return "rejected"
        except sqlite3.Error as exc:
            return f"database-error:{type(exc).__name__}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, ("ParallelResetOne123!", "ParallelResetTwo123!")))

    assert sorted(results) == ["accepted", "rejected"]


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


def test_temporary_lockout_blocks_login(auth_store: AdminAuthStore):
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            auth_store.login("admin", "WrongPassword1!", "10.0.0.5", "test")
    with pytest.raises(AccountLockedError):
        auth_store.login("admin", "WrongPassword1!", "10.0.0.5", "test")
    with pytest.raises(AccountLockedError):
        auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.6", "test")


def test_parallel_failed_logins_atomically_trigger_account_lockout(tmp_path: Path):
    store = AdminAuthStore(tmp_path / "parallel-account-lockout.db", lockout_attempts=3)
    store.ensure_bootstrap_admin("parallel-admin", "ParallelAdmin123!")

    def attempt(_index: int) -> None:
        try:
            store.login("parallel-admin", "WrongPassword123!", "198.51.100.10", "parallel-test")
        except (AuthenticationError, AccountLockedError):
            return
        raise AssertionError("An incorrect password must never authenticate.")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(attempt, range(8)))

    with store._connect() as db:
        user = db.execute(
            "SELECT failed_login_count, status, locked_until FROM admin_users WHERE normalized_username = ?",
            ("parallel-admin",),
        ).fetchone()
    assert user["failed_login_count"] >= 3
    assert user["status"] == "locked"
    assert user["locked_until"] is not None


def test_parallel_login_burst_is_atomically_limited_per_ip(tmp_path: Path):
    store = AdminAuthStore(tmp_path / "parallel-ip-lockout.db")

    def attempt(index: int) -> None:
        try:
            store.login(f"unknown-user-{index}", "WrongPassword123!", "198.51.100.11", "parallel-test")
        except (AuthenticationError, AccountLockedError):
            return
        raise AssertionError("Unknown users must never authenticate.")

    with ThreadPoolExecutor(max_workers=32) as executor:
        list(executor.map(attempt, range(32)))

    with store._connect() as db:
        attempts = db.execute(
            "SELECT COUNT(*) FROM admin_login_attempts WHERE ip_address = ? AND success = 0",
            ("198.51.100.11",),
        ).fetchone()[0]
    assert attempts == 20


def test_temporary_lockout_expires(auth_store: AdminAuthStore):
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            auth_store.login("admin", "WrongPassword1!", "10.0.0.5", "test")
    with pytest.raises(AccountLockedError):
        auth_store.login("admin", "WrongPassword1!", "10.0.0.5", "test")
    with auth_store._connect() as db:
        db.execute(
            "UPDATE admin_users SET locked_until = ? WHERE normalized_username = ?",
            (int(time.time()) - 1, "admin"),
        )
    _, principal = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.5", "test")
    assert principal.status == "active"


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


def test_disabled_account_cannot_login(auth_store: AdminAuthStore):
    _, administrator = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    user = auth_store.create_user(
        {
            "username": "disabled.user",
            "display_name": "Disabled User",
            "password": "DisabledPass123!",
            "role_id": "role-property-administrator",
            "property_id": "tenant-a",
            "status": "active",
        },
        administrator,
    )
    token, principal = auth_store.login("disabled.user", "DisabledPass123!", "10.0.0.8", "test")
    auth_store.update_user(user["id"], {"status": "disabled"}, administrator)
    assert auth_store.authenticate(token) is None
    with pytest.raises(AuthenticationError, match="Invalid username or password"):
        auth_store.login("disabled.user", "DisabledPass123!", "10.0.0.8", "test")


def test_revoked_sessions_are_rejected(auth_store: AdminAuthStore):
    _, administrator = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    user = auth_store.create_user(
        {
            "username": "revoked.user",
            "display_name": "Revoked User",
            "password": "RevokedPass123!",
            "role_id": "role-property-administrator",
            "property_id": "tenant-a",
            "status": "active",
        },
        administrator,
    )
    token, _ = auth_store.login("revoked.user", "RevokedPass123!", "10.0.0.8", "test")
    auth_store.update_user(user["id"], {"status": "active"}, administrator)
    assert auth_store.revoke_sessions(user["id"], administrator) == 1
    assert auth_store.authenticate(token) is None


def test_system_diagnostics_is_super_admin_only_and_sanitized(auth_store: AdminAuthStore, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    monkeypatch.setattr(main_module, "database_ready", lambda _path: None)
    monkeypatch.setattr(main_module, "persisted_schema_revision", lambda _path: "20261005_0001")

    _, super_admin = auth_store.login("admin", ADMIN_PASSWORD, "127.0.0.1", "test")
    auth_store.create_user(
        {
            "username": "property.admin",
            "display_name": "Property Administrator",
            "password": "PropertyAdmin123!",
            "role_id": "role-property-administrator",
            "property_id": "tenant-a",
            "status": "active",
        },
        super_admin,
    )
    monkeypatch.setattr(main_module, "properties", type("Properties", (), {"list": lambda self: []})())
    monkeypatch.setattr(main_module, "ai_provider_store", type("Providers", (), {"list_connections": lambda self, _id: [{"enabled": True, "status": "connected", "api_key": "never-return"}]})())

    with TestClient(app) as client:
        denied = client.post(
            "/api/admin/auth/login",
            json={"username": "property.admin", "password": "PropertyAdmin123!", "remember_me": False},
        )
        assert denied.status_code == 200
        assert client.get("/api/admin/system/diagnostics").status_code == 403

        elevated = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": ADMIN_PASSWORD, "remember_me": False},
        )
        assert elevated.status_code == 200
        response = client.get("/api/admin/system/diagnostics")

    assert response.status_code == 200, response.text
    assert response.json()["database"] == {"type": "sqlite", "status": "healthy"}
    assert "never-return" not in response.text
    assert "api_key" not in response.text


def test_global_health_details_requires_platform_admin_for_role_matrix(
    auth_store: AdminAuthStore, monkeypatch: pytest.MonkeyPatch
):
    from app.hospitality import HospitalityStore

    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    monkeypatch.setattr(main_module.observability, "database_health", lambda: {"state": "healthy"})
    department = HospitalityStore(auth_store.path).upsert_department("tenant-a", {"name": "Front Desk"})
    _, platform_admin = auth_store.login("admin", ADMIN_PASSWORD, "127.0.0.1", "test")
    role_slugs = (
        "property-administrator",
        "content-manager",
        "department-manager",
        "restaurant-manager",
        "restaurant-staff",
        "property-manager",
    )
    credentials: list[tuple[str, str]] = []
    for slug in role_slugs:
        username = slug.replace("-", ".")
        password = "RoleMatrix123!"
        payload = {
            "username": username,
            "display_name": slug,
            "password": password,
            "role_id": f"role-{slug}",
            "property_id": "tenant-a",
            "status": "active",
        }
        if slug == "department-manager":
            payload["department_id"] = department["department_id"]
        auth_store.create_user(payload, platform_admin)
        credentials.append((username, password))

    with TestClient(app) as client:
        assert client.get("/health/details").status_code == 401
        client.cookies.set(main_module.GUEST_SESSION_COOKIE, "guest-session")
        assert client.get("/health/details").status_code == 401
        client.cookies.clear()

        for username, password in [("admin", ADMIN_PASSWORD), *credentials]:
            logged_in = client.post(
                "/api/admin/auth/login",
                json={"username": username, "password": password, "remember_me": False},
            )
            assert logged_in.status_code == 200, logged_in.text
            expected = 200 if username == "admin" else 403
            assert client.get("/health/details").status_code == expected


def test_property_admin_cannot_delegate_global_permissions_even_with_spoofed_role_slug(auth_store: AdminAuthStore):
    _, global_admin = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    user = auth_store.create_user(
        {
            "username": "property.admin",
            "display_name": "Property Administrator",
            "password": "PropertyPass123!",
            "role_id": "role-property-administrator",
            "property_id": "tenant-a",
            "status": "active",
        },
        global_admin,
    )
    _, property_admin = auth_store.login("property.admin", "PropertyPass123!", "10.0.0.2", "test")
    with pytest.raises(PermissionError, match="cannot delegate"):
        auth_store.save_role(
            {"name": "Escalated", "property_id": "tenant-a", "permissions": ["properties.view", "properties.all"]},
            property_admin,
        )
    forged_role = {"role_id": "role-forged", "slug": "super-admin", "property_id": "tenant-a", "permissions": ["system.configure"]}
    with pytest.raises(PermissionError, match="cannot delegate"):
        auth_store.assert_role_assignment_allowed(property_admin, forged_role, "tenant-a")


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
    assert {"network.view", "network.manage"} <= set(auth_store.get_role("role-property-administrator")["permissions"])
    assert "security.configure" not in auth_store.get_role("role-property-manager")["permissions"]
    assert "network.view" in auth_store.get_role("role-property-manager")["permissions"]
    assert "network.manage" not in auth_store.get_role("role-property-manager")["permissions"]
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
    assert not ({"network.view", "network.manage"} & restaurant_manager)
    assert not ({"network.view", "network.manage"} & restaurant_staff)


def test_user_custom_role_and_password_management(auth_client: TestClient):
    csrf = login(auth_client)
    role_response = auth_client.post(
        "/api/admin/roles",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Marketing",
            "description": "Property content and promotions",
            "property_id": "tenant-a",
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
            "property_id": "tenant-a",
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



def test_admin_user_list_is_paginated_filtered_and_stable(auth_client: TestClient):
    csrf = login(auth_client)
    for index in range(5):
        response = auth_client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": f"page-user-{index}",
                "display_name": f"Page User {index}",
                "password": "PageUserPassword123!",
                "property_id": "tenant-a",
                "role_id": "role-property-administrator",
                "status": "disabled" if index == 4 else "active",
            },
        )
        assert response.status_code == 200, response.text

    first = auth_client.get("/api/admin/users?limit=2&offset=0").json()
    second = auth_client.get("/api/admin/users?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 6
    assert len(first["users"]) == len(second["users"]) == 2
    repeated_first = auth_client.get("/api/admin/users?limit=2&offset=0").json()
    assert [user["id"] for user in repeated_first["users"]] == [user["id"] for user in first["users"]]
    first_ids = {user["id"] for user in first["users"]}
    second_ids = {user["id"] for user in second["users"]}
    assert first_ids.isdisjoint(second_ids)

    stale = auth_client.get("/api/admin/users?limit=2&offset=1000000").json()
    assert stale["offset"] == 4
    assert len(stale["users"]) == 2

    filtered = auth_client.get("/api/admin/users?q=PAGE-USER-3&status=active").json()
    assert filtered["total"] == 1
    assert [user["username"] for user in filtered["users"]] == ["page-user-3"]
    assert auth_client.get("/api/admin/users?status=unknown").status_code == 422
    assert auth_client.get("/api/admin/users?limit=0").status_code == 422
    assert auth_client.get("/api/admin/users?offset=-1").status_code == 422


def test_paginated_admin_user_list_keeps_property_scope(auth_client: TestClient):
    csrf = login(auth_client)
    main_module.properties.upsert(PropertyRecord(property_id="tenant-b", hotel_name="Test Tenant B"))
    for username, property_id in (("tenant-a-admin", "tenant-a"), ("tenant-b-admin", "tenant-b")):
        response = auth_client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": username,
                "display_name": username,
                "password": "PropertyAdminPassword123!",
                "property_id": property_id,
                "role_id": "role-property-administrator",
                "status": "active",
                "force_password_change": False,
            },
        )
        assert response.status_code == 200, response.text

    login(auth_client, "tenant-a-admin", "PropertyAdminPassword123!")
    result = auth_client.get("/api/admin/users?limit=100").json()
    assert result["total"] >= 1
    assert {user["property_id"] for user in result["users"]} == {"tenant-a"}

def test_admin_user_list_is_paginated_filtered_and_stable(auth_client: TestClient):
    csrf = login(auth_client)
    for index in range(5):
        response = auth_client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": f"page-user-{index}",
                "display_name": f"Page User {index}",
                "password": "PageUserPassword123!",
                "property_id": "tenant-a",
                "role_id": "role-property-administrator",
                "status": "disabled" if index == 4 else "active",
            },
        )
        assert response.status_code == 200, response.text

    first = auth_client.get("/api/admin/users?limit=2&offset=0").json()
    second = auth_client.get("/api/admin/users?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 6
    assert len(first["users"]) == len(second["users"]) == 2
    repeated_first = auth_client.get("/api/admin/users?limit=2&offset=0").json()
    assert [user["id"] for user in repeated_first["users"]] == [user["id"] for user in first["users"]]
    first_ids = {user["id"] for user in first["users"]}
    second_ids = {user["id"] for user in second["users"]}
    assert first_ids.isdisjoint(second_ids)

    stale = auth_client.get("/api/admin/users?limit=2&offset=1000000").json()
    assert stale["offset"] == 4
    assert len(stale["users"]) == 2

    filtered = auth_client.get("/api/admin/users?q=PAGE-USER-3&status=active").json()
    assert filtered["total"] == 1
    assert [user["username"] for user in filtered["users"]] == ["page-user-3"]
    assert auth_client.get("/api/admin/users?status=unknown").status_code == 422
    assert auth_client.get("/api/admin/users?limit=0").status_code == 422
    assert auth_client.get("/api/admin/users?offset=-1").status_code == 422


def test_paginated_admin_user_list_keeps_property_scope(auth_client: TestClient, auth_store: AdminAuthStore):
    csrf = login(auth_client)
    main_module.properties.upsert(PropertyRecord(property_id="tenant-b", hotel_name="Test Tenant B"))
    for username, property_id in (("tenant-a-admin", "tenant-a"), ("tenant-b-admin", "tenant-b")):
        response = auth_client.post(
            "/api/admin/users",
            headers={"X-CSRF-Token": csrf},
            json={
                "username": username,
                "display_name": username,
                "password": "PropertyAdminPassword123!",
                "property_id": property_id,
                "role_id": "role-property-administrator",
                "status": "active",
                "force_password_change": False,
            },
        )
        assert response.status_code == 200, response.text

    login(auth_client, "tenant-a-admin", "PropertyAdminPassword123!")
    result = auth_client.get("/api/admin/users?limit=100").json()
    assert result["total"] >= 1
    assert {user["property_id"] for user in result["users"]} == {"tenant-a"}


def test_managed_knowledge_page_counts_only_role_visible_items(
    auth_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from app.knowledge_management import KnowledgeStore

    store = KnowledgeStore(tmp_path / "managed-knowledge.db", tmp_path / "managed-uploads")
    monkeypatch.setattr(main_module, "knowledge_management", store)
    admin_item = store.create_draft("tenant-a", "Admin item", "Verified admin-only fact", "Facilities", "admin")
    manager_item = store.create_draft("tenant-a", "Manager item", "Manager-only fact", "Facilities", "admin")
    store.update_item("tenant-a", manager_item["item_id"], {"visibility": "manager"}, "admin")

    csrf = login(auth_client)
    created = auth_client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "content.reviewer",
            "display_name": "Content Reviewer",
            "password": "ContentReviewerPassword123!",
            "property_id": "tenant-a",
            "role_id": "role-content-manager",
            "status": "active",
            "force_password_change": False,
        },
    )
    assert created.status_code == 200, created.text
    login(auth_client, "content.reviewer", "ContentReviewerPassword123!")

    result = auth_client.get("/api/admin/properties/tenant-a/knowledge/managed?limit=1")
    assert result.status_code == 200, result.text
    page = result.json()
    assert page["total"] == 1
    assert [item["item_id"] for item in page["items"]] == [admin_item["item_id"]]
    hidden_search = auth_client.get("/api/admin/properties/tenant-a/knowledge/managed?q=manager")
    assert hidden_search.status_code == 200
    assert hidden_search.json()["total"] == 0
    assert auth_client.get("/api/admin/properties/tenant-a/knowledge/managed?limit=0").status_code == 422


def test_property_admin_cannot_clone_design_from_another_property(
    auth_client: TestClient, auth_store: AdminAuthStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    properties = PropertyStore(tmp_path / "design-clone-scope.db")
    properties.upsert(PropertyRecord(property_id="tenant-a", hotel_name="Test Tenant A"))
    properties.upsert(PropertyRecord(property_id="tenant-b", hotel_name="Test Tenant B"))
    monkeypatch.setattr(main_module, "properties", properties)
    csrf = login(auth_client)
    created = auth_client.post(
        "/api/admin/users",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "tenant.a.designer",
            "display_name": "Tenant A Designer",
            "password": "TenantDesignerPassword123!",
            "property_id": "tenant-a",
            "role_id": "role-property-administrator",
            "status": "active",
            "force_password_change": False,
        },
    )
    assert created.status_code == 200, created.text
    login(auth_client, "tenant.a.designer", "TenantDesignerPassword123!")

    response = auth_client.post(
        "/api/admin/properties/tenant-a/design/clone",
        json={"source_property_id": "tenant-b"},
    )

    assert response.status_code == 403


def test_property_role_cannot_cross_tenant(auth_store: AdminAuthStore, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    super_token, super_principal = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    del super_token
    auth_store.create_user(
        {
            "username": "hotelmanager",
            "display_name": "Hotel Manager",
            "password": "PropertyPass123!",
            "property_id": "tenant-a",
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
    assert {item["property_id"] for item in listed.json()["properties"]} <= {"tenant-a"}
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
            "property_id": "tenant-a",
            "status": "active",
        },
        actor=None,
    )
    csrf = login(auth_client, "frontdesk", "FrontDeskPass123!")

    assert auth_client.get("/api/admin/properties/tenant-a/reports/export.xlsx").status_code == 403
    diagnostic = auth_client.post(
        "/api/admin/properties/tenant-a/assistant/query",
        headers={"X-CSRF-Token": csrf},
        json={"question": "Check the database", "period": "24h", "current_page": "overview"},
    )
    assert diagnostic.status_code == 403
    assert "does not have access to this system check" in diagnostic.json()["detail"]
    assert "infrastructure.view" not in diagnostic.json()["detail"]


def test_location_analytics_permissions_are_separate_from_property_editing(auth_store: AdminAuthStore, auth_client: TestClient):
    _, administrator = auth_store.login("admin", ADMIN_PASSWORD, "10.0.0.1", "test")
    analytics_role = auth_store.save_role({
        "name": "Location Analytics Reader",
        "description": "View aggregate property location analytics",
        "property_id": "tenant-a",
        "permissions": ["analytics.view"],
    }, administrator)
    editor_role = auth_store.save_role({
        "name": "Property Editor Only",
        "description": "Edit property configuration without analytics access",
        "property_id": "tenant-a",
        "permissions": ["properties.edit", "properties.view"],
    }, administrator)
    auth_store.create_user({
        "username": "location.reader", "display_name": "Location Reader", "password": "LocationReader123!",
        "role_id": analytics_role["role_id"], "property_id": "tenant-a", "status": "active",
    }, administrator)
    auth_store.create_user({
        "username": "property.editor", "display_name": "Property Editor", "password": "PropertyEditor123!",
        "role_id": editor_role["role_id"], "property_id": "tenant-a", "status": "active",
    }, administrator)

    reader_csrf = login(auth_client, "location.reader", "LocationReader123!")
    report = auth_client.post(
        "/api/admin/properties/tenant-a/location/report",
        headers={"X-CSRF-Token": reader_csrf},
        json={"start_at": 0, "end_at": 1, "filters": {}},
    )
    assert report.status_code == 200, report.text
    assert auth_client.get("/api/admin/properties/tenant-a/location/live").status_code == 200

    editor_csrf = login(auth_client, "property.editor", "PropertyEditor123!")
    denied_report = auth_client.post(
        "/api/admin/properties/tenant-a/location/report",
        headers={"X-CSRF-Token": editor_csrf},
        json={"start_at": 0, "end_at": 1, "filters": {}},
    )
    assert denied_report.status_code == 403
    assert auth_client.get("/api/admin/properties/tenant-a/location/live").status_code == 403


def test_property_viewer_does_not_receive_service_request_records(auth_store: AdminAuthStore, auth_client: TestClient):
    auth_store.create_user(
        {
            "username": "content-only",
            "display_name": "Content Only",
            "password": "ContentOnlyPass123!",
            "role_id": "role-content-manager",
            "property_id": "tenant-a",
            "status": "active",
        },
        actor=None,
    )
    login(auth_client, "content-only", "ContentOnlyPass123!")

    response = auth_client.get("/api/admin/properties/tenant-a/hospitality")

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


def test_audit_api_returns_stable_bounded_pages_and_clamps_stale_offsets(
    auth_store: AdminAuthStore, auth_client: TestClient
):
    login(auth_client)
    with auth_store._connect() as db:
        for index in range(5):
            db.execute(
                """INSERT INTO admin_audit_logs
                   (timestamp, username, display_name, role_name, property_id, action, resource, resource_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (1000, "pagination-user", "Pagination User", "Auditor", "tenant-a", "pagination.fixture", "fixture", f"row-{index}"),
            )

    first = auth_client.get("/api/admin/audit", params={"action": "pagination.fixture", "limit": 2, "offset": 0})
    second = auth_client.get("/api/admin/audit", params={"action": "pagination.fixture", "limit": 2, "offset": 2})
    stale = auth_client.get("/api/admin/audit", params={"action": "pagination.fixture", "limit": 2, "offset": 99})

    assert first.status_code == second.status_code == stale.status_code == 200
    assert first.json()["total"] == second.json()["total"] == stale.json()["total"] == 5
    assert first.json()["offset"] == 0
    assert second.json()["offset"] == 2
    assert stale.json()["offset"] == 4
    assert [item["resource_id"] for item in first.json()["events"]] == ["row-4", "row-3"]
    assert [item["resource_id"] for item in second.json()["events"]] == ["row-2", "row-1"]
    assert [item["resource_id"] for item in stale.json()["events"]] == ["row-0"]
    assert auth_client.get("/api/admin/audit", params={"limit": 101}).status_code == 422
    assert auth_client.get("/api/admin/audit", params={"offset": -1}).status_code == 422


def test_paged_audit_log_preserves_property_scope(auth_store: AdminAuthStore, auth_client: TestClient):
    _, administrator = auth_store.login("admin", ADMIN_PASSWORD, "127.0.0.1", "test")
    auth_store.create_user(
        {
            "username": "tenant-a-admin",
            "display_name": "Tenant A Admin",
            "password": "TenantAPass123!",
            "role_id": "role-property-administrator",
            "property_id": "tenant-a",
            "status": "active",
        },
        actor=administrator,
    )
    with auth_store._connect() as db:
        for property_id in ("tenant-a", "tenant-b"):
            db.execute(
                """INSERT INTO admin_audit_logs
                   (timestamp, username, display_name, role_name, property_id, action, resource, resource_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (1000, "scoped-user", "Scoped User", "Auditor", property_id, "pagination.scope", "fixture", property_id),
            )

    login(auth_client, "tenant-a-admin", "TenantAPass123!")
    response = auth_client.get("/api/admin/audit", params={"action": "pagination.scope", "limit": 1})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["property_id"] for item in response.json()["events"]] == ["tenant-a"]
