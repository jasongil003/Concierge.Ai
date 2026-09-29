import base64
from io import BytesIO
import json
import math
import re
import sqlite3
import time
import uuid
import warnings
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from PIL import Image

from .database import connect_database, table_columns

from .config import settings

UPLOAD_ROOT = settings.upload_root
FLOOR_PLAN_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/pdf": ".pdf",
}
ANIMATION_TYPES = {
    "video/webm": ".webm",
    "video/mp4": ".mp4",
}

MAX_FLOOR_MAP_BYTES = 8 * 1024 * 1024
MAX_FLOOR_MAP_PIXELS = 30_000_000
_SVG_ACTIVE_ELEMENTS = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video"}
_SVG_EXTERNAL_URL = re.compile(r"url\(\s*(['\"]?)(?!#)[^)]+\)", re.IGNORECASE)


def _validate_floor_map(content_type: str, raw: bytes) -> None:
    """Validate the uploaded format and reject active/external SVG behavior."""
    if content_type == "image/png":
        expected_format = "PNG"
    elif content_type == "image/jpeg":
        expected_format = "JPEG"
    elif content_type == "application/pdf":
        if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
            raise ValueError("The uploaded file is not a valid PDF floor plan.")
        return
    elif content_type == "image/svg+xml":
        try:
            svg_text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("SVG floor plans must use UTF-8 encoding.") from exc
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", svg_text, re.IGNORECASE) or "<?xml-stylesheet" in svg_text.casefold():
            raise ValueError("SVG floor plans cannot contain document declarations or external stylesheets.")
        try:
            root = ET.fromstring(svg_text)
        except (ET.ParseError, DefusedXmlException) as exc:
            raise ValueError("The uploaded file is not a valid SVG floor plan.") from exc
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError("The uploaded file is not a valid SVG floor plan.")
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1].casefold() if isinstance(element.tag, str) else ""
            if tag in _SVG_ACTIVE_ELEMENTS:
                raise ValueError("SVG floor plans cannot contain active content.")
            if tag == "style" and "@import" in (element.text or "").casefold():
                raise ValueError("SVG floor plans cannot load external stylesheets.")
            for name, value in element.attrib.items():
                attribute = name.rsplit("}", 1)[-1].casefold()
                if attribute.startswith("on"):
                    raise ValueError("SVG floor plans cannot contain event handlers.")
                if attribute in {"href", "src"} and not value.strip().startswith("#"):
                    raise ValueError("SVG floor plans cannot reference external resources.")
                if _SVG_EXTERNAL_URL.search(value):
                    raise ValueError("SVG floor plans cannot reference external resources.")
            if element.text and _SVG_EXTERNAL_URL.search(element.text):
                raise ValueError("SVG floor plans cannot reference external resources.")
        return
    else:
        raise ValueError("Unsupported floor plan file type.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(raw))
            if image.format != expected_format:
                raise ValueError("The uploaded file content does not match its declared type.")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_FLOOR_MAP_PIXELS:
                raise ValueError("Floor plan images must not exceed 30 million pixels.")
            image.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Floor plan image dimensions are too large.") from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError("The uploaded file is not a valid floor plan image.") from exc


def _now() -> int:
    return int(time.time())


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


def _load(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    return json.loads(value)


def _safe_text(value: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _record_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class ZoneStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS buildings (
                    building_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS floors (
                    floor_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    building_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS floor_maps (
                    map_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    floor_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    width REAL,
                    height REAL,
                    created_at INTEGER NOT NULL,
                    created_at_us BIGINT NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS zones (
                    zone_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    floor_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'common',
                    geometry TEXT NOT NULL,
                    guest_visible INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS facilities (
                    facility_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    facility_type TEXT NOT NULL DEFAULT 'amenity',
                    description TEXT NOT NULL DEFAULT '',
                    guest_visible INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_points (
                    access_point_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    x REAL,
                    y REAL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS navigation_nodes (
                    node_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    floor_id TEXT NOT NULL,
                    zone_id TEXT,
                    label TEXT NOT NULL,
                    x REAL NOT NULL DEFAULT 0,
                    y REAL NOT NULL DEFAULT 0,
                    node_type TEXT NOT NULL DEFAULT 'waypoint',
                    guest_visible INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS navigation_edges (
                    edge_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    from_node_id TEXT NOT NULL,
                    to_node_id TEXT NOT NULL,
                    distance REAL NOT NULL DEFAULT 1,
                    bidirectional INTEGER NOT NULL DEFAULT 1,
                    guest_visible INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            map_columns = table_columns(db, "floor_maps")
            if "created_at_us" not in map_columns:
                db.execute("ALTER TABLE floor_maps ADD COLUMN created_at_us BIGINT NOT NULL DEFAULT 0")
            # Legacy maps only have second-resolution created_at. Preserve that
            # time at microsecond scale; new uploads carry their actual upload
            # time so maps uploaded in the same second sort correctly.
            db.execute(
                "UPDATE floor_maps SET created_at_us=CAST(created_at AS BIGINT)*1000000 "
                "WHERE created_at_us=0 AND created_at>0"
            )

    def create_building(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        record = {
            "building_id": _record_id("bldg"),
            "property_id": property_id,
            "name": _safe_text(payload.get("name"), 120),
            "description": _safe_text(payload.get("description"), 500),
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Building name is required.")
        with self._connect() as db:
            db.execute(
                "INSERT INTO buildings VALUES (:building_id,:property_id,:name,:description,:created_at,:updated_at)",
                record,
            )
        return record

    def create_floor(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        building_id = str(payload.get("building_id") or "")
        self._require_owned("buildings", "building_id", building_id, property_id)
        now = _now()
        record = {
            "floor_id": _record_id("floor"),
            "property_id": property_id,
            "building_id": building_id,
            "name": _safe_text(payload.get("name"), 120),
            "level": int(payload.get("level") or 0),
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Floor name is required.")
        with self._connect() as db:
            db.execute("INSERT INTO floors VALUES (:floor_id,:property_id,:building_id,:name,:level,:created_at,:updated_at)", record)
        return record

    def save_floor_map(self, property_id: str, floor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_owned("floors", "floor_id", floor_id, property_id)
        filename = Path(str(payload.get("filename") or "floor-plan")).name
        content_type = str(payload.get("content_type") or "")
        if content_type not in FLOOR_PLAN_TYPES:
            raise ValueError("Unsupported floor plan file type.")
        raw = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
        if not raw or len(raw) > MAX_FLOOR_MAP_BYTES:
            raise ValueError("Floor plan must be between 1 byte and 8 MB.")
        _validate_floor_map(content_type, raw)
        map_id = _record_id("map")
        created_at_us = time.time_ns() // 1_000
        directory = UPLOAD_ROOT / property_id / "floor_maps"
        directory.mkdir(parents=True, exist_ok=True)
        storage_path = directory / f"{map_id}{FLOOR_PLAN_TYPES[content_type]}"
        storage_path.write_bytes(raw)
        record = {
            "map_id": map_id,
            "property_id": property_id,
            "floor_id": floor_id,
            "original_filename": filename[:180],
            "content_type": content_type,
            "storage_path": str(storage_path),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "created_at": created_at_us // 1_000_000,
            "created_at_us": created_at_us,
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO floor_maps
                (map_id,property_id,floor_id,original_filename,content_type,storage_path,width,height,created_at,created_at_us)
                VALUES (:map_id,:property_id,:floor_id,:original_filename,:content_type,:storage_path,:width,:height,:created_at,:created_at_us)""",
                record,
            )
        return {**record, "url": f"/api/admin/properties/{property_id}/floor-maps/{map_id}/asset"}

    def upsert_zone(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        floor_id = str(payload.get("floor_id") or "")
        self._require_owned("floors", "floor_id", floor_id, property_id)
        geometry = self._validate_geometry(payload.get("geometry") or {})
        zone_id = str(payload.get("zone_id") or _record_id("zone"))
        now = _now()
        record = {
            "zone_id": zone_id,
            "property_id": property_id,
            "floor_id": floor_id,
            "name": _safe_text(payload.get("name"), 120),
            "category": _safe_text(payload.get("category") or "common", 80),
            "geometry": _json(geometry),
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Zone name is required.")
        with self._connect() as db:
            existing = db.execute("SELECT created_at FROM zones WHERE zone_id=? AND property_id=?", (zone_id, property_id)).fetchone()
            if existing:
                record["created_at"] = existing["created_at"]
                db.execute(
                    """UPDATE zones SET floor_id=:floor_id,name=:name,category=:category,geometry=:geometry,
                    guest_visible=:guest_visible,updated_at=:updated_at WHERE zone_id=:zone_id AND property_id=:property_id""",
                    record,
                )
            else:
                db.execute("INSERT INTO zones VALUES (:zone_id,:property_id,:floor_id,:name,:category,:geometry,:guest_visible,:created_at,:updated_at)", record)
        return self._public(record)

    def delete_zone(self, property_id: str, zone_id: str) -> bool:
        with self._connect() as db:
            exists = db.execute(
                "SELECT 1 FROM zones WHERE property_id=? AND zone_id=?",
                (property_id, zone_id),
            ).fetchone()
            if not exists:
                return False
            node_ids = [
                row["node_id"]
                for row in db.execute(
                    "SELECT node_id FROM navigation_nodes WHERE property_id=? AND zone_id=?",
                    (property_id, zone_id),
                )
            ]
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                db.execute(
                    # B608 rationale: only placeholder tokens are generated; node IDs are bound below.
                    f"DELETE FROM navigation_edges WHERE property_id=? AND (from_node_id IN ({placeholders}) OR to_node_id IN ({placeholders}))",  # nosec B608
                    (property_id, *node_ids, *node_ids),
                )
            db.execute("DELETE FROM navigation_nodes WHERE property_id=? AND zone_id=?", (property_id, zone_id))
            db.execute("DELETE FROM access_points WHERE property_id=? AND zone_id=?", (property_id, zone_id))
            db.execute("DELETE FROM facilities WHERE property_id=? AND zone_id=?", (property_id, zone_id))
            db.execute("DELETE FROM zones WHERE property_id=? AND zone_id=?", (property_id, zone_id))
            return True

    def update_facility(self, property_id: str, facility_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_owned("facilities", "facility_id", facility_id, property_id)
        zone_id = str(payload.get("zone_id") or "")
        self._require_owned("zones", "zone_id", zone_id, property_id)
        record = {
            "facility_id": facility_id,
            "property_id": property_id,
            "zone_id": zone_id,
            "name": _safe_text(payload.get("name"), 120),
            "facility_type": _safe_text(payload.get("facility_type") or "amenity", 80),
            "description": _safe_text(payload.get("description"), 500),
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "updated_at": _now(),
        }
        if not record["name"]:
            raise ValueError("Facility name is required.")
        with self._connect() as db:
            db.execute(
                """UPDATE facilities SET zone_id=:zone_id,name=:name,facility_type=:facility_type,
                description=:description,guest_visible=:guest_visible,updated_at=:updated_at
                WHERE facility_id=:facility_id AND property_id=:property_id""",
                record,
            )
            row = db.execute("SELECT * FROM facilities WHERE facility_id=? AND property_id=?", (facility_id, property_id)).fetchone()
        return self._public(row)

    def update_access_point(self, property_id: str, access_point_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_owned("access_points", "access_point_id", access_point_id, property_id)
        zone_id = str(payload.get("zone_id") or "")
        self._require_owned("zones", "zone_id", zone_id, property_id)
        name = _safe_text(payload.get("name"), 120)
        identifier = _safe_text(payload.get("identifier"), 160)
        if not name or not identifier:
            raise ValueError("Access point name and identifier are required.")
        x = float(payload["x"]) if payload.get("x") is not None else None
        y = float(payload["y"]) if payload.get("y") is not None else None
        with self._connect() as db:
            db.execute(
                """UPDATE access_points SET zone_id=?,name=?,identifier=?,x=?,y=?,updated_at=?
                WHERE access_point_id=? AND property_id=?""",
                (zone_id, name, identifier, x, y, _now(), access_point_id, property_id),
            )
            row = db.execute("SELECT * FROM access_points WHERE access_point_id=? AND property_id=?", (access_point_id, property_id)).fetchone()
        return dict(row)

    def update_node(self, property_id: str, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_owned("navigation_nodes", "node_id", node_id, property_id)
        floor_id = str(payload.get("floor_id") or "")
        self._require_owned("floors", "floor_id", floor_id, property_id)
        zone_id = payload.get("zone_id") or None
        if zone_id:
            self._require_owned("zones", "zone_id", str(zone_id), property_id)
            with self._connect() as db:
                zone = db.execute("SELECT floor_id FROM zones WHERE zone_id=? AND property_id=?", (zone_id, property_id)).fetchone()
            if zone["floor_id"] != floor_id:
                raise ValueError("Waypoint zone must be on the selected floor.")
        label = _safe_text(payload.get("label"), 120)
        if not label:
            raise ValueError("Navigation node label is required.")
        record = {
            "node_id": node_id,
            "property_id": property_id,
            "floor_id": floor_id,
            "zone_id": zone_id,
            "label": label,
            "x": float(payload.get("x") or 0),
            "y": float(payload.get("y") or 0),
            "node_type": _safe_text(payload.get("node_type") or "waypoint", 80),
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "updated_at": _now(),
        }
        with self._connect() as db:
            db.execute(
                """UPDATE navigation_nodes SET floor_id=:floor_id,zone_id=:zone_id,label=:label,x=:x,y=:y,
                node_type=:node_type,guest_visible=:guest_visible,updated_at=:updated_at
                WHERE node_id=:node_id AND property_id=:property_id""",
                record,
            )
            row = db.execute("SELECT * FROM navigation_nodes WHERE node_id=? AND property_id=?", (node_id, property_id)).fetchone()
        return self._public(row)

    def update_edge(self, property_id: str, edge_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            edge = db.execute("SELECT * FROM navigation_edges WHERE edge_id=? AND property_id=?", (edge_id, property_id)).fetchone()
        if edge is None:
            raise KeyError("Navigation edge not found.")
        distance = float(payload.get("distance") or 0)
        if distance <= 0:
            raise ValueError("Route distance must be greater than zero.")
        with self._connect() as db:
            db.execute(
                """UPDATE navigation_edges SET distance=?,bidirectional=?,guest_visible=?,updated_at=?
                WHERE edge_id=? AND property_id=?""",
                (distance, 1 if payload.get("bidirectional", True) else 0, 1 if payload.get("guest_visible", True) else 0, _now(), edge_id, property_id),
            )
            row = db.execute("SELECT * FROM navigation_edges WHERE edge_id=? AND property_id=?", (edge_id, property_id)).fetchone()
        return self._public(row)

    def delete_map_record(self, property_id: str, object_type: str, object_id: str) -> bool:
        records = {
            "facility": ("facilities", "facility_id"),
            "access_point": ("access_points", "access_point_id"),
            "navigation_node": ("navigation_nodes", "node_id"),
            "navigation_edge": ("navigation_edges", "edge_id"),
        }
        table_key = records.get(object_type)
        if not table_key:
            raise ValueError("Unsupported map object type.")
        table, key = table_key
        with self._connect() as db:
            # B608 rationale: table and key come from the fixed records mapping above.
            exists = db.execute(f"SELECT 1 FROM {table} WHERE {key}=? AND property_id=?", (object_id, property_id)).fetchone()  # nosec B608
            if not exists:
                return False
            if object_type == "navigation_node":
                db.execute(
                    "DELETE FROM navigation_edges WHERE property_id=? AND (from_node_id=? OR to_node_id=?)",
                    (property_id, object_id, object_id),
                )
            # B608 rationale: table and key come from the fixed records mapping above.
            db.execute(f"DELETE FROM {table} WHERE {key}=? AND property_id=?", (object_id, property_id))  # nosec B608
        return True

    def create_facility(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        zone_id = str(payload.get("zone_id") or "")
        self._require_owned("zones", "zone_id", zone_id, property_id)
        now = _now()
        record = {
            "facility_id": _record_id("fac"),
            "property_id": property_id,
            "zone_id": zone_id,
            "name": _safe_text(payload.get("name"), 120),
            "facility_type": _safe_text(payload.get("facility_type") or "amenity", 80),
            "description": _safe_text(payload.get("description"), 500),
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"]:
            raise ValueError("Facility name is required.")
        with self._connect() as db:
            db.execute("INSERT INTO facilities VALUES (:facility_id,:property_id,:zone_id,:name,:facility_type,:description,:guest_visible,:created_at,:updated_at)", record)
        return self._public(record)

    def create_access_point(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        zone_id = str(payload.get("zone_id") or "")
        self._require_owned("zones", "zone_id", zone_id, property_id)
        now = _now()
        record = {
            "access_point_id": _record_id("ap"),
            "property_id": property_id,
            "zone_id": zone_id,
            "name": _safe_text(payload.get("name"), 120),
            "identifier": _safe_text(payload.get("identifier"), 160),
            "x": payload.get("x"),
            "y": payload.get("y"),
            "created_at": now,
            "updated_at": now,
        }
        if not record["name"] or not record["identifier"]:
            raise ValueError("Access point name and identifier are required.")
        with self._connect() as db:
            db.execute("INSERT INTO access_points VALUES (:access_point_id,:property_id,:zone_id,:name,:identifier,:x,:y,:created_at,:updated_at)", record)
        return record

    def create_node(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        floor_id = str(payload.get("floor_id") or "")
        self._require_owned("floors", "floor_id", floor_id, property_id)
        zone_id = payload.get("zone_id")
        if zone_id:
            self._require_owned("zones", "zone_id", str(zone_id), property_id)
        now = _now()
        record = {
            "node_id": _record_id("node"),
            "property_id": property_id,
            "floor_id": floor_id,
            "zone_id": zone_id,
            "label": _safe_text(payload.get("label"), 120),
            "x": float(payload.get("x") or 0),
            "y": float(payload.get("y") or 0),
            "node_type": _safe_text(payload.get("node_type") or "waypoint", 80),
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        if not record["label"]:
            raise ValueError("Navigation node label is required.")
        with self._connect() as db:
            db.execute("INSERT INTO navigation_nodes VALUES (:node_id,:property_id,:floor_id,:zone_id,:label,:x,:y,:node_type,:guest_visible,:created_at,:updated_at)", record)
        return self._public(record)

    def create_edge(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from_node_id = str(payload.get("from_node_id") or "")
        to_node_id = str(payload.get("to_node_id") or "")
        self._require_owned("navigation_nodes", "node_id", from_node_id, property_id)
        self._require_owned("navigation_nodes", "node_id", to_node_id, property_id)
        now = _now()
        record = {
            "edge_id": _record_id("edge"),
            "property_id": property_id,
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "distance": float(payload.get("distance") or 1),
            "bidirectional": 1 if payload.get("bidirectional", True) else 0,
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as db:
            db.execute("INSERT INTO navigation_edges VALUES (:edge_id,:property_id,:from_node_id,:to_node_id,:distance,:bidirectional,:guest_visible,:created_at,:updated_at)", record)
        return self._public(record)

    def overview(self, property_id: str, guest: bool = False) -> dict[str, Any]:
        with self._connect() as db:
            suffix = " AND guest_visible=1" if guest else ""
            buildings = [dict(row) for row in db.execute("SELECT * FROM buildings WHERE property_id=? ORDER BY name", (property_id,))]
            floors = [dict(row) for row in db.execute("SELECT * FROM floors WHERE property_id=? ORDER BY building_id, level", (property_id,))]
            maps = [self._map_row(row) for row in db.execute("SELECT * FROM floor_maps WHERE property_id=? ORDER BY created_at_us DESC,map_id ASC", (property_id,))]
            # B608 rationale: suffix is a fixed visibility predicate selected only by the guest flag.
            zones = [self._public(row) for row in db.execute(f"SELECT * FROM zones WHERE property_id=?{suffix} ORDER BY name", (property_id,))]  # nosec B608
            # B608 rationale: suffix is a fixed visibility predicate selected only by the guest flag.
            facilities = [self._public(row) for row in db.execute(f"SELECT * FROM facilities WHERE property_id=?{suffix} ORDER BY name", (property_id,))]  # nosec B608
            # B608 rationale: suffix is a fixed visibility predicate selected only by the guest flag.
            nodes = [self._public(row) for row in db.execute(f"SELECT * FROM navigation_nodes WHERE property_id=?{suffix} ORDER BY label", (property_id,))]  # nosec B608
            # B608 rationale: suffix is a fixed visibility predicate selected only by the guest flag.
            edges = [self._public(row) for row in db.execute(f"SELECT * FROM navigation_edges WHERE property_id=?{suffix}", (property_id,))]  # nosec B608
            aps = [] if guest else [dict(row) for row in db.execute("SELECT * FROM access_points WHERE property_id=? ORDER BY name", (property_id,))]
        return {"buildings": buildings, "floors": floors, "maps": maps, "zones": zones, "facilities": facilities, "access_points": aps, "navigation_nodes": nodes, "navigation_edges": edges}

    def route(self, property_id: str, from_node_id: str, to_node_id: str, guest: bool = True) -> dict[str, Any]:
        graph: dict[str, list[tuple[str, float]]] = {}
        labels: dict[str, str] = {}
        visibility = " AND guest_visible=1" if guest else ""
        with self._connect() as db:
            # B608 rationale: visibility is a fixed guest predicate controlled by a boolean.
            for row in db.execute(f"SELECT node_id,label FROM navigation_nodes WHERE property_id=?{visibility}", (property_id,)):  # nosec B608
                labels[row["node_id"]] = row["label"]
                graph[row["node_id"]] = []
            # B608 rationale: visibility is a fixed guest predicate controlled by a boolean.
            for row in db.execute(f"SELECT * FROM navigation_edges WHERE property_id=?{visibility}", (property_id,)):  # nosec B608
                if row["from_node_id"] in graph and row["to_node_id"] in graph:
                    graph[row["from_node_id"]].append((row["to_node_id"], float(row["distance"])))
                    if row["bidirectional"]:
                        graph[row["to_node_id"]].append((row["from_node_id"], float(row["distance"])))
        if from_node_id not in graph or to_node_id not in graph:
            raise ValueError("Route endpoints are not available.")
        distances = {from_node_id: 0.0}
        previous: dict[str, str] = {}
        queue = [(0.0, from_node_id)]
        while queue:
            queue.sort(reverse=True)
            distance, node = queue.pop()
            if node == to_node_id:
                break
            for neighbor, weight in graph[node]:
                candidate = distance + weight
                if candidate < distances.get(neighbor, math.inf):
                    distances[neighbor] = candidate
                    previous[neighbor] = node
                    queue.append((candidate, neighbor))
        if to_node_id not in distances:
            raise ValueError("No route exists between these nodes.")
        path = [to_node_id]
        while path[-1] != from_node_id:
            path.append(previous[path[-1]])
        path.reverse()
        return {"node_ids": path, "labels": [labels[item] for item in path], "distance": distances[to_node_id]}

    def floor_map_path(self, property_id: str, map_id: str) -> Path:
        with self._connect() as db:
            row = db.execute("SELECT storage_path FROM floor_maps WHERE property_id=? AND map_id=?", (property_id, map_id)).fetchone()
        if not row:
            raise KeyError("Floor map not found.")
        path = Path(row["storage_path"])
        if UPLOAD_ROOT.resolve() not in path.resolve().parents:
            raise ValueError("Invalid stored path.")
        return path

    def zone_for_ap(self, property_id: str, access_point_identifier: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT z.* FROM access_points ap JOIN zones z ON z.zone_id=ap.zone_id
                WHERE ap.property_id=? AND ap.identifier=?""",
                (property_id, access_point_identifier),
            ).fetchone()
        return self._public(row) if row else None

    def _require_owned(self, table: str, key: str, value: str, property_id: str) -> None:
        allowed_keys = {
            "buildings": {"building_id"},
            "floors": {"floor_id"},
            "zones": {"zone_id"},
            "facilities": {"facility_id"},
            "access_points": {"access_point_id"},
            "navigation_nodes": {"node_id"},
        }
        if key not in allowed_keys.get(table, set()):
            raise ValueError("Unsupported ownership lookup.")
        with self._connect() as db:
            # B608 rationale: table and key are checked against the fixed allowed_keys mapping above.
            row = db.execute(f"SELECT 1 FROM {table} WHERE {key}=? AND property_id=?", (value, property_id)).fetchone()  # nosec B608
        if row is None:
            raise KeyError(f"{table[:-1].replace('_', ' ').title()} not found.")

    def _validate_geometry(self, geometry: dict[str, Any]) -> dict[str, Any]:
        shape = geometry.get("type")
        if shape not in {"rectangle", "polygon", "ellipse", "point", "path", "label"}:
            raise ValueError("Unsupported geometry type.")
        points = geometry.get("points", [])
        if shape == "polygon" and len(points) < 3:
            raise ValueError("Polygon zones need at least three points.")
        return geometry

    def _map_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["url"] = f"/api/admin/properties/{data['property_id']}/floor-maps/{data['map_id']}/asset"
        return data

    def _public(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        data = dict(row)
        for key in ("geometry",):
            if key in data:
                data[key] = _load(data[key])
        for key in ("guest_visible", "bidirectional"):
            if key in data:
                data[key] = bool(data[key])
        return data
