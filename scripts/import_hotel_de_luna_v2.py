#!/usr/bin/env python3
"""Import the fictional Hotel De Luna V2 package through local Admin APIs."""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import struct
import sys
from urllib.parse import quote, urlsplit
import zipfile

from PIL import Image

from seed_local_demo import DemoAPI, PROPERTY_ID, payload


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / ".local-demo"
PACKAGE_COPY = DEMO_DIR / "hotel_de_luna_v2.zip"
MAX_ARCHIVE_BYTES = 12 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
MAP_BUILDING_NAME = "Hotel De Luna V2 — Conceptual Maps (DEMO)"
LEGACY_MAP_NODE_LABELS = {
    "Parking Entrance", "Basement 1 Elevators", "Main Lobby", "Ground Floor Elevators",
    "Pool Entrance", "12th Floor Elevators", "Fitness Center", "Luna Spa", "Sky Lounge",
}


def local_credentials() -> dict:
    from local_demo_credentials import ensure_credentials

    return ensure_credentials()["accounts"]


def require_local_demo(base_url: str) -> Path:
    failures: list[str] = []
    if os.environ.get("DEMO_MODE") != "true":
        failures.append("DEMO_MODE must be exactly true")
    if os.environ.get("CONCIERGE_LOCAL_DEMO") != "1":
        failures.append("CONCIERGE_LOCAL_DEMO must be exactly 1")
    if os.environ.get("APP_ENVIRONMENT") != "development":
        failures.append("APP_ENVIRONMENT must be development")
    if os.environ.get("CONCIERGE_DEPLOYMENT_MODE") != "source":
        failures.append("CONCIERGE_DEPLOYMENT_MODE must be source")
    expected_db = (DEMO_DIR / "state" / "concierge.db").resolve()
    expected_uploads = (DEMO_DIR / "uploads").resolve()
    configured_db = Path(os.environ.get("DB_PATH", "")).expanduser().resolve()
    configured_uploads = Path(os.environ.get("UPLOAD_ROOT", "")).expanduser().resolve()
    if configured_db != expected_db:
        failures.append("DB_PATH must be .local-demo/state/concierge.db")
    if os.environ.get("DATABASE_URL", "").strip():
        failures.append("DATABASE_URL must be blank")
    if configured_uploads != expected_uploads:
        failures.append("UPLOAD_ROOT must be .local-demo/uploads")
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        failures.append("base URL must be an HTTP loopback address without a path")
    if DEMO_DIR.is_symlink() or DEMO_DIR.resolve().parent != ROOT.resolve():
        failures.append(".local-demo must be a real directory inside this checkout")
    marker = DEMO_DIR / "DEMO_STATE"
    expected_marker = f"Concierge.AI local demo state v1\nrepo={ROOT}\n"
    if not marker.is_file() or marker.is_symlink() or marker.read_text(encoding="utf-8") != expected_marker:
        failures.append("the checkout-owned .local-demo marker is missing or invalid")
    if not expected_db.is_file() or expected_db.is_symlink():
        failures.append("the dedicated local SQLite database does not exist")
    if not expected_uploads.is_dir() or expected_uploads.is_symlink():
        failures.append("the dedicated local upload directory is missing or unsafe")
    if failures:
        raise RuntimeError("Refusing import: " + "; ".join(failures))

    # Verify the local database identity without opening it for writes.
    database_uri = f"file:{expected_db.as_posix()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True, timeout=3) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "properties" not in tables or "admin_users" not in tables:
            raise RuntimeError("Refusing import: local SQLite database is not an initialized Concierge.AI database.")
        property_ids = {str(row[0]) for row in db.execute("SELECT property_id FROM properties")}
        if property_ids - {PROPERTY_ID}:
            raise RuntimeError("Refusing import: the dedicated local database contains another property's data.")
    return expected_uploads


def archive_members(archive_path: Path) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]]:
    if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("The package must be a regular ZIP file under 12 MB.")
    archive = zipfile.ZipFile(archive_path)
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in archive.infolist():
        raw_name = info.filename
        path = PurePosixPath(raw_name)
        mode = info.external_attr >> 16
        if raw_name.startswith("/") or "\\" in raw_name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts if part != ""):
            raise ValueError(f"Unsafe ZIP member path: {raw_name!r}")
        if stat.S_ISLNK(mode):
            raise ValueError(f"Symbolic links are not allowed in the package: {raw_name!r}")
        if info.is_dir():
            continue
        if raw_name in members:
            raise ValueError(f"Duplicate ZIP member: {raw_name}")
        total += info.file_size
        if info.file_size > 8 * 1024 * 1024 or total > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("The package exceeds the supported image and data size limits.")
        members[raw_name] = info
    for required in ("data/hotel_de_luna_demo_v2.json", "data/asset_manifest.json", "docs/CODEX_IMPORT.md"):
        if required not in members:
            raise ValueError(f"The package is missing {required}.")
    return archive, members


def validate_package(archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo]) -> tuple[dict, dict, dict[str, bytes]]:
    try:
        data = json.loads(archive.read("data/hotel_de_luna_demo_v2.json"))
        manifest = json.loads(archive.read("data/asset_manifest.json"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("The package JSON files are invalid.") from exc
    if not isinstance(data, dict) or data.get("schema_version") != "2.0":
        raise ValueError("Unsupported Hotel De Luna fixture schema version.")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list):
        raise ValueError("The asset manifest is invalid.")
    assets: dict[str, bytes] = {}
    manifest_paths: set[str] = set()
    for record in manifest["assets"]:
        if not isinstance(record, dict):
            raise ValueError("The asset manifest contains a malformed record.")
        asset_id, name = record.get("id"), record.get("file")
        if not isinstance(asset_id, str) or not asset_id:
            raise ValueError("Asset identifiers must be non-empty strings.")
        if not isinstance(name, str) or name not in members or not name.startswith("assets/"):
            raise ValueError(f"Invalid or missing asset path: {name!r}")
        if name in manifest_paths:
            raise ValueError(f"Asset paths must be unique in the manifest: {name}")
        manifest_paths.add(name)
        content = archive.read(name)
        suffix = PurePosixPath(name).suffix.casefold()
        if suffix == ".jpg":
            valid_signature = content.startswith(b"\xff\xd8\xff")
        elif suffix == ".png":
            valid_signature = content.startswith(b"\x89PNG\r\n\x1a\n")
        else:
            valid_signature = False
        if not valid_signature:
            raise ValueError(f"Asset content does not match a supported JPEG or PNG file: {name}")
        try:
            with Image.open(__import__("io").BytesIO(content)) as image:
                width, height = image.size
                image.verify()
        except Exception as exc:
            raise ValueError(f"Invalid image data for {name}") from exc
        if width < 1 or height < 1 or width * height > 30_000_000:
            raise ValueError(f"Image dimensions are outside supported limits: {name}")
        assets[name] = content
    if len(assets) != int(manifest.get("asset_count", -1)):
        raise ValueError("The asset count does not match the manifest.")
    referenced_paths: set[str] = set()

    def find_asset_refs(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                find_asset_refs(child)
        elif isinstance(value, list):
            for child in value:
                find_asset_refs(child)
        elif isinstance(value, str) and value.startswith("assets/"):
            referenced_paths.add(value)

    find_asset_refs(data)
    if not referenced_paths <= assets.keys():
        raise ValueError("The fixture refers to assets missing from the manifest: " + ", ".join(sorted(referenced_paths - assets.keys())))

    property_data = data.get("property") or {}
    rooms = data.get("rooms") or []
    restaurants = data.get("restaurants") or []
    services = data.get("service_catalog") or []
    if property_data.get("name") != "Hotel De Luna" or not rooms or len(restaurants) != 4 or len(services) != 12:
        raise ValueError("The fixture must contain Hotel De Luna, its room catalog, four restaurants, and twelve services.")
    item_ids: set[str] = set()
    menu_count = 0
    for restaurant in restaurants:
        if not restaurant.get("id") or not restaurant.get("name") or not restaurant.get("menu"):
            raise ValueError("A restaurant is missing its identifier, name, or menu.")
        for item in restaurant["menu"]:
            menu_count += 1
            item_id = item.get("id")
            price = item.get("price_php_demo")
            if not isinstance(item_id, str) or not item_id or item_id in item_ids:
                raise ValueError("Menu item identifiers must be unique.")
            item_ids.add(item_id)
            if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0 or price > 1_000_000:
                raise ValueError(f"Invalid demo menu price for {item.get('name')!r}.")
    if menu_count != 40:
        raise ValueError(f"Expected 40 menu items; found {menu_count}.")
    for room in rooms:
        rate = room.get("nightly_rate_php_demo")
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate <= 0 or rate > 1_000_000:
            raise ValueError(f"Invalid demo room rate for {room.get('name')!r}.")
    restaurant_ids = {str(item.get("id")) for item in restaurants}
    if len(restaurant_ids) != len(restaurants):
        raise ValueError("Restaurant identifiers must be unique.")
    floor_ids = {str(item.get("floor")) for item in data.get("floor_maps", [])}
    if len(floor_ids) != len(data.get("floor_maps", [])):
        raise ValueError("Map floor identifiers must be unique.")
    return data, manifest, assets


def stage_package(source: Path, archive: zipfile.ZipFile, target: Path) -> Path:
    if source.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".zip.tmp")
        with source.open("rb") as read_stream, temporary.open("wb") as write_stream:
            shutil.copyfileobj(read_stream, write_stream)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    return target


def local_image_url(upload_root: Path, property_id: str, contents: bytes, filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.casefold()
    digest = hashlib.sha256(contents).hexdigest()
    media_dir = upload_root / property_id / "hotel_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    if media_dir.is_symlink() or media_dir.resolve().parent != (upload_root / property_id).resolve():
        raise RuntimeError("Refusing to write hotel media outside the local upload store.")
    path = media_dir / f"{digest}{suffix}"
    if path.is_symlink():
        raise RuntimeError("Refusing to overwrite a symlink in the local hotel media store.")
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(contents)
        os.replace(temporary, path)
    elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError("A content-addressed media file did not match its name.")
    return f"/api/guest/hotel-assets/{digest}?property_id={quote(property_id, safe='')}"


def media_url(upload_root: Path, property_id: str, assets: dict[str, bytes], path: str) -> str:
    if path not in assets:
        raise ValueError(f"The fixture refers to an unvalidated image: {path}")
    return local_image_url(upload_root, property_id, assets[path], path)


def category_floor_code(value: str) -> str:
    clean = str(value or "").strip().casefold()
    if clean in {"b1", "basement 1", "basement"}:
        return "B1"
    if clean in {"g", "ground", "ground floor", "lobby"}:
        return "G"
    if clean.startswith("level "):
        clean = clean.removeprefix("level ").strip()
    if clean.endswith(" floor"):
        clean = clean.removesuffix(" floor").strip()
    return str(int(clean)) if clean.isdigit() else "G"


def floor_name(code: str) -> str:
    if code == "B1":
        return "Basement 1 · conceptual demo"
    if code == "G":
        return "Ground Floor · conceptual demo"
    return f"Level {int(code)} · conceptual demo"


def floor_level(code: str) -> int:
    return -1 if code == "B1" else 0 if code == "G" else int(code)


def import_map_structure(api: DemoAPI, property_id: str, data: dict, assets: dict[str, bytes], upload_root: Path) -> dict[str, str]:
    base = f"/api/admin/properties/{quote(property_id, safe='')}"
    overview = api.call("GET", f"{base}/zones")
    building = next((item for item in overview.get("buildings", []) if item.get("name") == MAP_BUILDING_NAME), None)
    if not building:
        building = api.call("POST", f"{base}/buildings", payload({
            "name": MAP_BUILDING_NAME,
            "description": "Synthetic conceptual floor diagrams from the Hotel De Luna V2 demo package. Routing is disabled.",
        }))
    building_id = building["building_id"]
    overview = api.call("GET", f"{base}/zones")
    floors_existing = {
        item.get("name"): item
        for item in overview.get("floors", [])
        if item.get("building_id") == building_id
    }
    floor_ids: dict[str, str] = {}
    floor_specs: dict[str, dict] = {}
    for map_record in data["floor_maps"]:
        code = str(map_record["floor"])
        floor_specs[code] = map_record
        title = floor_name(code)
        floor = floors_existing.get(title)
        if not floor:
            floor = api.call("POST", f"{base}/floors", payload({
                "building_id": building_id,
                "name": title,
                "level": floor_level(code),
            }))
        floor_ids[code] = floor["floor_id"]

    # Remove only the nine known nodes from the previous local-demo seed. Their
    # attached routes disappear with the nodes; the V2 fixture marks routing off.
    overview = api.call("GET", f"{base}/zones")
    for node in overview.get("navigation_nodes", []):
        if node.get("label") in LEGACY_MAP_NODE_LABELS:
            api.call("DELETE", f"{base}/navigation/nodes/{quote(str(node['node_id']), safe='')}")

    overview = api.call("GET", f"{base}/zones")
    existing_maps = {
        (item.get("floor_id"), item.get("original_filename")): item
        for item in overview.get("maps", [])
    }
    existing_nodes = {
        (item.get("floor_id"), item.get("label")): item
        for item in overview.get("navigation_nodes", [])
    }
    map_ids: dict[str, str] = {}
    for code, map_record in floor_specs.items():
        image_path = map_record["map_image"]
        image = assets[image_path]
        filename = f"hotel-de-luna-v2-floor-{code}-conceptual.png"
        map_row = existing_maps.get((floor_ids[code], filename))
        if not map_row:
            width, height = struct.unpack(">II", image[16:24])
            map_row = api.call("POST", f"{base}/floors/{quote(floor_ids[code], safe='')}/maps", {
                "filename": filename,
                "content_type": "image/png",
                "content_base64": base64.b64encode(image).decode("ascii"),
                "width": width,
                "height": height,
            })
        map_ids[code] = str(map_row["map_id"])
        width, height = struct.unpack(">II", image[16:24])
        for fixture_node in map_record.get("nodes", []):
            label = str(fixture_node["label"])
            x = round(float(fixture_node["x_normalized"]) * width, 2)
            y = round(float(fixture_node["y_normalized"]) * height, 2)
            node = existing_nodes.get((floor_ids[code], label))
            node_payload = {
                "floor_id": floor_ids[code],
                "label": label,
                "x": x,
                "y": y,
                "node_type": "conceptual_marker",
                "guest_visible": True,
            }
            if node:
                if any(node.get(key) != value for key, value in node_payload.items() if key != "floor_id"):
                    api.call("PUT", f"{base}/navigation/nodes/{quote(str(node['node_id']), safe='')}", payload(node_payload))
            else:
                node = api.call("POST", f"{base}/navigation/nodes", payload(node_payload))
            existing_nodes[(floor_ids[code], label)] = node
    return floor_ids


def property_policy_records(data: dict) -> list[dict[str, str]]:
    policies = data.get("policies") or {}
    result = []
    for key, value in policies.items():
        title = key.replace("_", " ").title()
        if isinstance(value, dict):
            text = "; ".join(f"{label.replace('_', ' ')}: {content}" for label, content in value.items())
        else:
            text = str(value)
        if key == "emergency":
            text = "DEMO POLICY ONLY. " + text + " Verify current emergency information before using this fictional property content."
        result.append({"title": title, "name": title, "text": text, "content": text})
    return result


def upsert_property_data(api: DemoAPI, data: dict, assets: dict[str, bytes], upload_root: Path) -> None:
    hotel = data["property"]
    property_id = PROPERTY_ID
    brand = hotel.get("branding") or {}
    image_gallery = [media_url(upload_root, property_id, assets, item) for item in hotel.get("image_gallery", [])]
    logo_url = media_url(upload_root, property_id, assets, brand["logo"])
    rooms = []
    for room in data.get("rooms", []):
        gallery = [media_url(upload_root, property_id, assets, item) for item in room.get("gallery", [])]
        amenities = [str(item) for item in room.get("amenities", [])]
        description = str(room.get("description") or "")
        if amenities:
            description += " Amenities: " + ", ".join(amenities) + "."
        rooms.append({
            "id": str(room["id"]),
            "name": str(room["name"]),
            "description": description[:1000],
            "capacity": int(room["max_guests"]),
            "status": "available",
            "size_sqm": int(room["size_sqm"]),
            "nightly_rate_php_demo": int(room["nightly_rate_php_demo"]),
            "beds": str(room.get("beds") or ""),
            "amenities": amenities,
            "images": gallery,
            "gallery": gallery,
        })
    facilities = []
    facility_by_name = {str(item.get("name") or "").casefold(): item for item in data.get("facilities", [])}
    restaurants = []
    restaurant_images: dict[str, list[str]] = {}
    for restaurant in data.get("restaurants", []):
        images = [media_url(upload_root, property_id, assets, path) for path in restaurant.get("gallery", [])]
        restaurant_images[str(restaurant["id"])] = images
        hours = restaurant.get("hours") or {}
        display = f"{hours.get('open', 'hours not provided')}–{hours.get('close', 'hours not provided')} (demo hours)"
        meal_periods = ["all_day"]
        restaurants.append({
            "id": restaurant["id"], "name": restaurant["name"], "description": restaurant.get("description", ""),
            "location": str(restaurant.get("floor") or "") + " · " + str(restaurant.get("name") or ""),
            "cuisine": restaurant.get("cuisine", ""), "meal_periods": meal_periods,
            "opening_hours": display, "hours": display, "images": images,
        })
    for facility in data.get("facilities", []):
        images = [media_url(upload_root, property_id, assets, path) for path in facility.get("images", [])]
        hours = facility.get("hours") or {}
        display = f"{hours.get('open', 'hours not provided')}–{hours.get('close', 'hours not provided')} (demo hours; days not specified)"
        facilities.append({
            "name": facility["name"], "description": facility.get("description", ""),
            "location": str(facility.get("floor") or ""), "hours": display,
            "images": images,
        })
    contact = hotel.get("contact") or {}
    policies = data.get("policies") or {}
    wifi = policies.get("wifi") or {}
    try:
        current = api.call("GET", f"/api/admin/properties/{quote(property_id, safe='')}")
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        current = {}
    guest_experience = deepcopy((current.get("app_settings") or {}).get("guest_experience") or {})
    guest_experience.update({
        "intelligent_ui": {"enabled": True},
        "welcome_message": "Welcome to Hotel De Luna. I'm your local demo concierge. What can I help with?",
        "suggested_prompts": [
            "I'm hungry.", "Show me the room types.", "Where is the Infinity Pool?",
            "What time is checkout?", "Can you send two extra pillows to my room?",
        ],
    })
    profile = {
        "property_id": property_id,
        "hotel_name": hotel["name"],
        "description": f"{hotel.get('description', '')} This is a fictional Manila, Philippines property. All room rates, services, policies, operating hours, and hotel-specific details are synthetic demo content. No street address, live booking system, POS, or operational floor plan is configured.",
        "timezone": hotel.get("timezone", "Asia/Manila"),
        "latitude": hotel.get("latitude"),
        "longitude": hotel.get("longitude"),
        "address": "Manila, Philippines (fictional; no street address provided)",
        "contact_details": {
            "phone": contact.get("phone", "DEMO — not callable"),
            "email": contact.get("email", ""),
            "check_in": policies.get("check_in", ""),
            "checkout": policies.get("check_out", ""),
            "wifi_guidance": "; ".join(f"{key.replace('_', ' ')}: {value}" for key, value in wifi.items()),
        },
        "logo_url": logo_url,
        "brand_assets": {
            "tagline": hotel.get("tagline", ""), "category": hotel.get("category", ""),
            "stars_demo": hotel.get("stars_demo"), "room_count_demo": hotel.get("room_count_demo"),
            "floor_count_demo": hotel.get("floor_count_demo"), "image_gallery": image_gallery,
            "content_status": hotel.get("content_status", "published_demo"),
            "notice": data.get("notice", "Synthetic demo property and placeholder media."),
        },
        "concierge_name": "Luna Concierge",
        "primary_color": brand.get("primary", "#123F3B"),
        "secondary_color": brand.get("secondary", "#C7A86D"),
        "background": brand.get("background", "#F7F5EE"),
        "languages": ["en"],
        "facilities": facilities,
        "dining": restaurants,
        "pool": next((item for item in facilities if "pool" in item["name"].casefold()), {}),
        "gym": next((item for item in facilities if "fitness" in item["name"].casefold()), {}),
        "spa": next((item for item in facilities if "spa" in item["name"].casefold()), {}),
        "policies": property_policy_records(data),
        "support_contacts": [],
        "quick_actions": [
            {"label": "Explore dining", "prompt": "I'm hungry."},
            {"label": "View room types", "prompt": "Show me the room types."},
            {"label": "Find the pool", "prompt": "Where is the Infinity Pool?"},
            {"label": "Request an item", "prompt": "Can you send two extra pillows to my room?"},
        ],
        "rooms": rooms,
        "app_settings": {
            "application": {"default_language": "en", "timezone": hotel.get("timezone", "Asia/Manila")},
            "guest_experience": guest_experience,
        },
    }
    api.call("PUT", f"/api/admin/properties/{quote(property_id, safe='')}", profile)


def import_restaurants_and_menus(api: DemoAPI, data: dict, assets: dict[str, bytes], upload_root: Path, facility_ids: dict[str, str]) -> dict[str, str]:
    property_id = PROPERTY_ID
    base = f"/api/admin/properties/{quote(property_id, safe='')}"
    current = api.call("GET", f"{base}/restaurants").get("restaurants", [])
    by_name = {str(item.get("name") or "").casefold(): item for item in current}
    result: dict[str, str] = {}
    menu_payloads: dict[str, list[dict]] = {}
    for restaurant in data["restaurants"]:
        image_paths = restaurant.get("gallery", [])
        images = [media_url(upload_root, property_id, assets, item) for item in image_paths]
        hours = restaurant.get("hours") or {}
        hours_display = f"{hours.get('open', '')}–{hours.get('close', '')} (demo hours; timezone {hours.get('timezone') or 'not specified'})"
        reservation = restaurant.get("reservations") or {}
        entry = {
            "name": restaurant["name"],
            "cuisine": restaurant.get("cuisine", ""),
            "location": str(restaurant.get("floor") or "") + " · " + str(restaurant.get("name") or ""),
            "phone_extension": str(restaurant.get("contact_extension_demo") or "DEMO — not callable") + " (DEMO)",
            "description": str(restaurant.get("description") or ""),
            "opening_hours": {"display": hours_display, "open": str(hours.get("open") or ""), "close": str(hours.get("close") or ""), "timezone": str(hours.get("timezone") or "")},
            "meal_periods": ["all_day"],
            "reservation_available": bool(reservation.get("supported_in_demo")),
            "contact_details": {},
            "external_reservation_url": "",
            "guest_notes": "Demo reservation requests require staff confirmation. No live booking engine or calendar is connected.",
            "internal_notes": "Hotel De Luna V2 synthetic fixture. Bundled image assets are stylized demo placeholders, not hotel photographs.",
            "images": images,
            "status": "open",
            "facility_id": facility_ids.get(str(restaurant["name"]).casefold()),
        }
        prior = by_name.get(str(restaurant["name"]).casefold())
        if prior:
            record = api.call("PUT", f"{base}/restaurants/{quote(str(prior['restaurant_id']), safe='')}", payload(entry))
        else:
            record = api.call("POST", f"{base}/restaurants", payload(entry))
        restaurant_id = str(record["restaurant_id"])
        result[str(restaurant["id"])] = restaurant_id

        menus = api.call("GET", f"{base}/restaurants/{quote(restaurant_id, safe='')}/menus").get("menus", [])
        categories: dict[str, list[dict]] = defaultdict(list)
        for item in restaurant.get("menu", []):
            categories[str(item.get("category") or "Menu")].append(item)
        menu_payloads[restaurant_id] = []
        for category, items in categories.items():
            menu_name = f"Hotel De Luna V2 — {category} (DEMO)"
            meal_period = category.casefold().replace("_", " ")
            menu = next((value for value in menus if value.get("name") == menu_name), None)
            if not menu:
                menu = api.call("POST", f"{base}/restaurants/{quote(restaurant_id, safe='')}/menus", payload({
                    "name": menu_name, "meal_period": meal_period, "active": True,
                }))
                menu["items"] = []
            elif menu.get("meal_period") != meal_period:
                menu = api.call("PUT", f"{base}/menus/{quote(str(menu['menu_id']), safe='')}", payload({"name": menu_name, "meal_period": meal_period}))
                menu["items"] = []
            menu_items = {str(value.get("name") or "").casefold(): value for value in menu.get("items", [])}
            for item in items:
                image = media_url(upload_root, property_id, assets, item["image"])
                tags = [str(item["dietary_tag"])] if item.get("dietary_tag") else []
                expected = {
                    "name": str(item["name"]),
                    "description": str(item.get("description") or ""),
                    "price": f"PHP {int(item['price_php_demo']):,} (DEMO)",
                    "image_url": image,
                    "ingredients": [], "allergens": [], "dietary_tags": tags,
                    "available": True,
                }
                old = menu_items.get(expected["name"].casefold())
                same = old and all(old.get(key) == value for key, value in expected.items())
                if same:
                    continue
                item_path = f"{base}/menus/{quote(str(menu['menu_id']), safe='')}/items" if not old else f"{base}/menu-items/{quote(str(old['item_id']), safe='')}"
                method = "POST" if not old else "PUT"
                api.call(method, item_path, payload(expected))
            menu_payloads[restaurant_id].append(str(menu["menu_id"]))

        # The old starter seed had one published sample menu per restaurant.
        # Mark only those known menus as drafts so the guest sees the imported catalog.
        for menu in menus:
            if menu.get("name") == "Hotel De Luna sample menu (DEMO)":
                api.call("PUT", f"{base}/menus/{quote(str(menu['menu_id']), safe='')}", payload({
                    "name": "Superseded local starter menu (DEMO)",
                    "meal_period": menu.get("meal_period") or "all_day",
                }))

    for restaurant_id, menu_ids in menu_payloads.items():
        for menu_id in menu_ids:
            menus = api.call("GET", f"{base}/restaurants/{quote(restaurant_id, safe='')}/menus").get("menus", [])
            menu = next((value for value in menus if str(value.get("menu_id")) == menu_id), None)
            if menu and menu.get("workflow_status") != "published":
                if menu.get("workflow_status") != "approved":
                    api.call("POST", f"{base}/menus/{quote(menu_id, safe='')}/approve", {})
                api.call("POST", f"{base}/menus/{quote(menu_id, safe='')}/publish", {})
    return result


def import_facilities(api: DemoAPI, data: dict, assets: dict[str, bytes], upload_root: Path, floor_ids: dict[str, str], building_id: str) -> dict[str, str]:
    property_id = PROPERTY_ID
    base = f"/api/admin/properties/{quote(property_id, safe='')}"
    existing = api.call("GET", f"{base}/hospitality").get("facilities", [])
    by_name = {str(item.get("name") or "").casefold(): item for item in existing}
    aliases = {"infinity pool": "swimming pool", "meeting suites": "meeting rooms"}
    result: dict[str, str] = {}
    for fixture in data.get("facilities", []):
        name = str(fixture["name"])
        prior = by_name.get(name.casefold()) or by_name.get(aliases.get(name.casefold(), ""))
        facility_id = str(prior.get("facility_id")) if prior else "hotel-de-luna-v2-" + str(fixture["id"])
        hours = fixture.get("hours") or {}
        display = f"{hours.get('open', '')}–{hours.get('close', '')} (demo hours; days not specified)"
        images = [media_url(upload_root, property_id, assets, item) for item in fixture.get("images", [])]
        floor = str(fixture.get("floor") or "")
        policy = ["Access and availability details are synthetic demo content."]
        if fixture.get("accessible_route_available"):
            policy.append("Accessible route: " + str(fixture["accessible_route_available"]) + " (demo reference).")
        record = api.call("PUT", f"{base}/hospitality/facilities", payload({
            "facility_id": facility_id,
            "name": name,
            "facility_type": str(fixture.get("id") or "amenity").replace("_", " "),
            "location": floor,
            "floor_id": floor_ids.get(category_floor_code(floor)),
            "building_id": building_id,
            "zone_id": None,
            "opening_hours": {"display": display, "open": str(hours.get("open") or ""), "close": str(hours.get("close") or "")},
            "description": fixture.get("description", ""),
            "images": images,
            "policies": policy[:8],
            "live_status": "open" if fixture.get("status") == "active" else "closed",
            "status_note": "DEMO status; no live availability system is connected.",
            "booking_supported": False,
        }))
        result[name.casefold()] = str(record["facility_id"])
        by_name[name.casefold()] = record

    # Keep restaurant location records linked to the conceptual V2 floors.
    for restaurant in data["restaurants"]:
        name = str(restaurant["name"])
        prior = by_name.get(name.casefold())
        if not prior:
            continue
        images = [media_url(upload_root, property_id, assets, item) for item in restaurant.get("gallery", [])]
        hours = restaurant.get("hours") or {}
        record = api.call("PUT", f"{base}/hospitality/facilities", payload({
            "facility_id": prior["facility_id"], "name": name, "facility_type": "restaurant",
            "location": str(restaurant.get("floor") or ""),
            "floor_id": floor_ids.get(category_floor_code(str(restaurant.get("floor") or ""))),
            "building_id": building_id, "zone_id": None,
            "opening_hours": {"display": f"{hours.get('open', '')}–{hours.get('close', '')} (demo hours)"},
            "description": restaurant.get("description", ""), "images": images,
            "policies": ["Menu prices and availability are synthetic demo content."],
            "live_status": "open", "status_note": "DEMO status; no live restaurant service is connected.",
            "booking_supported": False,
        }))
        result[name.casefold()] = str(record["facility_id"])
        by_name[name.casefold()] = record

    # The prior local fixture had one extra generic elevator facility; the V2
    # package represents elevator locations as conceptual map markers instead.
    prior_elevators = by_name.get("elevators")
    if prior_elevators and str(prior_elevators.get("facility_id", "")).startswith("demo-"):
        api.call("DELETE", f"{base}/hospitality/facilities/{quote(str(prior_elevators['facility_id']), safe='')}")
    return result


def import_services(api: DemoAPI, data: dict) -> dict[str, str]:
    property_id = PROPERTY_ID
    base = f"/api/admin/properties/{quote(property_id, safe='')}"
    catalog = api.call("GET", f"{base}/service-catalog")
    departments = {str(item.get("name") or "").casefold(): item for item in catalog.get("departments", [])}
    services_by_name = {str(item.get("name") or "").casefold(): item for item in catalog.get("services", [])}
    legacy_aliases = {"room cleaning": "housekeeping visit"}
    synonyms = {
        "extra_pillows": ["extra pillows", "pillow", "pillows"],
        "extra_towels": ["extra towels", "towel", "towels"],
        "drinking_water": ["drinking water", "water bottles", "bottled water"],
        "room_cleaning": ["room cleaning", "housekeeping", "clean my room"],
        "turndown": ["turndown", "turn down service"],
        "laundry_pickup": ["laundry pickup", "laundry", "dry cleaning"],
        "maintenance": ["maintenance", "repair", "broken", "not working"],
        "aircon_issue": ["air conditioner", "aircon", "ac not working", "cooling"],
        "wake_up_call": ["wake-up call", "wake up call", "morning call"],
        "luggage_help": ["luggage assistance", "bags", "baggage", "bell service"],
        "restaurant_booking": ["restaurant reservation", "book a restaurant", "reserve a table"],
        "spa_booking": ["spa appointment", "book a spa", "spa treatment"],
    }
    service_ids: dict[str, str] = {}
    for department_name in sorted({str(item["department"]) for item in data["service_catalog"]}):
        if department_name.casefold() not in departments:
            created = api.call("PUT", f"{base}/departments", payload({
                "name": department_name,
                "default_sla_minutes": 30,
                "enabled": True,
                "operating_hours": {"display": "Demo availability; no live department schedule is connected."},
            }))
            departments[department_name.casefold()] = created
    for index, service in enumerate(data["service_catalog"]):
        name = str(service["name"])
        prior = services_by_name.get(name.casefold()) or services_by_name.get(legacy_aliases.get(name.casefold(), ""))
        required_fields = ", ".join(str(item) for item in service.get("required_fields", []))
        description = f"{service.get('department', '')} demo service. Required details: {required_fields or 'confirm with guest'}. Requests require explicit guest confirmation; fulfillment and estimates are simulated."
        body = {
            "service_id": str(prior.get("service_id")) if prior else "hotel-de-luna-v2-" + str(service["id"]),
            "name": name,
            "department_id": departments[str(service["department"]).casefold()]["department_id"],
            "description": description,
            "keywords": synonyms.get(str(service["id"]), [name.casefold(), str(service["id"]).replace("_", " ")]),
            "sla_minutes": int(service.get("estimated_response_minutes_demo") or 30),
            "confirmation_required": bool(service.get("requires_guest_confirmation", True)),
            "enabled": True,
            "archived": False,
            "sort_order": index,
        }
        api.call("PUT", f"{base}/service-catalog", payload(body))
        services_by_name[name.casefold()] = body
        service_ids[str(service["id"])] = str(body["service_id"])
    return service_ids


def import_sample_requests(api: DemoAPI, data: dict, service_ids: dict[str, str]) -> list[str]:
    base = f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}"
    existing = api.call("GET", f"{base}/hospitality").get("service_requests", [])
    by_client_id = {
        str(item.get("client_request_id")): item
        for item in existing
        if item.get("client_request_id")
    }
    imported: list[str] = []
    for sample in data.get("sample_requests", []):
        sample_id = str(sample.get("id") or "").strip()
        service_key = str(sample.get("type") or "")
        service_id = service_ids.get(service_key)
        if not sample_id or not service_id:
            raise ValueError("A sample service request has no matching imported service.")
        client_request_id = f"hotel-de-luna-v2:{sample_id}"
        record = by_client_id.get(client_request_id)
        if not record:
            record = api.call("POST", f"{base}/service-requests", payload({
                "service_id": service_id,
                "room": str(sample.get("room") or "") or None,
                "description": (
                    f"Imported synthetic sample {sample_id}: {sample.get('type')}"
                    + (f" ×{int(sample['quantity'])}" if sample.get("quantity") else "")
                    + "."
                ),
                "priority": "normal",
                "client_request_id": client_request_id,
            }))
        desired_status = str(sample.get("status") or "new")
        if desired_status not in {"new", "assigned", "accepted", "in_progress", "delivered", "completed", "cancelled"}:
            raise ValueError(f"Unsupported sample request status for {sample_id}.")
        if record.get("status") != desired_status:
            record = api.call("PUT", f"{base}/service-requests/{quote(str(record['request_id']), safe='')}/status", {
                "status": desired_status,
            })
        by_client_id[client_request_id] = record
        imported.append(str(record["request_id"]))
    return imported


def import_recommendations(api: DemoAPI, data: dict, assets: dict[str, bytes], upload_root: Path) -> None:
    base = f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/recommendations"
    current = api.call("GET", base).get("recommendations", [])
    by_name = {str(item.get("name") or "").casefold(): item for item in current}
    for item in data.get("nearby_attractions", []):
        image = item.get("image")
        images = [media_url(upload_root, PROPERTY_ID, assets, image)] if image else []
        prior = by_name.get(str(item.get("name") or "").casefold())
        record = {
            "recommendation_id": str(prior.get("recommendation_id")) if prior else "hotel-de-luna-v2-" + str(item["id"]),
            "name": str(item["name"]),
            "category": str(item.get("category") or "Public place"),
            "address": str(item.get("address") or ""),
            "description": str(item.get("description") or "") + " This sample has no verified live hours, distance, or travel-time data.",
            "source": "Public Manila place sample; hotel recommendation and image are synthetic demo content.",
            "images": images,
            "opening_hours": {},
            "map_url": "",
            "enabled": True,
        }
        api.call("PUT", base, payload(record))


def ensure_staff_users(api: DemoAPI, restaurant_ids: dict[str, str]) -> list[str]:
    roles = api.call("GET", "/api/admin/roles").get("roles", [])
    users = api.call("GET", "/api/admin/users").get("users", [])
    departments = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/service-catalog").get("departments", [])
    department = next((item for item in departments if item.get("name", "").casefold() == "housekeeping"), None)
    credentials = local_credentials()
    staff = [
        ("department-manager", "housekeeping", "Demo Housekeeping Lead", department.get("department_id") if department else None, []),
        ("restaurant-manager", "restaurant_manager", "Demo Sora Manager", None, [restaurant_ids.get("sora_japanese", "")]),
    ]
    ensured: list[str] = []
    for role_slug, account_key, display, department_id, assigned_restaurants in staff:
        username = str(credentials[account_key]["username"])
        role = next((item for item in roles if item.get("slug") == role_slug), None)
        if not role:
            continue
        prior = next((item for item in users if item.get("username") == username), None)
        if prior:
            verifier = DemoAPI(api.base_url)
            try:
                verifier.call("POST", "/api/admin/auth/login", {
                    "username": username, "password": credentials[account_key]["password"], "remember_me": False,
                }, authenticated=False)
            except RuntimeError:
                prior_id = prior.get("id") or prior.get("user_id")
                if not prior_id:
                    raise RuntimeError(f"The existing {username} account has no API identifier.")
                api.call("POST", f"/api/admin/users/{quote(str(prior_id), safe='')}/reset-password", {
                    "password": credentials[account_key]["password"], "force_password_change": False,
                })
        else:
            api.call("POST", "/api/admin/users", {
                "username": username,
                "display_name": display,
                "password": credentials[account_key]["password"],
                "property_id": PROPERTY_ID,
                "department_id": department_id,
                "role_id": role["role_id"],
                "status": "active",
                "force_password_change": False,
                "restaurant_ids": [value for value in assigned_restaurants if value],
            })
        ensured.append(username)
    return ensured


def store_package_copy(source: Path) -> Path:
    target = PACKAGE_COPY
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return target
    temporary = target.with_suffix(".zip.tmp")
    with source.open("rb") as read_stream, temporary.open("wb") as write_stream:
        shutil.copyfileobj(read_stream, write_stream)
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True, help="Hotel_De_Luna_V2_Complete_Demo.zip")
    parser.add_argument("--base-url", default="http://127.0.0.1:8082")
    args = parser.parse_args()
    try:
        upload_root = require_local_demo(args.base_url)
        archive, members = archive_members(args.archive)
        with archive:
            data, manifest, assets = validate_package(archive, members)
            api = DemoAPI(args.base_url)
            api.login()
            ready = api.call("GET", "/health/ready", authenticated=False)
            if ready.get("status") != "ok":
                raise RuntimeError("The loopback local demo is not ready.")
            properties = api.call("GET", "/api/admin/properties").get("properties", [])
            property_ids = {str(item.get("property_id")) for item in properties}
            if property_ids - {PROPERTY_ID}:
                raise RuntimeError("Refusing import: the local Admin API returned a different property identity.")
            staged = store_package_copy(args.archive)

            # Create or update the property first so every following write uses
            # an existing, property-scoped Admin API resource.
            upsert_property_data(api, data, assets, upload_root)

            # Copy every referenced package asset into the existing isolated
            # upload store. Floor map uploads additionally use the app's normal
            # floor-map API so their media records remain in the map schema.
            uploaded = {path: local_image_url(upload_root, PROPERTY_ID, contents, path) for path, contents in assets.items() if not path.startswith("assets/maps/")}
            for path, contents in assets.items():
                if path.startswith("assets/maps/"):
                    uploaded[path] = ""

            floor_ids = import_map_structure(api, PROPERTY_ID, data, assets, upload_root)
            overview = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/zones")
            building = next(item for item in overview.get("buildings", []) if item.get("name") == MAP_BUILDING_NAME)
            facilities_by_name = import_facilities(api, data, assets, upload_root, floor_ids, str(building["building_id"]))
            restaurant_ids = import_restaurants_and_menus(api, data, assets, upload_root, facilities_by_name)
            service_ids = import_services(api, data)
            sample_request_ids = import_sample_requests(api, data, service_ids)
            import_recommendations(api, data, assets, upload_root)
            staff = ensure_staff_users(api, restaurant_ids)

            # Check through the authenticated, property-scoped APIs that the
            # expected content is visible before reporting the import complete.
            property_record = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}")
            restaurants = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/restaurants").get("restaurants", [])
            hospitality = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/hospitality")
            services = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/service-catalog").get("services", [])
            recommendations = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/recommendations").get("recommendations", [])
            zones = api.call("GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/zones")
            menu_items = sum(len(menu.get("items", [])) for restaurant in restaurants for menu in api.call(
                "GET", f"/api/admin/properties/{quote(PROPERTY_ID, safe='')}/restaurants/{quote(str(restaurant['restaurant_id']), safe='')}/menus",
            ).get("menus", []) if menu.get("workflow_status") == "published" and menu.get("name", "").startswith("Hotel De Luna V2"))
            if property_record.get("hotel_name") != "Hotel De Luna" or len(property_record.get("rooms", [])) != 6:
                raise RuntimeError("Post-import property or room catalog verification failed.")
            if len(restaurants) != 4 or menu_items != 40:
                raise RuntimeError(f"Post-import dining verification failed: {len(restaurants)} restaurants, {menu_items} published menu items.")
            facility_names = {str(item.get("name") or "").casefold() for item in hospitality.get("facilities", [])}
            expected_facility_names = {str(item.get("name") or "").casefold() for item in data.get("facilities", [])}
            if len(expected_facility_names) != 11 or not expected_facility_names <= facility_names:
                raise RuntimeError("Post-import facility verification failed.")
            service_names = {str(item.get("name") or "").casefold() for item in services}
            expected_service_names = {str(item.get("name") or "").casefold() for item in data.get("service_catalog", [])}
            recommendation_names = {str(item.get("name") or "").casefold() for item in recommendations}
            expected_recommendation_names = {str(item.get("name") or "").casefold() for item in data.get("nearby_attractions", [])}
            if not expected_service_names <= service_names or not expected_recommendation_names <= recommendation_names:
                raise RuntimeError("Post-import service or recommendation verification failed.")
            request_client_ids = {str(item.get("client_request_id")) for item in hospitality.get("service_requests", [])}
            expected_request_ids = {f"hotel-de-luna-v2:{item.get('id')}" for item in data.get("sample_requests", [])}
            if not expected_request_ids <= request_client_ids or len(sample_request_ids) != len(expected_request_ids):
                raise RuntimeError("Post-import sample service request verification failed.")
            map_names = {str(item.get("original_filename") or "") for item in zones.get("maps", [])}
            imported_maps = {name for name in map_names if name.startswith("hotel-de-luna-v2-floor-") and name.endswith("-conceptual.png")}
            if len(imported_maps) != len(data.get("floor_maps", [])):
                raise RuntimeError(f"Post-import floor map verification failed: {len(imported_maps)} V2 maps.")
            print(f"Imported Hotel De Luna V2 into local property {PROPERTY_ID}.")
            print(f"Rooms: {len(property_record['rooms'])}; restaurants: {len(restaurants)}; published menu items: {menu_items}.")
            print(f"Facilities: {len(data['facilities'])}; floor maps: {len(data['floor_maps'])}; guest services: {len(data['service_catalog'])}; attractions: {len(recommendations)}.")
            print(f"Synthetic sample requests: {len(sample_request_ids)}; guest request IDs are generated by the local backend.")
            print(f"Validated image assets: {len(assets)}; package retained at {staged.relative_to(ROOT)}.")
            print("Maps are conceptual; the imported package provides no indoor routes or live booking/POS integration.")
            print("Generated demo accounts remain in .local-demo/credentials.json (mode 0600).")
            print(f"Generated staff accounts ready: {', '.join(staff) if staff else 'built-in role templates unavailable'}.")
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile, sqlite3.Error) as exc:
        print(f"Hotel De Luna V2 import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
