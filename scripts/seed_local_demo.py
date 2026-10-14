#!/usr/bin/env python3
"""Seed Hotel De Luna through the existing authenticated local Admin APIs."""

from __future__ import annotations

import argparse
import base64
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


PROPERTY_ID = "hotel-de-luna-demo"
ADMIN_USERNAME = "demo-admin"
PLACEHOLDER_IMAGE = "/static/assets/demo/food-placeholder.svg"


def _is_loopback_demo_url(value: str) -> bool:
    """Accept only the exact HTTP loopback origin used by the demo launcher."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    return bool(
        parsed.scheme == "http"
        and parsed.hostname == "127.0.0.1"
        and port is not None
        and not parsed.username
        and not parsed.password
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def local_credentials() -> dict:
    from local_demo_credentials import ensure_credentials

    return ensure_credentials()["accounts"]

RESTAURANTS = [
    {
        "name": "Luna Grand Dining", "cuisine": "International buffet",
        "location": "Ground floor, beside the Main Lobby", "phone_extension": "2101 (fictional)",
        "description": "An all-day international buffet with Filipino, Asian, and European demo dishes.",
        "opening_hours": {"display": "Daily, 06:00–22:00 (demo hours)"},
        "meal_periods": ["breakfast", "lunch", "dinner"], "reservation_available": True,
        "contact_details": {"phone": "Local extension 2101 (fictional)"},
        "guest_notes": "Fictional Hotel De Luna outlet. Menu, prices, and hours are demo data.",
        "items": [
            ("Manila breakfast buffet", "Eggs, pandesal, seasonal fruit, and Filipino breakfast favorites.", "PHP 1,250 (DEMO DATA)", ["vegetarian option"], ["egg", "gluten"]),
            ("Garden vegetable curry", "Coconut curry with steamed rice; ask staff about ingredients.", "PHP 680 (DEMO DATA)", ["vegetarian", "vegan option"], ["coconut"]),
            ("Grilled salmon plate", "Salmon, greens, and calamansi rice.", "PHP 980 (DEMO DATA)", ["gluten-free option"], ["fish"]),
        ],
    },
    {
        "name": "Sora Japanese Restaurant", "cuisine": "Japanese",
        "location": "Ground floor, East Dining Wing", "phone_extension": "2202 (fictional)",
        "description": "A fictional Japanese dining room serving sushi, tempura, and seasonal set meals.",
        "opening_hours": {"display": "Daily, 11:30–14:30 and 17:30–22:00 (demo hours)"},
        "meal_periods": ["lunch", "dinner"], "reservation_available": True,
        "contact_details": {"phone": "Local extension 2202 (fictional)"},
        "guest_notes": "Fictional Hotel De Luna outlet. Menu, prices, and hours are demo data.",
        "items": [
            ("Sora sushi set", "Chef selection of nigiri and maki; ask staff about raw fish and allergens.", "PHP 1,100 (DEMO DATA)", [], ["fish", "soy"]),
            ("Vegetable tempura", "Seasonal vegetables in a light batter.", "PHP 520 (DEMO DATA)", ["vegetarian"], ["gluten", "soy"]),
            ("Miso-glazed eggplant", "Grilled eggplant with miso glaze and rice.", "PHP 460 (DEMO DATA)", ["vegetarian"], ["soy"]),
        ],
    },
    {
        "name": "The Garden Café", "cuisine": "Coffee, pastries, and light meals",
        "location": "Ground floor, Garden Courtyard", "phone_extension": "2303 (fictional)",
        "description": "A relaxed café for espresso, pastries, sandwiches, and light meals.",
        "opening_hours": {"display": "Daily, 07:00–20:00 (demo hours)"},
        "meal_periods": ["breakfast", "lunch", "all_day"], "reservation_available": False,
        "contact_details": {"phone": "Local extension 2303 (fictional)"},
        "guest_notes": "Fictional Hotel De Luna outlet. Menu, prices, and hours are demo data.",
        "items": [
            ("Calamansi cheesecake", "Creamy cheesecake with a calamansi finish.", "PHP 320 (DEMO DATA)", ["vegetarian"], ["dairy", "egg", "gluten"]),
            ("Ube latte", "Espresso with ube and milk; non-dairy milk is a demo option.", "PHP 240 (DEMO DATA)", ["vegetarian"], ["dairy"]),
            ("Garden chicken sandwich", "Roasted chicken, lettuce, and tomato on sourdough.", "PHP 390 (DEMO DATA)", [], ["gluten", "egg"]),
        ],
    },
    {
        "name": "Sky Lounge", "cuisine": "Rooftop dining",
        "location": "12th floor, South Terrace", "phone_extension": "2404 (fictional)",
        "description": "A fictional rooftop lounge with Manila-inspired small plates and skyline views.",
        "opening_hours": {"display": "Daily, 16:00–23:00 (demo hours; weather dependent)"},
        "meal_periods": ["dinner", "late_night"], "reservation_available": True,
        "contact_details": {"phone": "Local extension 2404 (fictional)"},
        "guest_notes": "Fictional Hotel De Luna outlet. Menu, prices, and hours are demo data.",
        "items": [
            ("Manila sunset tasting plate", "Demo selection of local-inspired small plates.", "PHP 1,450 (DEMO DATA)", [], ["soy", "fish"]),
            ("Crispy tofu sisig", "Plant-forward sizzling tofu with rice.", "PHP 620 (DEMO DATA)", ["vegetarian"], ["soy"]),
            ("Calamansi spritz", "Non-alcoholic citrus and soda demo drink.", "PHP 280 (DEMO DATA)", ["vegan", "alcohol-free"], []),
        ],
    },
]

FACILITIES = [
    {"name": "Swimming Pool", "facility_type": "pool", "location": "12th floor, West Terrace", "zone": "Pool Terrace", "floor": "12th Floor", "hours": "Daily, 06:00–21:00 (demo hours)", "description": "Outdoor lap and leisure pool; lifeguard availability is not represented by this demo.", "policies": ["Children must be supervised by an adult.", "Pool access and hours are demo data."]},
    {"name": "Fitness Center", "facility_type": "fitness", "location": "12th floor, North Wing", "zone": "Fitness Center", "floor": "12th Floor", "hours": "Daily, 05:00–23:00 (demo hours)", "description": "Guest fitness room with cardio equipment and free weights.", "policies": ["Use equipment at your own risk.", "Hours and availability are demo data."]},
    {"name": "Luna Spa", "facility_type": "spa", "location": "12th floor, East Wing", "zone": "Luna Spa", "floor": "12th Floor", "hours": "Daily, 10:00–22:00 (demo hours)", "description": "Fictional wellness rooms offering sample massage and relaxation services.", "policies": ["Treatments require confirmation.", "Service availability and hours are demo data."]},
    {"name": "Business Center", "facility_type": "business_center", "location": "Ground floor, beside Reception", "zone": "Business Center", "floor": "Ground Floor", "hours": "Daily, 07:00–22:00 (demo hours)", "description": "Shared work tables, printing desk, and two bookable work pods.", "policies": ["Printing charges are not configured in this demo."]},
    {"name": "Meeting Rooms", "facility_type": "meeting_room", "location": "Ground floor, North Corridor", "zone": "Meeting Rooms", "floor": "Ground Floor", "hours": "By reservation (demo availability)", "description": "Two fictional meeting rooms available for demonstration; no live calendar is connected.", "policies": ["Availability must be confirmed by the Concierge."]},
    {"name": "Concierge Desk", "facility_type": "concierge", "location": "Ground floor, Main Lobby", "zone": "Main Lobby", "floor": "Ground Floor", "hours": "Daily, 24 hours (demo hours)", "description": "The fictional hotel concierge desk is beside Reception.", "policies": ["Contact details in this demo are fictional."]},
    {"name": "Reception", "facility_type": "reception", "location": "Ground floor, Main Lobby", "zone": "Main Lobby", "floor": "Ground Floor", "hours": "Daily, 24 hours (demo hours)", "description": "Front desk for guest assistance and stay questions.", "policies": ["Hotel and contact details are synthetic demo content."]},
    {"name": "Parking", "facility_type": "parking", "location": "Basement 1, access from Luna Street", "zone": "Parking", "floor": "Basement 1", "hours": "Daily, 24 hours (demo hours)", "description": "Fictional hotel parking entrance; spaces and fees are not connected to a live service.", "policies": ["Parking capacity and fees are not configured."]},
    {"name": "Elevators", "facility_type": "elevator", "location": "Main Lobby and each guest floor", "zone": "Main Lobby", "floor": "Ground Floor", "hours": "Daily, 24 hours (demo hours)", "description": "Passenger elevators connect the lobby, guest floors, and rooftop facilities.", "policies": ["In an emergency, follow posted building instructions."]},
    {"name": "Luna Grand Dining", "facility_type": "restaurant", "location": "Ground floor, beside the Main Lobby", "zone": "Luna Grand Dining", "floor": "Ground Floor", "hours": "Daily, 06:00–22:00 (demo hours)", "description": "Fictional international buffet outlet; all hours and menu information are demo data.", "policies": ["Menu prices and availability are demo data."]},
    {"name": "Sora Japanese Restaurant", "facility_type": "restaurant", "location": "Ground floor, East Dining Wing", "zone": "Sora Japanese Restaurant", "floor": "Ground Floor", "hours": "Daily, 11:30–14:30 and 17:30–22:00 (demo hours)", "description": "Fictional Japanese dining outlet; all hours and menu information are demo data.", "policies": ["Menu prices and availability are demo data."]},
    {"name": "The Garden Café", "facility_type": "restaurant", "location": "Ground floor, Garden Courtyard", "zone": "Garden Courtyard", "floor": "Ground Floor", "hours": "Daily, 07:00–20:00 (demo hours)", "description": "Fictional café; all hours and menu information are demo data.", "policies": ["Menu prices and availability are demo data."]},
    {"name": "Sky Lounge", "facility_type": "restaurant", "location": "12th floor, South Terrace", "zone": "Sky Lounge", "floor": "12th Floor", "hours": "Daily, 16:00–23:00 (demo hours; weather dependent)", "description": "Fictional rooftop dining outlet; all hours and menu information are demo data.", "policies": ["Menu prices and availability are demo data."]},
]

SERVICES = [
    ("Extra pillows", "Housekeeping", ["extra pillow", "extra pillows", "pillow", "pillows"], "One or more additional pillows for the guest room.", 15),
    ("Extra towels", "Housekeeping", ["extra towel", "extra towels", "towel", "towels"], "Fresh bath or hand towels for the guest room.", 15),
    ("Housekeeping visit", "Housekeeping", ["housekeeping", "room cleaning", "clean my room", "cleaning"], "A housekeeping visit or room refresh.", 30),
    ("Drinking water", "Housekeeping", ["drinking water", "water bottles", "bottled water"], "Drinking water for the guest room.", 15),
    ("Maintenance assistance", "Engineering", ["maintenance", "repair", "broken", "not working"], "A maintenance colleague to inspect a room issue.", 30),
    ("Laundry pickup", "Laundry", ["laundry pickup", "laundry", "dry cleaning", "wash clothes"], "A staff member to collect laundry from the room.", 45),
    ("Wake-up call", "Front Desk", ["wake-up call", "wake up call", "morning call"], "A requested wake-up call; no telephony integration is connected.", 15),
]

ATTRACTIONS = [
    ("Rizal Park", "Park", "Ermita, Manila", "A real public park and national landmark. This demo recommendation does not provide live hours or travel-time data."),
    ("Intramuros", "Historic district", "Intramuros, Manila", "A real historic district in Manila. This demo recommendation does not provide live opening hours or access conditions."),
    ("National Museum of Fine Arts", "Museum", "Padre Burgos Avenue, Ermita, Manila", "A real public museum. Check the museum's official information for current hours and visitor guidance."),
]


class DemoAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf = ""

    def call(self, method: str, path: str, data: dict | None = None, *, authenticated: bool = True):
        headers = {"Accept": "application/json"}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        if authenticated and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        req = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=20) as response:
                content = response.read()
                return json.loads(content) if content else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Cannot reach {self.base_url}: {exc}") from exc

    def login(self) -> None:
        credentials = local_credentials()["admin"]
        result = self.call(
            "POST", "/api/admin/auth/login",
            {"username": credentials["username"], "password": credentials["password"], "remember_me": False},
            authenticated=False,
        )
        self.csrf = str(result.get("user", {}).get("csrf_token") or "")
        if not self.csrf:
            raise RuntimeError("Admin login succeeded without a CSRF token; refusing to seed.")


def payload(value: dict) -> dict:
    return {"data": value}


def upsert_property(api: DemoAPI) -> None:
    profile = {
        "property_id": PROPERTY_ID,
        "hotel_name": "Hotel De Luna",
        "description": "Hotel De Luna is a fictional five-star luxury hotel in Manila, created entirely for local Concierge.AI testing. All hotel-specific policies, facilities, dining, prices, schedules, phone extensions, and request fulfillment are demo data.",
        "timezone": "Asia/Manila",
        "address": "100 Luna Crescent, Ermita, Manila (fictional address; demo data)",
        "contact_details": {
            "phone": "+63 2 8555 1208 (fictional demo number)",
            "checkin": "15:00 (demo policy)",
            "checkout": "12:00 noon (demo policy)",
            "wifi_guidance": "Connect to the fictional HotelDeLuna-Guest network. Demo access code: LUNA-DEMO-1208. This code works only in the local demo.",
            "breakfast": "Breakfast demo service is available at Luna Grand Dining, 06:00–10:30.",
        },
        "concierge_name": "Luna Concierge",
        "primary_color": "#987346",
        "secondary_color": "#f5f0e8",
        "languages": ["en", "fil"],
        "facilities": [{"name": item["name"], "description": item["description"]} for item in FACILITIES],
        "dining": [{"name": item["name"], "description": item["description"]} for item in RESTAURANTS],
        "pool": {"name": "Swimming Pool", "location": "12th floor, West Terrace", "hours": "Daily, 06:00–21:00 (demo hours)", "description": "Outdoor lap and leisure pool; all details are demo data."},
        "gym": {"name": "Fitness Center", "location": "12th floor, North Wing", "hours": "Daily, 05:00–23:00 (demo hours)", "description": "Guest fitness room; all details are demo data."},
        "spa": {"name": "Luna Spa", "location": "12th floor, East Wing", "hours": "Daily, 10:00–22:00 (demo hours)", "description": "Fictional wellness rooms; appointments are not connected to a live booking system."},
        "policies": [
            {"title": "Check-in", "content": "Standard check-in is 15:00. Early arrival is subject to availability. DEMO POLICY."},
            {"title": "Checkout", "content": "Standard checkout is 12:00 noon. Late checkout must be confirmed with Reception. DEMO POLICY."},
            {"title": "Reception", "content": "Reception and the Concierge Desk are on the Ground Floor in the Main Lobby. Local extension 1000 is fictional demo data."},
            {"title": "Wi-Fi", "content": "Network: HotelDeLuna-Guest. Demo access code: LUNA-DEMO-1208. This code works only in the local demo."},
            {"title": "Room service", "content": "Room service demo requests are available from 06:00 to 23:00. Call fictional local extension 2000; menus and fulfillment are simulated."},
            {"title": "Housekeeping", "content": "Housekeeping demo requests can be submitted through Concierge.AI. Service times and fulfillment are simulated."},
            {"title": "Laundry", "content": "Laundry pickup is a demo request available until 18:00. Cleaning fees are not configured."},
            {"title": "Accessibility", "content": "Step-free entry, accessible elevators, and one demo accessible guest room are listed. Contact Reception to confirm individual requirements; no physical property exists."},
            {"title": "Emergency", "content": "For a real emergency, contact local emergency services. Within fictional Hotel De Luna, alert Reception at extension 1000 (fictional). Do not use demo numbers for real emergencies."},
            {"title": "Hotel rules", "content": "Keep noise low after 22:00; smoking is not permitted in indoor areas; pool access requires adult supervision for children. These are fictional demo policies."},
        ],
        "support_contacts": [
            {"name": "Reception", "department": "Front Desk", "phone": "Local extension 1000 (fictional demo number)"},
            {"name": "Concierge Desk", "department": "Concierge", "phone": "Local extension 1001 (fictional demo number)"},
            {"name": "Room Service", "department": "Dining", "phone": "Local extension 2000 (fictional demo number)"},
            {"name": "Housekeeping", "department": "Housekeeping", "phone": "Local extension 3000 (fictional demo number)"},
            {"name": "Laundry", "department": "Laundry", "phone": "Local extension 3100 (fictional demo number)"},
            {"name": "Security", "department": "Security", "phone": "Local extension 1100 (fictional demo number)"},
        ],
        "quick_actions": [
            {"label": "Explore dining", "prompt": "I'm hungry."},
            {"label": "Ask about checkout", "prompt": "What time is checkout?"},
            {"label": "Find the pool", "prompt": "Where is the swimming pool?"},
            {"label": "Request an item", "prompt": "Can you send two extra pillows to my room?"},
        ],
        "rooms": [{"room": "1208", "room_type": "Demo Deluxe King", "synthetic": True}],
        "app_settings": {
            "application": {"default_language": "en", "timezone": "Asia/Manila"},
            "guest_experience": {
                "intelligent_ui": {"enabled": True},
                "welcome_message": "Welcome to Hotel De Luna. I'm your local demo concierge. What can I help with?",
                "suggested_prompts": ["I'm hungry.", "What time is checkout?", "Where is the swimming pool?", "Can you send two extra pillows to my room?"],
            },
        },
        "antlabs_config": {
            "authentication_enabled": True,
            "authentication_types": {"pms": {"label": "Demo Room Login", "enabled": True}},
        },
        "guardrails": {"directions_enabled": True, "guest_session_timeout": 60},
        "welcome": "Welcome to Hotel De Luna. All property information in this local demo is fictional.",
    }
    api.call("PUT", f"/api/admin/properties/{PROPERTY_ID}", profile)


def ensure_map(api: DemoAPI) -> tuple[dict[str, str], dict[str, str]]:
    base = f"/api/admin/properties/{PROPERTY_ID}"
    overview = api.call("GET", f"{base}/zones")
    building = next((item for item in overview.get("buildings", []) if item.get("name") == "Hotel De Luna (DEMO)"), None)
    if not building:
        building = api.call("POST", f"{base}/buildings", payload({"name": "Hotel De Luna (DEMO)", "description": "Fictional Manila demo property. Map coordinates and routes are illustrative."}))

    floors_by_name = {item.get("name"): item for item in overview.get("floors", []) if item.get("building_id") == building["building_id"]}
    floors: dict[str, str] = {}
    for name, level in (("Basement 1", -1), ("Ground Floor", 0), ("12th Floor", 12)):
        floor = floors_by_name.get(name)
        if not floor:
            floor = api.call("POST", f"{base}/floors", payload({"building_id": building["building_id"], "name": name, "level": level}))
        floors[name] = floor["floor_id"]

    overview = api.call("GET", f"{base}/zones")
    map_specs = [
        ("Basement 1", "hotel-de-luna-basement-1-demo.svg", _basement_map()),
        ("Ground Floor", "hotel-de-luna-ground-demo.svg", _ground_floor_map()),
        ("12th Floor", "hotel-de-luna-level-12-demo.svg", _twelfth_floor_map()),
    ]
    for floor_name, filename, svg in map_specs:
        present = any(item.get("floor_id") == floors[floor_name] and item.get("original_filename") == filename for item in overview.get("maps", []))
        if not present:
            api.call("POST", f"{base}/floors/{floors[floor_name]}/maps", {
                "filename": filename, "content_type": "image/svg+xml",
                "content_base64": base64.b64encode(svg.encode("utf-8")).decode("ascii"),
                "width": 1200, "height": 800,
            })

    zone_specs = [
        ("zone-main-lobby", "Main Lobby", "Ground Floor", "lobby", {"type": "rectangle", "x": 60, "y": 80, "width": 420, "height": 260}),
        ("zone-grand-dining", "Luna Grand Dining", "Ground Floor", "dining", {"type": "rectangle", "x": 510, "y": 80, "width": 300, "height": 250}),
        ("zone-garden-cafe", "Garden Courtyard", "Ground Floor", "dining", {"type": "rectangle", "x": 850, "y": 80, "width": 280, "height": 250}),
        ("zone-sora", "Sora Japanese Restaurant", "Ground Floor", "dining", {"type": "rectangle", "x": 790, "y": 410, "width": 340, "height": 240}),
        ("zone-parking", "Parking", "Basement 1", "parking", {"type": "rectangle", "x": 70, "y": 120, "width": 700, "height": 420}),
        ("zone-business", "Business Center", "Ground Floor", "business", {"type": "rectangle", "x": 60, "y": 410, "width": 300, "height": 240}),
        ("zone-meetings", "Meeting Rooms", "Ground Floor", "meeting", {"type": "rectangle", "x": 390, "y": 410, "width": 360, "height": 240}),
        ("zone-pool", "Pool Terrace", "12th Floor", "pool", {"type": "rectangle", "x": 60, "y": 80, "width": 520, "height": 330}),
        ("zone-fitness", "Fitness Center", "12th Floor", "fitness", {"type": "rectangle", "x": 630, "y": 80, "width": 240, "height": 330}),
        ("zone-spa", "Luna Spa", "12th Floor", "spa", {"type": "rectangle", "x": 900, "y": 80, "width": 230, "height": 330}),
        ("zone-sky-lounge", "Sky Lounge", "12th Floor", "dining", {"type": "rectangle", "x": 300, "y": 470, "width": 600, "height": 180}),
    ]
    existing_zones = {item.get("zone_id"): item for item in overview.get("zones", [])}
    zone_ids: dict[str, str] = {}
    for zone_id, name, floor_name, category, geometry in zone_specs:
        api.call("PUT", f"{base}/zones", payload({
            "zone_id": zone_id, "name": name, "floor_id": floors[floor_name],
            "category": category, "geometry": geometry, "guest_visible": True,
        }))
        zone_ids[name] = zone_id

    overview = api.call("GET", f"{base}/zones")
    existing_nodes = {item.get("label"): item for item in overview.get("navigation_nodes", [])}
    nodes: dict[str, str] = {}
    node_specs = [
        ("Parking Entrance", "Basement 1", "zone-parking", 420, 360),
        ("Basement 1 Elevators", "Basement 1", "zone-parking", 850, 360),
        ("Main Lobby", "Ground Floor", "zone-main-lobby", 250, 220),
        ("Ground Floor Elevators", "Ground Floor", "zone-main-lobby", 420, 350),
        ("Pool Entrance", "12th Floor", "zone-pool", 300, 430),
        ("12th Floor Elevators", "12th Floor", "zone-fitness", 600, 430),
        ("Fitness Center", "12th Floor", "zone-fitness", 740, 220),
        ("Luna Spa", "12th Floor", "zone-spa", 1000, 220),
        ("Sky Lounge", "12th Floor", "zone-sky-lounge", 600, 560),
    ]
    for label, floor_name, zone_id, x, y in node_specs:
        node = existing_nodes.get(label)
        if not node:
            node = api.call("POST", f"{base}/navigation/nodes", payload({
                "floor_id": floors[floor_name], "zone_id": zone_id, "label": label,
                "x": x, "y": y, "node_type": "facility", "guest_visible": True,
            }))
        nodes[label] = node["node_id"]

    existing_edges = {(item.get("from_node_id"), item.get("to_node_id")) for item in overview.get("navigation_edges", [])}
    for start, end, distance in [
        ("Basement 1 Elevators", "Ground Floor Elevators", 80),
        ("Main Lobby", "Ground Floor Elevators", 35),
        ("Ground Floor Elevators", "12th Floor Elevators", 120),
        ("12th Floor Elevators", "Pool Entrance", 28),
        ("12th Floor Elevators", "Fitness Center", 40),
        ("12th Floor Elevators", "Luna Spa", 60),
        ("12th Floor Elevators", "Sky Lounge", 75),
    ]:
        forward, reverse = (nodes[start], nodes[end]), (nodes[end], nodes[start])
        if forward not in existing_edges and reverse not in existing_edges:
            api.call("POST", f"{base}/navigation/edges", payload({
                "from_node_id": nodes[start], "to_node_id": nodes[end],
                "distance": distance, "bidirectional": True, "guest_visible": True,
            }))
    return floors, zone_ids


def _ground_floor_map() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800" role="img" aria-labelledby="title desc">
<title id="title">Hotel De Luna fictional ground floor map</title><desc id="desc">Illustrative demo plan with lobby, restaurants, business center, and meeting rooms.</desc>
<rect width="1200" height="800" fill="#f6f1e8"/><text x="60" y="48" font-family="sans-serif" font-size="28" font-weight="700" fill="#493c2b">HOTEL DE LUNA · GROUND FLOOR (DEMO)</text>
<g fill="#fff" stroke="#9a805c" stroke-width="4"><rect x="60" y="80" width="420" height="260" rx="22"/><rect x="510" y="80" width="300" height="250" rx="22"/><rect x="850" y="80" width="280" height="250" rx="22"/><rect x="60" y="410" width="300" height="240" rx="22"/><rect x="390" y="410" width="360" height="240" rx="22"/><rect x="800" y="410" width="330" height="240" rx="22"/></g>
<g font-family="sans-serif" font-size="22" text-anchor="middle" fill="#493c2b"><text x="270" y="190">MAIN LOBBY</text><text x="660" y="190">LUNA GRAND DINING</text><text x="990" y="190">GARDEN CAFÉ</text><text x="210" y="520">BUSINESS CENTER</text><text x="570" y="520">MEETING ROOMS</text><text x="965" y="520">SORA JAPANESE RESTAURANT</text></g>
<path d="M270 220 L270 370 L965 370 L965 500" fill="none" stroke="#987346" stroke-width="9" stroke-dasharray="16 12"/><text x="60" y="740" font-family="sans-serif" font-size="18" fill="#6e655a">Illustrative layout only · all property locations are fictional</text></svg>'''


def _twelfth_floor_map() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800" role="img" aria-labelledby="title desc">
<title id="title">Hotel De Luna fictional twelfth floor map</title><desc id="desc">Illustrative demo plan with pool, fitness center, spa, and rooftop lounge.</desc>
<rect width="1200" height="800" fill="#edf2ef"/><text x="60" y="48" font-family="sans-serif" font-size="28" font-weight="700" fill="#30443f">HOTEL DE LUNA · 12TH FLOOR (DEMO)</text>
<g fill="#fff" stroke="#6d8e82" stroke-width="4"><rect x="60" y="80" width="520" height="330" rx="22"/><rect x="630" y="80" width="240" height="330" rx="22"/><rect x="900" y="80" width="230" height="330" rx="22"/><rect x="300" y="470" width="600" height="180" rx="22"/><rect x="930" y="470" width="200" height="180" rx="22"/></g>
<rect x="115" y="150" width="410" height="190" rx="80" fill="#d1edf0" stroke="#68a4aa" stroke-width="5"/><g font-family="sans-serif" font-size="21" text-anchor="middle" fill="#30443f"><text x="320" y="250">SWIMMING POOL</text><text x="750" y="240">FITNESS CENTER</text><text x="1015" y="240">LUNA SPA</text><text x="600" y="560">SKY LOUNGE</text><text x="1030" y="560">ELEVATORS</text></g>
<path d="M1030 510 L1030 440 L600 440 L600 400 L320 400 L320 340" fill="none" stroke="#987346" stroke-width="9" stroke-dasharray="16 12"/><text x="60" y="740" font-family="sans-serif" font-size="18" fill="#52655f">Illustrative layout only · all property locations are fictional</text></svg>'''


def _basement_map() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800" role="img" aria-labelledby="title desc">
<title id="title">Hotel De Luna fictional basement map</title><desc id="desc">Illustrative demo plan with a parking area and elevator lobby.</desc>
<rect width="1200" height="800" fill="#eff0f2"/><text x="60" y="48" font-family="sans-serif" font-size="28" font-weight="700" fill="#39404a">HOTEL DE LUNA · BASEMENT 1 (DEMO)</text>
<g fill="#fff" stroke="#777f8a" stroke-width="4"><rect x="70" y="120" width="700" height="420" rx="22"/><rect x="830" y="120" width="280" height="420" rx="22"/></g>
<g font-family="sans-serif" font-size="22" text-anchor="middle" fill="#39404a"><text x="420" y="310">DEMO PARKING AREA</text><text x="970" y="310">ELEVATOR LOBBY</text><text x="420" y="365">Access from fictional Luna Street</text></g>
<path d="M760 360 L850 360" fill="none" stroke="#987346" stroke-width="9" stroke-dasharray="16 12"/><text x="60" y="740" font-family="sans-serif" font-size="18" fill="#606a75">Illustrative layout only · capacity and parking availability are not configured</text></svg>'''


def seed_facilities(api: DemoAPI, floors: dict[str, str], zones: dict[str, str]) -> None:
    base = f"/api/admin/properties/{PROPERTY_ID}"
    existing = api.call("GET", f"{base}/hospitality").get("facilities", [])
    existing_by_name = {item.get("name"): item.get("facility_id") for item in existing}
    for item in FACILITIES:
        floor_id = floors[item["floor"]]
        zone_id = zones[item["zone"]]
        facility_id = existing_by_name.get(item["name"], "demo-" + item["name"].casefold().replace(" ", "-"))
        api.call("PUT", f"{base}/hospitality/facilities", payload({
            "facility_id": facility_id,
            "name": item["name"], "facility_type": item["facility_type"],
            "location": item["location"], "floor_id": floor_id, "zone_id": zone_id,
            "building_id": None,
            "opening_hours": {"display": item["hours"]},
            "description": item["description"], "policies": item["policies"],
            "live_status": "open", "status_note": "DEMO STATUS; no live property service is connected.",
            "booking_supported": False, "images": [],
        }))


def seed_dining(api: DemoAPI) -> dict[str, str]:
    base = f"/api/admin/properties/{PROPERTY_ID}"
    current = api.call("GET", f"{base}/restaurants").get("restaurants", [])
    by_name = {item.get("name"): item for item in current}
    hospitality = api.call("GET", f"{base}/hospitality")
    facility_ids = {item.get("name"): item.get("facility_id") for item in hospitality.get("facilities", [])}
    ids: dict[str, str] = {}
    for item in RESTAURANTS:
        restaurant = by_name.get(item["name"])
        if not restaurant:
            restaurant = api.call("POST", f"{base}/restaurants", payload({
                key: value for key, value in item.items() if key != "items"
            } | {"images": [PLACEHOLDER_IMAGE], "status": "open", "facility_id": facility_ids.get(item["name"])}))
        else:
            restaurant = api.call("PUT", f"{base}/restaurants/{quote(restaurant['restaurant_id'], safe='')}", payload({
                key: value for key, value in item.items() if key != "items"
            } | {"images": [PLACEHOLDER_IMAGE], "status": "open", "facility_id": facility_ids.get(item["name"])}))
        restaurant_id = restaurant["restaurant_id"]
        ids[item["name"]] = restaurant_id
        menus = api.call("GET", f"{base}/restaurants/{quote(restaurant_id, safe='')}/menus").get("menus", [])
        menu = next((candidate for candidate in menus if candidate.get("name") == "Hotel De Luna sample menu (DEMO)"), None)
        if not menu:
            menu = api.call("POST", f"{base}/restaurants/{quote(restaurant_id, safe='')}/menus", payload({
                "name": "Hotel De Luna sample menu (DEMO)", "meal_period": "all_day", "active": True,
            }))
            menu = {**menu, "items": []}
        existing_items = {str(value.get("name", "")).casefold() for value in menu.get("items", [])}
        for name, description, price, dietary, allergens in item["items"]:
            if name.casefold() not in existing_items:
                api.call("POST", f"{base}/menus/{quote(menu['menu_id'], safe='')}/items", payload({
                    "name": name, "description": description, "price": price,
                    "image_url": PLACEHOLDER_IMAGE,
                    "ingredients": [], "allergens": allergens, "dietary_tags": dietary,
                    "available": True,
                }))
        if menu.get("workflow_status") != "published":
            api.call("POST", f"{base}/menus/{quote(menu['menu_id'], safe='')}/approve", {})
            api.call("POST", f"{base}/menus/{quote(menu['menu_id'], safe='')}/publish", {})
    return ids


def seed_services(api: DemoAPI) -> None:
    base = f"/api/admin/properties/{PROPERTY_ID}"
    catalog = api.call("GET", f"{base}/service-catalog")
    departments = {item.get("name"): item for item in catalog.get("departments", [])}
    required_departments = sorted({item[1] for item in SERVICES})
    for name in required_departments:
        if name not in departments:
            department = api.call("PUT", f"{base}/departments", payload({
                "name": name, "default_sla_minutes": 30, "enabled": True,
                "operating_hours": {"display": "Daily, 06:00–23:00 (demo hours)"},
            }))
            departments[name] = department

    by_service = {item.get("name"): item for item in catalog.get("services", [])}
    for name, department_name, keywords, description, sla in SERVICES:
        prior = by_service.get(name)
        api.call("PUT", f"{base}/service-catalog", payload({
            "service_id": prior.get("service_id") if prior else "demo-" + name.casefold().replace(" ", "-"),
            "name": name, "department_id": departments[department_name]["department_id"],
            "description": description, "keywords": keywords, "sla_minutes": sla,
            "confirmation_required": True, "enabled": True, "archived": False,
            "sort_order": SERVICES.index((name, department_name, keywords, description, sla)),
        }))


def seed_recommendations(api: DemoAPI) -> None:
    base = f"/api/admin/properties/{PROPERTY_ID}/recommendations"
    current = api.call("GET", base).get("recommendations", [])
    by_name = {item.get("name"): item for item in current}
    for name, category, address, description in ATTRACTIONS:
        prior = by_name.get(name)
        data = {
            "recommendation_id": prior.get("recommendation_id") if prior else "demo-" + name.casefold().replace(" ", "-"),
            "name": name, "category": category, "address": address,
            "description": description,
            "source": "Real public Manila attraction; sample copy for a fictional hotel demo.",
            "images": [], "opening_hours": {}, "map_url": "", "enabled": True,
        }
        api.call("PUT", base, payload(data))


def seed_staff(api: DemoAPI, restaurant_ids: dict[str, str]) -> list[str]:
    roles = api.call("GET", "/api/admin/roles").get("roles", [])
    users = api.call("GET", "/api/admin/users").get("users", [])
    created: list[str] = []
    tasks = [
        ("department-manager", "demo-housekeeping", "Demo Housekeeping Lead", "Housekeeping", []),
        ("restaurant-manager", "demo-sora-manager", "Demo Sora Manager", None, [restaurant_ids["Sora Japanese Restaurant"]]),
    ]
    for slug, username, display, department_name, restaurant_assignments in tasks:
        role = next((item for item in roles if item.get("slug") == slug), None)
        if not role or any(item.get("username") == username for item in users):
            continue
        department_id = None
        if department_name:
            catalog = api.call("GET", f"/api/admin/properties/{PROPERTY_ID}/service-catalog")
            department = next((item for item in catalog.get("departments", []) if item.get("name") == department_name), None)
            department_id = department.get("department_id") if department else None
        data = {
            "username": username, "display_name": display,
            "password": local_credentials()["housekeeping" if username == "demo-housekeeping" else "restaurant_manager"]["password"], "property_id": PROPERTY_ID,
            "department_id": department_id, "role_id": role["role_id"],
            "status": "active", "force_password_change": False,
            "restaurant_ids": restaurant_assignments,
        }
        api.call("POST", "/api/admin/users", data)
        created.append(username)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8082")
    args = parser.parse_args()
    if (
        os.environ.get("DEMO_MODE") != "true"
        or
        os.environ.get("CONCIERGE_LOCAL_DEMO") != "1"
        or os.environ.get("APP_ENVIRONMENT") != "development"
        or os.environ.get("CONCIERGE_DEPLOYMENT_MODE") != "source"
    ):
        print("Refusing to seed: start this script through scripts/local-demo.sh.", file=sys.stderr)
        return 2
    expected_database = Path(__file__).resolve().parents[1] / ".local-demo" / "state" / "concierge.db"
    if Path(os.environ.get("DB_PATH", "")).expanduser().resolve() != expected_database.resolve() or os.environ.get("DATABASE_URL", "").strip():
        print("Refusing to seed: the configured database is not the isolated local demo SQLite database.", file=sys.stderr)
        return 2
    if not _is_loopback_demo_url(args.base_url):
        print("Refusing to send demo data outside the loopback local demo.", file=sys.stderr)
        return 2

    api = DemoAPI(args.base_url)
    try:
        api.login()
        upsert_property(api)
        floors, zones = ensure_map(api)
        seed_facilities(api, floors, zones)
        restaurants = seed_dining(api)
        seed_services(api)
        seed_recommendations(api)
        staff = seed_staff(api, restaurants)
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"Local demo seed failed: {exc}", file=sys.stderr)
        return 1

    print(f"Seeded fictional property: Hotel De Luna ({PROPERTY_ID})")
    print(f"Dining outlets: {len(RESTAURANTS)}; hotel facilities: {len(FACILITIES)}; guest services: {len(SERVICES)}")
    print("Map data: Ground Floor and 12th Floor plans, locations, and published navigation edges")
    print(f"Nearby recommendations: {len(ATTRACTIONS)} real public Manila attractions (hours and travel data omitted)")
    print("Guest UI and Admin APIs use the application's property-scoped models and authorization.")
    print(f"Staff accounts created where supported by built-in roles: {', '.join(staff) if staff else 'no optional staff roles found'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
