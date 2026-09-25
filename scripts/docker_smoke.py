"""Runtime smoke used by CI against the production container."""

from __future__ import annotations

import argparse
import json
import ipaddress
import os
import urllib.error
import urllib.request


BASE_URL = os.getenv("CONCIERGE_SMOKE_URL", "http://127.0.0.1:8080")
PASSWORD = os.environ["ADMIN_BOOTSTRAP_PASSWORD"]


def request(path: str, method: str = "GET", payload=None, headers=None, *, raw: bool = False):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
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
    property_id = properties[0]["property_id"]
    record = request(f"/api/admin/properties/{property_id}", headers=headers)
    record["domain"] = "hotel-a.test"
    record["hotel_name"] = "Docker Persistence Hotel"
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
    guest_headers = {"Host": "hotel-a.test"}
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
    record = next(item for item in properties if item["property_id"] == "hotel-a")
    if record["hotel_name"] != "Docker Persistence Hotel":
        raise RuntimeError("Property database state did not persist across container recreation.")
    knowledge = request("/api/admin/properties/hotel-a/knowledge", headers=headers)
    if "Persisted knowledge" not in json.dumps(knowledge):
        raise RuntimeError("Knowledge state did not persist.")
    ai = request("/api/admin/properties/hotel-a/ai", headers=headers)
    if ai["settings"]["limits"].get("requests_per_minute") != 10:
        raise RuntimeError("AI configuration did not persist.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["write", "verify"])
    args = parser.parse_args()
    request("/health/ready")
    write_phase() if args.phase == "write" else verify_phase()
    print(json.dumps({"status": "ok", "phase": args.phase}))
