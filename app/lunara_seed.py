"""Idempotent demo data mapping for Lunara Grand Hotel & Residences."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .hospitality import HospitalityStore
from .operations import OperationsStore
from .properties import PropertyStore, default_design_config, validate_design_config
from .zones import ZoneStore

PROPERTY_ID = "lunara-mnl-001"
SEED_VERSION = 1
MAP_FILENAME = "lunara-property-map.png"


ROOMS = [
    {"name": "Deluxe King", "count": 90, "floors": "4-12"},
    {"name": "Deluxe Twin", "count": 90, "floors": "4-12"},
    {"name": "Executive King", "count": 20, "floors": "13-14"},
    {"name": "Executive Twin", "count": 16, "floors": "13-14"},
    {"name": "Junior Suite", "count": 6, "floors": "15"},
    {"name": "Grand Suite", "count": 4, "floors": "15"},
    {"name": "Presidential Suite", "count": 2, "floors": "15"},
]

FACILITIES = [
    ("pool", "Infinity Pool & Pool Deck", "Level 3", "06:00-22:00", False),
    ("fitness", "Fitness Center", "Level 3", "24 hours", False),
    ("spa", "Lunara Spa", "Level 3", "10:00-22:00", True),
    ("business", "Business Center", "Level 2", "06:00-22:00", False),
    ("events", "Meeting & Event Center", "Level 2", "By arrangement", True),
    ("lounge", "Executive Lounge", "Level 16", "See current schedule", False),
    ("parking", "Guest Parking & EV Charging", "Basements 1-2", "24 hours", False),
]

DINING = [
    ("solace-kitchen", "Solace Kitchen", "Ground Floor", ["breakfast", "lunch", "dinner"], True),
    ("drift-cafe", "Drift Cafe", "Ground Floor", ["all day"], False),
    ("halo-rooftop", "Halo Rooftop Bar", "Level 16", ["evening"], True),
    ("executive-lounge", "Executive Lounge", "Level 16", ["breakfast", "evening cocktails"], False),
]

ZONE_LAYOUT = [
    (1, "Main Entrance & Porte-Cochere", "entrance", 584, 415),
    (2, "Lobby & Reception", "lobby", 585, 352),
    (3, "Solace Kitchen (map label: The Horizon)", "dining", 694, 346),
    (4, "Drift Cafe (map label: Aster Lounge & Bar)", "dining", 483, 347),
    (5, "Dining Venue (map label: Solara)", "dining", 389, 350),
    (6, "Meeting & Event Center", "events", 409, 274),
    (7, "Lunara Spa (map label: The Retreat Spa)", "wellness", 714, 274),
    (8, "Fitness Center", "wellness", 813, 274),
    (9, "Infinity Pool & Pool Deck", "recreation", 577, 147),
    (10, "Children's Pool / Kids' Area", "recreation", 820, 325),
    (11, "Garden Terrace", "outdoor", 580, 244),
    (12, "Residences Tower", "residences", 371, 175),
    (13, "Hotel Tower", "rooms", 778, 174),
    (14, "Parking", "parking", 359, 440),
    (15, "Service Entrance", "staff", 899, 356),
]

FAQS = [
    ("checkin", "What time are check-in and checkout?", "Check-in is at 3:00 PM and checkout is at 12:00 PM. Changes require availability and confirmation."),
    ("pool", "Where is the pool and when is it open?", "The Infinity Pool and pool deck are on Level 3 and open from 6:00 AM to 10:00 PM."),
    ("fitness", "Where is the gym and when is it open?", "The Fitness Center is on Level 3 and is open 24 hours for registered guests."),
    ("spa", "Where is Lunara Spa?", "Lunara Spa is on Level 3 and is open from 10:00 AM to 10:00 PM. Treatments require confirmation."),
    ("dining", "What dining venues are available?", "Solace Kitchen and Drift Cafe are on the Ground Floor. Halo Rooftop Bar and the Executive Lounge are on Level 16."),
    ("frontdesk", "Is the Front Desk open all day?", "Yes. The Front Desk is available 24 hours. Concierge is available from 6:00 AM to 11:00 PM."),
]


def _find_or_create_structure(zones: ZoneStore, property_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    overview = zones.overview(property_id)
    building = next((item for item in overview["buildings"] if item["name"] == "Lunara Property"), None)
    if building is None:
        building = zones.create_building(property_id, {"name": "Lunara Property", "description": "Hotel, residences, podium, and grounds."})
    floors_by_name = {item["name"]: item for item in overview["floors"] if item["building_id"] == building["building_id"]}
    for name, level in [("Property Map", 0), ("B2", -2), ("B1", -1), ("Ground Floor", 0), ("Level 2", 2), ("Level 3", 3), ("Levels 4-12", 4), ("Levels 13-14", 13), ("Level 15", 15), ("Level 16", 16)]:
        if name not in floors_by_name:
            floors_by_name[name] = zones.create_floor(property_id, {"building_id": building["building_id"], "name": name, "level": level})
    return building, floors_by_name


def seed_lunara_demo(
    properties: PropertyStore,
    zones: ZoneStore,
    hospitality: HospitalityStore,
    operations: OperationsStore,
    asset_path: Path,
    *,
    force: bool = False,
) -> dict[str, int]:
    record = properties.get(PROPERTY_ID)
    if record is None:
        raise KeyError(f"Seed {PROPERTY_ID} from data/lunara.json before applying the full mapping.")
    if not force and record.app_settings.get("lunara_seed_version") == SEED_VERSION:
        return {"zones": 0, "facilities": 0, "services": 0, "faqs": 0}

    record.hotel_name = "Lunara Grand Hotel & Residences"
    record.description = "A five-star urban lifestyle hotel with 228 rooms and suites in Aurora Bay District, Metro Manila."
    record.timezone = "Asia/Manila"
    record.address = "88 Meridian Drive, Aurora Bay District, Metro Manila, Philippines"
    record.contact_details = {"front_desk": "24 hours", "concierge": "06:00-23:00", "room_service": "24 hours"}
    record.concierge_name = "Luna"
    record.primary_color = "#0B2A45"
    record.secondary_color = "#F7F2E9"
    record.languages = ["en", "fil"]
    record.rooms = ROOMS
    record.facilities = [{"name": name, "location": location, "hours": hours} for _, name, location, hours, _ in FACILITIES]
    record.dining = [{"name": name, "location": location, "meal_periods": periods} for _, name, location, periods, _ in DINING]
    record.spa = {"name": "Lunara Spa", "location": "Level 3", "hours": "10:00-22:00", "booking_required": True}
    record.pool = {"name": "Infinity Pool & Pool Deck", "location": "Level 3", "hours": "06:00-22:00"}
    record.gym = {"name": "Fitness Center", "location": "Level 3", "hours": "24 hours"}
    record.policies = [
        {"name": "Check-in", "value": "15:00"}, {"name": "Checkout", "value": "12:00"},
        {"name": "Privacy", "value": "Never disclose another guest's room or stay, access credentials, CCTV details, or full payment credentials."},
    ]
    record.support_contacts = [
        {"name": "Front Desk", "hours": "24 hours"}, {"name": "Concierge", "hours": "06:00-23:00"},
        {"name": "Emergency", "hours": "Immediate escalation"},
    ]
    record.guest_modules = [{"id": item, "enabled": True} for item in ["chat", "property_map", "facilities", "dining", "service_requests"]]
    record.personality = {"tone": "warm, polished, concise", "hotel_voice": "modern Filipino hospitality"}
    record.guardrails = {
        "privacy": ["Do not reveal other guest information", "Do not expose credentials, CCTV, PINs, OTPs, or full card details"],
        "routing": {"P1": "immediate", "P2": "5-10 minutes", "P3": "10-30 minutes", "P4": "AI answer"},
        "confirmation_required": ["bookings", "service requests", "charges", "room access", "compensation"],
    }
    record.knowledge_sources = [
        {"type": "authoritative_kb", "name": "Lunara ConciergeAI KB Pack", "status": "active", "categories": 16},
        {"type": "visual_map", "name": MAP_FILENAME, "status": "active", "note": "Spatial layout only; KB facts override labels and contact details."},
    ]
    record.app_settings = {
        **record.app_settings,
        "source_property_id": "LUNARA-MNL-001",
        "lunara_seed_version": SEED_VERSION,
        "property_map_url": f"/static/assets/{MAP_FILENAME}",
        "map_conflict_policy": "Authoritative KB facts override text embedded in the supplied visual map.",
        "application": {"default_language": "en", "maintenance_enabled": False, "maintenance_message": ""},
    }
    design = default_design_config(record.hotel_name, record.concierge_name, record.welcome, record.quick_actions)
    design["theme"].update({"background": "#F7F2E9", "surface": "#FFFFFF", "textPrimary": "#0B2A45", "textSecondary": "#526273", "accent": "#0B2A45", "accentText": "#FFFFFF", "border": "#D8CCB8", "buttonColor": "#C89B52"})
    design["header"].update({"background": "#F7F2E9", "subtitle": "A brighter stay awaits"})
    design["welcome"].update({"greeting": "Welcome to Lunara.", "description": "Dining, directions, facilities, and guest services—mapped to the verified hotel knowledge base."})
    record.design_draft = validate_design_config(design)
    record.design_published = record.design_draft
    properties.upsert(record)

    building, floors = _find_or_create_structure(zones, PROPERTY_ID)
    overview = zones.overview(PROPERTY_ID)
    property_floor = floors["Property Map"]
    if asset_path.exists() and not any(item["original_filename"] == MAP_FILENAME for item in overview["maps"]):
        zones.save_floor_map(PROPERTY_ID, property_floor["floor_id"], {"filename": MAP_FILENAME, "content_type": "image/png", "content_base64": base64.b64encode(asset_path.read_bytes()).decode("ascii"), "width": 1536, "height": 1024})
    for number, name, category, x, y in ZONE_LAYOUT:
        zones.upsert_zone(PROPERTY_ID, {"zone_id": f"lunara-zone-{number:02d}", "floor_id": property_floor["floor_id"], "name": name, "category": category, "guest_visible": number != 15, "geometry": {"type": "ellipse", "x": x - 14, "y": y - 14, "width": 28, "height": 28, "sourceCanvas": {"width": 1200, "height": 720}, "mapNumber": number}})

    for facility_id, name, location, hours, booking in FACILITIES:
        hospitality.upsert_facility_profile(PROPERTY_ID, {"facility_id": f"lunara-facility-{facility_id}", "building_id": building["building_id"], "name": name, "facility_type": facility_id, "opening_hours": {"display": hours}, "description": f"{name}, {location}.", "booking_supported": booking, "live_status": "open"})
    for restaurant_id, name, location, periods, reservation in DINING:
        hospitality.create_restaurant(PROPERTY_ID, {"restaurant_id": f"lunara-restaurant-{restaurant_id}", "name": name, "location": location, "meal_periods": periods, "reservation_available": reservation, "description": f"Lunara dining venue at {location}.", "status": "open"})

    departments = [
        ("front-desk", "Front Desk", 10, "Duty Manager"), ("housekeeping", "Housekeeping", 20, "Housekeeping Supervisor"),
        ("engineering", "Engineering", 15, "Chief Engineer"), ("food-beverage", "Food & Beverage", 20, "F&B Manager"),
        ("security", "Security", 5, "Security Manager"), ("concierge", "Concierge", 15, "Guest Relations Manager"),
    ]
    for key, name, sla, escalation in departments:
        hospitality.upsert_department(PROPERTY_ID, {"department_id": f"lunara-dept-{key}", "name": name, "default_sla_minutes": sla, "escalation_target": escalation, "operating_hours": {"display": "24 hours" if key in {"front-desk", "security"} else "See department schedule"}})
    services = [
        ("extra-towels", "Extra towels", "housekeeping", 20, ["towels", "linen"]),
        ("room-cleaning", "Room cleaning", "housekeeping", 30, ["cleaning", "housekeeping"]),
        ("maintenance", "Room maintenance", "engineering", 15, ["broken", "aircon", "plumbing"]),
        ("dining-reservation", "Dining reservation", "food-beverage", 20, ["restaurant", "table", "reservation"]),
        ("spa-booking", "Spa booking", "concierge", 20, ["spa", "massage", "treatment"]),
        ("urgent-assistance", "Urgent guest assistance", "security", 5, ["urgent", "security", "danger"]),
    ]
    for order, (key, name, department, sla, keywords) in enumerate(services):
        hospitality.upsert_service(PROPERTY_ID, {"service_id": f"lunara-service-{key}", "department_id": f"lunara-dept-{department}", "name": name, "description": "Request routed using the Lunara SLA and escalation policy.", "keywords": keywords, "sla_minutes": sla, "confirmation_required": True, "sort_order": order})

    for key, question, answer in FAQS:
        operations.save_knowledge(PROPERTY_ID, {"kind": "faq", "question": question, "answer": answer, "enabled": True}, item_id=f"lunara-faq-{key}")
    operations.save_knowledge(PROPERTY_ID, {"kind": "entry", "title": "AI routing, SLA, and escalation", "body": "P1 emergencies are escalated immediately. P2 urgent requests target 5-10 minute acknowledgement. P3 normal service requests target 10-30 minutes. P4 information requests may be answered directly from verified knowledge. Bookings, charges, access, compensation, billing, and privacy matters require confirmation or human handling.", "enabled": True}, item_id="lunara-routing-policy")
    return {"zones": len(ZONE_LAYOUT), "facilities": len(FACILITIES), "services": len(services), "faqs": len(FAQS)}
