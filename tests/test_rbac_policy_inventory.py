from __future__ import annotations

import re
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import DEFAULT_ROLES, PERMISSIONS, AdminAuthStore
from app.hospitality import HospitalityStore
from app.main import app
from app.rbac import ADMIN_ROUTE_POLICIES, load_admin_route_policies
from app.guardrails import RateLimiter


def _route_inventory() -> list[tuple[str, str, str]]:
    inventory: list[tuple[str, str, str]] = []
    for route in app.routes:
        for method, policy in getattr(route, "admin_policies", {}).items():
            if policy.permission is None:
                continue
            path = re.sub(
                r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                lambda match: "hotel-a" if match.group(1) == "property_id" else f"probe-{match.group(1)}",
                route.path,
            )
            inventory.append((method, path, policy.permission))
    return inventory


def _authenticated_route_inventory() -> list[tuple[str, str]]:
    inventory: list[tuple[str, str]] = []
    for route in app.routes:
        for method, policy in getattr(route, "admin_policies", {}).items():
            if policy.authentication != "required":
                continue
            path = re.sub(
                r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                lambda match: "hotel-a" if match.group(1) == "property_id" else f"probe-{match.group(1)}",
                route.path,
            )
            inventory.append((method, path))
    return inventory


@pytest.fixture(scope="module")
def no_permission_admin_client(tmp_path_factory: pytest.TempPathFactory):
    database = tmp_path_factory.mktemp("rbac-policy") / "rbac.db"
    HospitalityStore(database)
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "RootBaseline123!")
    _, root = auth.login("root", "RootBaseline123!", "127.0.0.1", "rbac-test")
    role = auth.save_role({"name": "No Permissions", "property_id": "hotel-a", "permissions": []}, root)
    user = auth.create_user(
        {
            "username": "no.permissions",
            "display_name": "No Permissions",
            "password": "NoPermissions123!",
            "role_id": role["role_id"],
            "property_id": "hotel-a",
        },
        root,
    )

    previous_auth = main_module.admin_auth
    previous_limiter = main_module.rate_limiter
    main_module.admin_auth = auth
    main_module.rate_limiter = RateLimiter()
    client = TestClient(app)
    login = client.post(
        "/api/admin/auth/login",
        json={"username": user["username"], "password": "NoPermissions123!"},
    )
    assert login.status_code == 200
    yield client
    client.close()
    main_module.admin_auth = previous_auth
    main_module.rate_limiter = previous_limiter


@pytest.fixture(scope="module")
def unauthenticated_admin_client():
    class AnonymousAuth:
        @staticmethod
        def authenticate(_token):
            return None

    previous_auth = main_module.admin_auth
    previous_limiter = main_module.rate_limiter
    main_module.admin_auth = AnonymousAuth()
    main_module.rate_limiter = RateLimiter()
    client = TestClient(app)
    yield client
    client.close()
    main_module.admin_auth = previous_auth
    main_module.rate_limiter = previous_limiter


def test_registered_admin_api_routes_have_exact_policies():
    actual = {
        f"{method} {route.path}"
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/admin/")
        for method in set(getattr(route, "methods", ())) - {"HEAD", "OPTIONS"}
    }
    assert actual == set(ADMIN_ROUTE_POLICIES)
    for route in app.routes:
        if not getattr(route, "path", "").startswith("/api/admin/"):
            continue
        route_policies = getattr(route, "admin_policies", {})
        for method in set(route.methods) - {"HEAD", "OPTIONS"}:
            policy = route_policies[method]
            assert policy.authentication in {"required", "public"}
            assert policy.permission is None or policy.permission in PERMISSIONS


@pytest.mark.parametrize(
    "route_key,item",
    [
        ("GET /api/admin/new-operation", {"permission": None, "authentication": "required"}),
        ("GET /api/admin/new-public-operation", {"permission": None, "authentication": "public"}),
    ],
)
def test_new_permissionless_admin_route_requires_explicit_exception(
    tmp_path: Path, route_key: str, item: dict[str, object]
):
    raw = {key: {"permission": policy.permission, "authentication": policy.authentication}
           for key, policy in ADMIN_ROUTE_POLICIES.items()}
    raw[route_key] = item
    policy_path = tmp_path / "admin-route-policies.json"
    policy_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(RuntimeError, match="no required permission|not approved for public access"):
        load_admin_route_policies(policy_path)


def test_every_system_role_is_present_and_limited_to_known_permissions(tmp_path: Path):
    database = tmp_path / "role-matrix.db"
    HospitalityStore(database)
    auth = AdminAuthStore(database)
    for slug, definition in DEFAULT_ROLES.items():
        role = auth.get_role(f"role-{slug}")
        assert role is not None, f"missing system role: {slug}"
        assert set(role["permissions"]) == set(definition["permissions"])
        assert set(role["permissions"]) <= set(PERMISSIONS)
    assert set(auth.get_role("role-super-admin")["permissions"]) == set(PERMISSIONS)


def test_system_role_matrix_matches_every_admin_route_capability(tmp_path: Path):
    database = tmp_path / "role-route-matrix.db"
    HospitalityStore(database).upsert_department("hotel-a", {"department_id": "housekeeping", "name": "Housekeeping"})
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "MatrixRoot123!")
    _, root = auth.login("root", "MatrixRoot123!", "127.0.0.1", "rbac-matrix")

    for slug, definition in DEFAULT_ROLES.items():
        username = f"matrix-{slug}"
        payload = {
            "username": username,
            "display_name": definition["name"],
            "password": "MatrixUser123!",
            "role_id": f"role-{slug}",
            "property_id": None if slug == "super-admin" else "hotel-a",
            "status": "active",
        }
        if slug == "department-manager":
            payload["department_id"] = "housekeeping"
        user = auth.create_user(payload, root)
        token, principal = auth.login(user["username"], "MatrixUser123!", "127.0.0.1", "rbac-matrix")
        assert auth.authenticate(token) is not None
        expected_permissions = set(definition["permissions"])
        assert set(principal.permissions) == expected_permissions
        for permission in PERMISSIONS:
            assert principal.can(permission) is (permission in expected_permissions), (slug, permission)
        for route in app.routes:
            for policy in getattr(route, "admin_policies", {}).values():
                if policy.permission is not None:
                    assert principal.can(policy.permission) is (policy.permission in expected_permissions)


@pytest.mark.parametrize("method,path", _authenticated_route_inventory(), ids=lambda value: str(value))
def test_every_authenticated_admin_route_rejects_anonymous_requests(
    unauthenticated_admin_client: TestClient,
    method: str,
    path: str,
):
    response = unauthenticated_admin_client.request(method, path)
    assert response.status_code == 401, f"{method} {path} unexpectedly returned {response.status_code}: {response.text}"


@pytest.mark.parametrize("method,path,permission", _route_inventory(), ids=lambda value: str(value))
def test_every_sensitive_admin_route_denies_an_authenticated_user_without_permission(
    no_permission_admin_client: TestClient,
    method: str,
    path: str,
    permission: str,
):
    response = no_permission_admin_client.request(method, path)
    assert response.status_code == 403, f"{method} {path} unexpectedly returned {response.status_code}: {response.text}"
    assert response.json()["detail"] == f"Permission required: {permission}"


def test_csp_has_no_inline_style_exception():
    with TestClient(app) as client:
        response = client.get("/")
    policy = response.headers["content-security-policy"]
    assert "style-src 'self'" in policy
    assert "unsafe-inline" not in policy
