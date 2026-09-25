"""Explicit, fail-closed authorization policies for administrator API routes."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.routing import Match

from .admin_auth import PERMISSIONS


PUBLIC_ADMIN_ROUTES = frozenset(
    {
        "POST /api/admin/auth/login",
        "POST /api/admin/auth/password-reset/request",
        "POST /api/admin/auth/password-reset/confirm",
    }
)
AUTH_ONLY_ADMIN_ROUTES = frozenset(
    {
        "GET /api/admin/auth/me",
        "POST /api/admin/auth/change-password",
        "POST /api/admin/auth/logout",
    }
)


@dataclass(frozen=True)
class AdminRoutePolicy:
    """Authorization rule bound to one concrete method and route template."""

    permission: str | None
    authentication: str


def load_admin_route_policies(path: Path | None = None) -> dict[str, AdminRoutePolicy]:
    policy_path = path or Path(__file__).with_name("admin_route_policies.json")
    raw = json.loads(policy_path.read_text(encoding="utf-8"))
    policies: dict[str, AdminRoutePolicy] = {}
    for route_key, item in raw.items():
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid administrator route policy for {route_key}.")
        permission = item.get("permission")
        authentication = item.get("authentication")
        if permission is not None and not isinstance(permission, str):
            raise RuntimeError(f"Invalid permission for administrator route {route_key}.")
        if permission is not None and permission not in PERMISSIONS:
            raise RuntimeError(f"Unknown permission {permission!r} for administrator route {route_key}.")
        if authentication not in {"required", "public"}:
            raise RuntimeError(f"Invalid authentication mode for administrator route {route_key}.")
        if authentication == "public" and permission is not None:
            raise RuntimeError(f"Public administrator route {route_key} cannot require a permission.")
        if authentication == "public" and route_key not in PUBLIC_ADMIN_ROUTES:
            raise RuntimeError(f"Administrator route is not approved for public access: {route_key}")
        if authentication == "required" and permission is None and route_key not in AUTH_ONLY_ADMIN_ROUTES:
            raise RuntimeError(f"Administrator route has no required permission: {route_key}")
        policies[route_key] = AdminRoutePolicy(permission, authentication)
    return policies


ADMIN_ROUTE_POLICIES = load_admin_route_policies()


def bind_admin_route_policies(app: FastAPI) -> None:
    """Bind static policies and fail application startup for any unlisted route."""
    seen: set[str] = set()
    for route in app.routes:
        route_path = getattr(route, "path", "")
        if not route_path.startswith("/api/admin/"):
            continue
        route_policies: dict[str, AdminRoutePolicy] = {}
        for method in sorted(set(getattr(route, "methods", ())) - {"HEAD", "OPTIONS"}):
            route_key = f"{method} {route_path}"
            policy = ADMIN_ROUTE_POLICIES.get(route_key)
            if policy is None:
                raise RuntimeError(f"Administrator route has no explicit RBAC policy: {route_key}")
            route_policies[method] = policy
            seen.add(route_key)
        setattr(route, "admin_policies", route_policies)

    stale = sorted(set(ADMIN_ROUTE_POLICIES) - seen)
    if stale:
        raise RuntimeError("RBAC inventory contains routes that are not registered: " + ", ".join(stale))


def matched_admin_policy(app: FastAPI, scope: dict[str, Any], method: str) -> tuple[AdminRoutePolicy | None, dict[str, Any]]:
    """Resolve policy from FastAPI's registered route match, including path params."""
    for route in app.routes:
        policies = getattr(route, "admin_policies", None)
        if not policies:
            continue
        match, child_scope = route.matches(scope)
        if match is Match.FULL:
            return policies.get(method), child_scope
    return None, scope
