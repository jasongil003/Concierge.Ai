"""Runtime smoke used by CI against the production container."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import ipaddress
import os
import secrets
import urllib.request
import urllib.error


BASE_URL = os.getenv("CONCIERGE_SMOKE_URL", "http://127.0.0.1:8080")
PASSWORD = os.environ["ADMIN_BOOTSTRAP_PASSWORD"]
PROPERTY_ID = os.getenv("PROPERTY_ID", "ci-property")
PROPERTY_HOST = f"{PROPERTY_ID}.ci.example"
COOKIE_JAR = http.cookiejar.CookieJar()
HTTP_CLIENT = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))


def request(path: str, method: str = "GET", payload=None, headers=None, *, raw: bool = False):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=body, headers=request_headers, method=method)
    try:
        with HTTP_CLIENT.open(req, timeout=15) as response:
            content = response.read()
            return (response, content) if raw else json.loads(content or b"{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc.code} {exc.read().decode(errors='replace')}") from exc


def login() -> tuple[dict[str, str], dict]:
    response, content = request(
        "/api/admin/auth/login",
        "POST",
        {"username": "admin", "password": PASSWORD, "remember_me": False},
        raw=True,
    )
    payload = json.loads(content)
    cookie = response.headers["Set-Cookie"].split(";", 1)[0]
    headers = {"Cookie": cookie, "X-CSRF-Token": payload["user"]["csrf_token"]}
    return headers, payload


def write_phase() -> None:
    headers, _ = login()
    properties = request("/api/admin/properties", headers=headers)["properties"]
    property_id = PROPERTY_ID
    existing = next((item for item in properties if item["property_id"] == property_id), None)
    if existing:
        record = request(f"/api/admin/properties/{property_id}", headers=headers)
    else:
        record = {"property_id": property_id, "hotel_name": "CI Persistence Property"}
    record["domain"] = PROPERTY_HOST
    record["hotel_name"] = "CI Persistence Property"
    request(f"/api/admin/properties/{property_id}", "PUT", record, headers)
    # The production default allows loopback guest traffic. CI reaches the
    # container through Docker's bridge, so permit only this exact smoke-runner
    # source address while retaining guest_network_only enforcement.
    diagnostics = request(f"/api/admin/properties/{property_id}/guardrails/diagnostics", headers=headers)
    source = ipaddress.ip_address(diagnostics["detected_client_ip"])
    guardrails = request(f"/api/admin/properties/{property_id}/guardrails", headers=headers)["config"]
    allowed = list(guardrails.get("allowed_cidrs") or [])
    smoke_network = f"{source}/{source.max_prefixlen}"
    if smoke_network not in allowed:
        allowed.append(smoke_network)
    guardrails["allowed_cidrs"] = allowed
    guardrails["guest_access_hosts"] = [f"guest.{PROPERTY_HOST}"]
    request(f"/api/admin/properties/{property_id}/guardrails", "PUT", {"config": guardrails}, headers)
    request(
        f"/api/admin/properties/{property_id}/knowledge",
        "PUT",
        {"kind": "faq", "question": "Docker verification", "answer": "Persisted knowledge", "enabled": True},
        headers,
    )
    request(
        f"/api/admin/properties/{property_id}/ai/settings",
        "PUT",
        {"default_provider": "local", "routing_mode": "fixed", "local_only": True, "limits": {"requests_per_minute": 10}},
        headers,
    )
    design = request(f"/api/admin/properties/{property_id}/design", headers=headers)["draft"]
    design["theme"]["accent"] = "#125D8A"
    request(f"/api/admin/properties/{property_id}/design/draft", "PUT", {"config": design}, headers)
    request(f"/api/admin/properties/{property_id}/design/publish", "POST", {}, headers)
    department = request(
        f"/api/admin/properties/{property_id}/departments",
        "PUT",
        {"data": {"name": "Docker Housekeeping", "default_sla_minutes": 15}},
        headers,
    )
    service = request(
        f"/api/admin/properties/{property_id}/service-catalog",
        "PUT",
        {"data": {"name": "Docker Towels", "department_id": department["department_id"], "keywords": ["docker-towels"]}},
        headers,
    )
    restaurant = request(
        f"/api/admin/properties/{property_id}/restaurants",
        "POST",
        {"data": {"name": "Docker Persistence Dining", "cuisine": "Test Kitchen"}},
        headers,
    )
    menu = request(
        f"/api/admin/properties/{property_id}/restaurants/{restaurant['restaurant_id']}/menus",
        "POST",
        {"data": {"name": "Docker Persistence Dinner", "meal_period": "dinner"}},
        headers,
    )
    request(
        f"/api/admin/properties/{property_id}/menus/{menu['menu_id']}/items",
        "POST",
        {"data": {"name": "Docker Test Pasta", "description": "Persistence check", "price": "PHP 100"}},
        headers,
    )
    request(f"/api/admin/properties/{property_id}/menus/{menu['menu_id']}/approve", "POST", {}, headers)
    request(f"/api/admin/properties/{property_id}/menus/{menu['menu_id']}/publish", "POST", {}, headers)
    promotion = request(
        f"/api/admin/properties/{property_id}/restaurants/{restaurant['restaurant_id']}/promotions",
        "POST",
        {"data": {"title": "Docker Persistence Promotion", "description": "Test only"}},
        headers,
    )
    request(f"/api/admin/properties/{property_id}/promotions/{promotion['promotion_id']}/approve", "POST", {}, headers)
    request(f"/api/admin/properties/{property_id}/promotions/{promotion['promotion_id']}/publish", "POST", {}, headers)
    request(
        "/api/admin/users",
        "POST",
        {
            "username": "docker.persistence.manager",
            "display_name": "Docker Persistence Manager",
            "password": f"{secrets.token_urlsafe(32)}A!9",
            "property_id": property_id,
            "role_id": "role-property-administrator",
            "status": "active",
            "force_password_change": False,
        },
        headers,
    )
    guest_headers = {"Host": PROPERTY_HOST}
    session = request("/api/session/start", "POST", {"client_id": "docker-smoke"}, guest_headers)
    request(
        "/api/guest/service-requests",
        "POST",
        {"session_id": session["session_id"], "service_id": service["service_id"], "description": "Runtime persistence proof", "confirmed": True},
        guest_headers,
    )
    response, content = request(f"/api/admin/properties/{property_id}/reports/export.xlsx", headers=headers, raw=True)
    if response.status != 200 or len(content) < 500:
        raise RuntimeError("XLSX report was not generated.")
    details = request("/health/details", headers=headers)
    if details["database"]["state"] not in {"healthy", "warning"}:
        raise RuntimeError("Detailed health database probe failed.")


def verify_phase() -> None:
    headers, _ = login()
    properties = request("/api/admin/properties", headers=headers)["properties"]
    record = next(item for item in properties if item["property_id"] == PROPERTY_ID)
    if record["hotel_name"] != "CI Persistence Property":
        raise RuntimeError("Property database state did not persist across container recreation.")
    knowledge = request(f"/api/admin/properties/{PROPERTY_ID}/knowledge", headers=headers)
    if "Persisted knowledge" not in json.dumps(knowledge):
        raise RuntimeError("Knowledge state did not persist.")
    ai = request(f"/api/admin/properties/{PROPERTY_ID}/ai", headers=headers)
    if ai["settings"]["limits"].get("requests_per_minute") != 10:
        raise RuntimeError("AI configuration did not persist.")
    guardrails = request(f"/api/admin/properties/{PROPERTY_ID}/guardrails", headers=headers)["config"]
    if guardrails.get("guest_access_hosts") != [f"guest.{PROPERTY_HOST}"]:
        raise RuntimeError("Guest host configuration did not persist.")
    design = request(f"/api/admin/properties/{PROPERTY_ID}/design", headers=headers)
    if design["published"]["theme"].get("accent") != "#125D8A":
        raise RuntimeError("Published guest interface configuration did not persist.")
    restaurants = request(f"/api/admin/properties/{PROPERTY_ID}/restaurants", headers=headers)["restaurants"]
    restaurant = next((item for item in restaurants if item["name"] == "Docker Persistence Dining"), None)
    if not restaurant:
        raise RuntimeError("Restaurant configuration did not persist.")
    menus = request(
        f"/api/admin/properties/{PROPERTY_ID}/restaurants/{restaurant['restaurant_id']}/menus", headers=headers
    )["menus"]
    if not any(menu["name"] == "Docker Persistence Dinner" and menu["workflow_status"] == "published" for menu in menus):
        raise RuntimeError("Menu configuration did not persist.")
    promotions = request(
        f"/api/admin/properties/{PROPERTY_ID}/restaurants/{restaurant['restaurant_id']}/promotions", headers=headers
    )["promotions"]
    if not any(item["title"] == "Docker Persistence Promotion" and item["status"] == "published" for item in promotions):
        raise RuntimeError("Promotion configuration did not persist.")
    users = request("/api/admin/users", headers=headers)["users"]
    if not any(item["username"] == "docker.persistence.manager" for item in users):
        raise RuntimeError("Role and user configuration did not persist.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["write", "verify"])
    args = parser.parse_args()
    request("/health/ready")
    write_phase() if args.phase == "write" else verify_phase()
    print(json.dumps({"status": "ok", "phase": args.phase}))
