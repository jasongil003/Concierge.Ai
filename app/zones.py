import base64
import json
import math
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings

UPLOAD_ROOT = settings.upload_root
FLOOR_PLAN_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/pdf": ".pdf",
}
ANIMATION_TYPES = {
    "application/json": ".json",
    "application/octet-stream": ".lottie",
    "video/webm": ".webm",
    "video/mp4": ".mp4",
}


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
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

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
                    created_at INTEGER NOT NULL
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
        if not raw or len(raw) > 8 * 1024 * 1024:
            raise ValueError("Floor plan must be between 1 byte and 8 MB.")
        map_id = _record_id("map")
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
            "created_at": _now(),
        }
        with self._connect() as db:
            db.execute(
                "INSERT INTO floor_maps VALUES (:map_id,:property_id,:floor_id,:original_filename,:content_type,:storage_path,:width,:height,:created_at)",
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
            row = db.execute("DELETE FROM zones WHERE property_id=? AND zone_id=?", (property_id, zone_id))
            return row.rowcount > 0

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
            maps = [self._map_row(row) for row in db.execute("SELECT * FROM floor_maps WHERE property_id=? ORDER BY created_at DESC", (property_id,))]
            zones = [self._public(row) for row in db.execute(f"SELECT * FROM zones WHERE property_id=?{suffix} ORDER BY name", (property_id,))]
            facilities = [self._public(row) for row in db.execute(f"SELECT * FROM facilities WHERE property_id=?{suffix} ORDER BY name", (property_id,))]
            nodes = [self._public(row) for row in db.execute(f"SELECT * FROM navigation_nodes WHERE property_id=?{suffix} ORDER BY label", (property_id,))]
            edges = [self._public(row) for row in db.execute(f"SELECT * FROM navigation_edges WHERE property_id=?{suffix}", (property_id,))]
            aps = [] if guest else [dict(row) for row in db.execute("SELECT * FROM access_points WHERE property_id=? ORDER BY name", (property_id,))]
        return {"buildings": buildings, "floors": floors, "maps": maps, "zones": zones, "facilities": facilities, "access_points": aps, "navigation_nodes": nodes, "navigation_edges": edges}

    def route(self, property_id: str, from_node_id: str, to_node_id: str, guest: bool = True) -> dict[str, Any]:
        graph: dict[str, list[tuple[str, float]]] = {}
        labels: dict[str, str] = {}
        visibility = " AND guest_visible=1" if guest else ""
        with self._connect() as db:
            for row in db.execute(f"SELECT node_id,label FROM navigation_nodes WHERE property_id=?{visibility}", (property_id,)):
                labels[row["node_id"]] = row["label"]
                graph[row["node_id"]] = []
            for row in db.execute(f"SELECT * FROM navigation_edges WHERE property_id=?{visibility}", (property_id,)):
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
        with self._connect() as db:
            row = db.execute(f"SELECT 1 FROM {table} WHERE {key}=? AND property_id=?", (value, property_id)).fetchone()
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
