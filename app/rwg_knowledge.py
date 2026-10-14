"""Validation and import planning for the RWG Hotel Knowledge Package v2."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any
from urllib.parse import urlsplit
import zipfile


DATASET_PREFIX = "rwg-hotel-knowledge-v2"
REQUIRED_JSON_FILES = {
    "rwg_hotel_knowledge.json",
    "maps/facility_locations.json",
    "maps/map_manifest.json",
}
MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
OFFICIAL_HOSTS = {"rwgenting.com", "gentingskyworlds.com"}


@dataclass(frozen=True)
class RWGPackage:
    hotel_knowledge: dict[str, Any]
    facility_locations: dict[str, Any]
    map_manifest: dict[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.hotel_knowledge["dataset_id"])


def _official_https_url(value: Any, *, image: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 2000:
        raise ValueError("Package URLs must be non-empty text no longer than 2,000 characters.")
    if any(ord(char) < 32 or char == "\\" for char in value):
        raise ValueError("Package URLs cannot contain control characters or backslashes.")
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Package URL contains an invalid port.") from exc
    host = (parts.hostname or "").casefold().rstrip(".")
    if (
        parts.scheme != "https" or not host or parts.username or parts.password
        or (port is not None and port != 443)
        or not any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_HOSTS)
    ):
        label = "Image" if image else "Official source"
        raise ValueError(f"{label} URLs must use HTTPS on an official Resorts World Genting domain.")
    return value


def _read_json(archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], name: str) -> dict[str, Any]:
    info = members[name]
    if info.file_size > MAX_JSON_BYTES:
        raise ValueError(f"Package file {name} exceeds the JSON size limit.")
    try:
        value = json.loads(archive.read(info).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Package file {name} is not valid UTF-8 JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Package file {name} must contain a JSON object.")
    return value


def load_rwg_package(path: str | Path) -> RWGPackage:
    """Read the three source JSON files without extracting or executing archive content."""
    package_path = Path(path)
    if package_path.is_symlink() or not package_path.is_file() or package_path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("The RWG package must be a regular ZIP file under 10 MB.")
    try:
        archive = zipfile.ZipFile(package_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("The RWG package is not a readable ZIP archive.") from exc
    with archive:
        members: dict[str, zipfile.ZipInfo] = {}
        total_uncompressed = 0
        for info in archive.infolist():
            name = info.filename
            member_path = PurePosixPath(name)
            mode = info.external_attr >> 16
            if (
                name.startswith("/") or "\\" in name or member_path.is_absolute()
                or any(part in {".", ".."} for part in member_path.parts)
                or stat.S_ISLNK(mode)
            ):
                raise ValueError(f"Unsafe package path: {name!r}")
            if info.is_dir():
                continue
            if name in members:
                raise ValueError(f"Duplicate package path: {name}")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_PACKAGE_BYTES:
                raise ValueError("The RWG package exceeds the uncompressed size limit.")
            members[name] = info
        missing = REQUIRED_JSON_FILES - members.keys()
        if missing:
            raise ValueError("The RWG package is missing required JSON files: " + ", ".join(sorted(missing)))

        package = RWGPackage(
            hotel_knowledge=_read_json(archive, members, "rwg_hotel_knowledge.json"),
            facility_locations=_read_json(archive, members, "maps/facility_locations.json"),
            map_manifest=_read_json(archive, members, "maps/map_manifest.json"),
        )
    validate_rwg_package(package)
    return package


def _unique_records(value: Any, field: str, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a list of objects.")
    seen: set[str] = set()
    for item in value:
        record_id = str(item.get(field) or "").strip()
        if not record_id or record_id in seen:
            raise ValueError(f"{label} must contain unique, non-empty {field} values.")
        seen.add(record_id)
    return value


def validate_rwg_package(package: RWGPackage) -> None:
    primary = package.hotel_knowledge
    locations = package.facility_locations
    manifest = package.map_manifest
    if primary.get("schema_version") != "1.0.0" or not isinstance(primary.get("dataset_id"), str) or not primary["dataset_id"].strip():
        raise ValueError("Unsupported RWG hotel knowledge package schema.")
    hotel_records = _unique_records(primary.get("hotels"), "id", "Hotels")
    hotel_ids = {str(item["id"]) for item in hotel_records}
    if not hotel_ids:
        raise ValueError("The package must define at least one hotel.")
    for key in ("images", "restaurants", "facilities", "attractions", "maps", "guest_service_request_templates"):
        _unique_records(primary.get(key), "id", key)
    if not isinstance(primary.get("faq"), list) or any(
        not isinstance(item, dict) or not str(item.get("question") or "").strip() or not str(item.get("answer") or "").strip()
        for item in primary["faq"]
    ):
        raise ValueError("FAQs must contain non-empty questions and answers.")
    if not isinstance(locations.get("facilities"), list):
        raise ValueError("Facility locations must contain a facilities list.")
    _unique_records(locations["facilities"], "id", "Facility locations")
    for item in locations["facilities"]:
        _official_https_url(item.get("source_url"))
        # The package intentionally has no coordinates or route graph. Keep any
        # source values as-is; never derive them from descriptive location text.
    image_ids = {str(item["id"]) for item in primary["images"]}
    for item in primary["images"]:
        _official_https_url(item.get("url"), image=True)
        if item.get("source_page"):
            _official_https_url(item["source_page"])
    for hotel in hotel_records:
        for image_id in [hotel.get("hero_image_id"), *(hotel.get("gallery_image_ids") or [])]:
            if image_id and str(image_id) not in image_ids:
                raise ValueError(f"Hotel {hotel['id']} references an image absent from the package.")
    for key in ("restaurants", "attractions", "faq"):
        for item in primary[key]:
            for field in ("source_url", "website", "map_url"):
                if item.get(field):
                    _official_https_url(item[field])
    for item in primary["maps"]:
        if item.get("official_url"):
            _official_https_url(item["official_url"])
    manifest_maps = _unique_records(manifest.get("maps"), "id", "Map manifest")
    primary_maps = {str(item["id"]): item for item in primary["maps"]}
    if set(primary_maps) != {str(item["id"]) for item in manifest_maps}:
        raise ValueError("The primary JSON and map manifest must describe the same official maps.")
    for item in manifest_maps:
        _official_https_url(item.get("official_url"))
        if primary_maps[str(item["id"])].get("official_url") != item.get("official_url"):
            raise ValueError(f"The primary JSON and map manifest disagree for {item['id']}.")
    if not isinstance(manifest.get("directions_policy"), str):
        raise ValueError("The map manifest must state its directions policy.")


def default_property_map(package: RWGPackage) -> dict[str, str]:
    return {str(item["id"]): f"rwg-{item['id']}" for item in package.hotel_knowledge["hotels"]}


def build_import_plan(package: RWGPackage, property_map: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    hotels = {str(item["id"]): item for item in package.hotel_knowledge["hotels"]}
    if set(property_map) != set(hotels):
        missing = sorted(set(hotels) - set(property_map))
        extra = sorted(set(property_map) - set(hotels))
        details = []
        if missing:
            details.append("missing hotel mappings: " + ", ".join(missing))
        if extra:
            details.append("unknown hotel mappings: " + ", ".join(extra))
        raise ValueError("Property mapping must cover exactly the package hotels (" + "; ".join(details) + ").")
    if any(not isinstance(value, str) or not value.strip() or len(value) > 120 for value in property_map.values()):
        raise ValueError("Property IDs must be non-empty text up to 120 characters.")
    if len(set(property_map.values())) != len(property_map):
        raise ValueError("Each package hotel must map to a distinct property ID.")

    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    unmapped_images: list[dict[str, str]] = []
    primary = package.hotel_knowledge
    dataset_id = package.dataset_id

    def add(record_type: str, source_id: str, payload: dict[str, Any], targets: list[str], *, enabled: bool = True) -> None:
        for property_id in targets:
            records.append({
                "property_id": property_id,
                "dataset_id": dataset_id,
                "record_type": record_type,
                "source_record_id": source_id,
                "payload": payload,
                "enabled": enabled,
            })
            counts[f"{property_id}:{record_type}"] += 1

    all_properties = list(property_map.values())
    add("dataset_metadata", "package", {
        "schema_version": primary["schema_version"],
        "dataset_id": dataset_id,
        "mode": primary.get("mode", ""),
        "verified_as_of": primary.get("verified_as_of", ""),
        "brand": primary.get("brand", {}),
        "content_governance": primary.get("content_governance", {}),
        "maps_status": primary.get("maps_status", ""),
        "sources": primary.get("sources", []),
    }, all_properties)

    for hotel_id, hotel in hotels.items():
        add("hotel", hotel_id, hotel, [property_map[hotel_id]])

    for image in primary["images"]:
        hotel_id = str(image.get("hotel_id") or "")
        if hotel_id not in property_map:
            unmapped_images.append({"image_id": str(image.get("id") or ""), "hotel_id": hotel_id})
            continue
        safe_image = dict(image)
        # References are validated and retained, but no photo is displayed
        # while the source package says reuse permission is not established.
        safe_image["display_allowed"] = False
        safe_image["display_image_url"] = ""
        add("image", str(image["id"]), safe_image, [property_map[hotel_id]], enabled=False)

    for record_type in ("restaurant", "facility"):
        collection_name = "restaurants" if record_type == "restaurant" else "facilities"
        for item in primary[collection_name]:
            hotel_id = item.get("hotel_id")
            targets = [property_map[str(hotel_id)]] if hotel_id in property_map else all_properties
            add(record_type, str(item["id"]), item, targets)

    for item in primary["attractions"]:
        add("attraction", str(item["id"]), item, all_properties)

    for index, item in enumerate(primary["faq"]):
        hotel_id = item.get("hotel_id")
        targets = [property_map[str(hotel_id)]] if hotel_id in property_map else all_properties
        source_id = str(item.get("id") or f"faq-{index + 1}")
        add("faq", source_id, item, targets)

    for item in primary["guest_service_request_templates"]:
        # The package marks these as unverified proposals. Keep them in the
        # property knowledge store for staff review, never as active requests.
        add("service_request_template", str(item["id"]), item, all_properties, enabled=False)

    for item in package.facility_locations["facilities"]:
        add("facility_location", str(item["id"]), item, all_properties)

    for item in package.map_manifest["maps"]:
        add("map", str(item["id"]), item, all_properties)
    add("map_manifest", "manifest", {
        "version": package.map_manifest.get("version", ""),
        "copyright_note": package.map_manifest.get("copyright_note", ""),
        "directions_policy": package.map_manifest["directions_policy"],
        "map_files_in_zip": package.map_manifest.get("map_files_in_zip", 0),
        "image_files_in_zip": package.map_manifest.get("image_files_in_zip", 0),
        "image_references_in_primary_json": package.map_manifest.get("image_references_in_primary_json", 0),
    }, all_properties)

    report = {
        "dataset_id": dataset_id,
        "schema_version": primary["schema_version"],
        "properties": list(property_map.values()),
        "counts_by_property_and_type": dict(sorted(counts.items())),
        "planned_records": len(records),
        "unmapped_images": unmapped_images,
        "images_with_unconfirmed_rights": len(primary["images"]),
        "map_files_bundled": package.map_manifest.get("map_files_in_zip", 0),
        "image_files_bundled": package.map_manifest.get("image_files_in_zip", 0),
        "official_maps": len(package.map_manifest["maps"]),
        "facility_locations": len(package.facility_locations["facilities"]),
        "coordinates_present": sum(item.get("coordinates") is not None for item in package.facility_locations["facilities"]),
        "indoor_routes_present": sum(item.get("indoor_route") is not None for item in package.facility_locations["facilities"]),
    }
    return records, report


def decode_imported_reference_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse only namespaced package rows returned for a single property."""
    decoded: list[dict[str, Any]] = []
    expected_prefix = f"{DATASET_PREFIX}:"
    for row in rows:
        source_name = str(row.get("source_name") or "")
        if not source_name.startswith(expected_prefix):
            continue
        parts = source_name.split(":", 3)
        if len(parts) != 4 or not parts[1] or not parts[2] or not parts[3]:
            continue
        if row.get("kind") == "faq":
            try:
                metadata = json.loads(str(row.get("body") or "{}"))
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            payload = {
                "question": str(row.get("question") or ""),
                "answer": str(row.get("answer") or ""),
                "source_url": str(metadata.get("source_url") or "") if isinstance(metadata, dict) else "",
            }
        else:
            try:
                payload = json.loads(str(row.get("body") or "{}"))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
        decoded.append({
            "property_id": row.get("property_id"),
            "dataset_id": parts[1],
            "record_type": parts[2],
            "source_record_id": parts[3],
            "item_id": row.get("item_id"),
            "payload": payload,
        })
    return decoded
