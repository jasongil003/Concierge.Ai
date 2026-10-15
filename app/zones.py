import base64
import hashlib
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

from .database import connect_database, database_url_configured, table_columns, table_exists

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

_MAP_SNAPSHOT_TABLES = {
    "buildings": "building_id",
    "floors": "floor_id",
    "floor_maps": "map_id",
    "zones": "zone_id",
    "facilities": "facility_id",
    "access_points": "access_point_id",
    "navigation_nodes": "node_id",
    "navigation_edges": "edge_id",
}
_MAP_SNAPSHOT_DELETE_ORDER = (
    "navigation_edges",
    "navigation_nodes",
    "facilities",
    "access_points",
    "zones",
    "floor_maps",
    "floors",
    "buildings",
)
_MAP_SNAPSHOT_INSERT_ORDER = tuple(reversed(_MAP_SNAPSHOT_DELETE_ORDER))


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


def _route_distance(value: Any = 1) -> float:
    """Return a usable route weight, rejecting values Dijkstra cannot handle."""
    try:
        distance = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Route distance must be a finite number greater than zero.") from exc
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("Route distance must be a finite number greater than zero.")
    return distance


class ZoneStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connect() as db:
            revision_schema_existed = table_exists(db, "map_revisions")
        self._init_db()
        if not revision_schema_existed:
            self._publish_legacy_maps()

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
                    transition_type TEXT NOT NULL DEFAULT 'path',
                    accessible INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS map_revisions (
                    revision_id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    revision_number BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    revision_kind TEXT NOT NULL DEFAULT 'snapshot',
                    snapshot_json TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    preview_json TEXT NOT NULL DEFAULT '{}',
                    created_at BIGINT NOT NULL,
                    created_by TEXT,
                    published_at BIGINT,
                    published_by TEXT,
                    restored_from_revision_id TEXT,
                    rollback_backup_revision_id TEXT,
                    UNIQUE(property_id, revision_number)
                );
                CREATE TABLE IF NOT EXISTS map_revision_publications (
                    property_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL,
                    published_at BIGINT NOT NULL,
                    published_by TEXT
                );
                """
            )
            map_columns = table_columns(db, "floor_maps")
            if "created_at_us" not in map_columns:
                db.execute("ALTER TABLE floor_maps ADD COLUMN created_at_us BIGINT NOT NULL DEFAULT 0")
            edge_columns = table_columns(db, "navigation_edges")
            if "transition_type" not in edge_columns:
                db.execute("ALTER TABLE navigation_edges ADD COLUMN transition_type TEXT NOT NULL DEFAULT 'path'")
            if "accessible" not in edge_columns:
                db.execute("ALTER TABLE navigation_edges ADD COLUMN accessible INTEGER NOT NULL DEFAULT 0")
            db.execute(
                "CREATE INDEX IF NOT EXISTS ix_map_revisions_property_number "
                "ON map_revisions(property_id,revision_number)"
            )
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

    def create_map_revision(self, property_id: str, created_by: str | None = None) -> dict[str, Any]:
        """Capture the property's current map as an immutable draft revision."""
        if not str(property_id or "").strip():
            raise ValueError("Property ID is required for a map revision.")
        actor = self._map_revision_actor(created_by)
        with self._connect() as db:
            self._begin_map_revision_transaction(db, property_id)
            snapshot = self._capture_map_snapshot(db, property_id)
            revision = self._insert_map_revision(
                db,
                property_id,
                snapshot,
                status="draft",
                revision_kind="snapshot",
                created_by=actor,
            )
        return self._map_revision_metadata(revision)

    def preview_map_revision(self, property_id: str, revision_id: str) -> dict[str, Any]:
        """Return safe preview metadata without exposing the stored snapshot."""
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? AND revision_id=?",
                (property_id, revision_id),
            ).fetchone()
            if row is None:
                raise KeyError("Map revision not found.")
            self._read_map_revision_snapshot(row, property_id, db)
        return self._map_revision_metadata(row)

    def list_map_revisions(self, property_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List a property's revision metadata, newest first, without snapshot data."""
        try:
            bounded_limit = int(limit)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Map revision limit must be between 1 and 100.") from exc
        if not 1 <= bounded_limit <= 100:
            raise ValueError("Map revision limit must be between 1 and 100.")
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? "
                "ORDER BY revision_number DESC LIMIT ?",
                (property_id, bounded_limit),
            ).fetchall()
        return [self._map_revision_metadata(row) for row in rows]

    def current_map_revision(self, property_id: str) -> dict[str, Any] | None:
        """Return the property-scoped revision currently selected for publication."""
        with self._connect() as db:
            row = db.execute(
                """SELECT r.* FROM map_revision_publications p
                JOIN map_revisions r ON r.revision_id=p.revision_id AND r.property_id=p.property_id
                WHERE p.property_id=?""",
                (property_id,),
            ).fetchone()
        return self._map_revision_metadata(row) if row else None

    def publish_map_revision(
        self,
        property_id: str,
        revision_id: str,
        published_by: str | None = None,
        expected_current_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish an unchanged draft and move the property's published pointer."""
        actor = self._map_revision_actor(published_by)
        now = _now()
        with self._connect() as db:
            self._begin_map_revision_transaction(db, property_id)
            row = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? AND revision_id=?",
                (property_id, revision_id),
            ).fetchone()
            if row is None:
                raise KeyError("Map revision not found.")
            if row["revision_kind"] != "snapshot":
                raise ValueError("This map revision cannot be published directly.")
            current = self._current_map_revision_id(db, property_id)
            if expected_current_revision_id is not None and current != expected_current_revision_id:
                raise ValueError("Published map revision changed; reload the map revision list and retry.")
            snapshot = self._read_map_revision_snapshot(row, property_id, db)
            if row["status"] == "published" and current == revision_id:
                return self._map_revision_metadata(row)
            if row["status"] != "draft":
                raise ValueError("Only a draft map revision can be published.")
            current_snapshot = self._capture_map_snapshot(db, property_id)
            if self._map_snapshot_digest(current_snapshot) != row["snapshot_sha256"]:
                raise ValueError("Map data changed after this draft was created; create a new draft before publishing.")
            db.execute(
                """UPDATE map_revisions SET status='published',published_at=?,published_by=?
                WHERE property_id=? AND revision_id=? AND status='draft'""",
                (now, actor, property_id, revision_id),
            )
            self._set_current_map_revision(db, property_id, revision_id, now, actor)
            published = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? AND revision_id=?",
                (property_id, revision_id),
            ).fetchone()
        return self._map_revision_metadata(published)

    def restore_map_revision(
        self,
        property_id: str,
        revision_id: str,
        restored_by: str | None = None,
        expected_current_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically restore a published snapshot and append an auditable rollback revision."""
        actor = self._map_revision_actor(restored_by)
        now = _now()
        with self._connect() as db:
            self._begin_map_revision_transaction(db, property_id)
            target = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? AND revision_id=?",
                (property_id, revision_id),
            ).fetchone()
            if target is None:
                raise KeyError("Map revision not found.")
            if target["status"] != "published":
                raise ValueError("Only a published map revision can be restored.")
            current = self._current_map_revision_id(db, property_id)
            if expected_current_revision_id is not None and current != expected_current_revision_id:
                raise ValueError("Published map revision changed; reload the map revision list and retry.")
            target_snapshot = self._read_map_revision_snapshot(target, property_id, db)
            current_snapshot = self._capture_map_snapshot(db, property_id)
            backup = self._insert_map_revision(
                db,
                property_id,
                current_snapshot,
                status="draft",
                revision_kind="rollback_backup",
                created_by=actor,
            )
            self._restore_map_snapshot(db, property_id, target_snapshot)
            restored_snapshot = self._capture_map_snapshot(db, property_id)
            if self._map_snapshot_digest(restored_snapshot) != target["snapshot_sha256"]:
                raise ValueError("Restored map did not match the selected revision snapshot.")
            restored = self._insert_map_revision(
                db,
                property_id,
                restored_snapshot,
                status="published",
                revision_kind="rollback",
                created_by=actor,
                published_by=actor,
                published_at=now,
                restored_from_revision_id=revision_id,
                rollback_backup_revision_id=backup["revision_id"],
            )
            self._set_current_map_revision(db, property_id, restored["revision_id"], now, actor)
        return self._map_revision_metadata(restored)

    def map_revision_state(self, property_id: str) -> dict[str, Any]:
        """Return safe publication metadata and whether working data has changed."""
        with self._connect() as db:
            current_id = self._current_map_revision_id(db, property_id)
            current_row = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? AND revision_id=?",
                (property_id, current_id),
            ).fetchone() if current_id else None
            live_snapshot = self._capture_map_snapshot(db, property_id)
            live_digest = self._map_snapshot_digest(live_snapshot)
            revisions = db.execute(
                "SELECT * FROM map_revisions WHERE property_id=? ORDER BY revision_number DESC LIMIT 50",
                (property_id,),
            ).fetchall()
            drafts = [row for row in revisions if row["status"] == "draft" and row["revision_kind"] == "snapshot"]
        has_live_map_data = any(live_snapshot["tables"][name] for name in _MAP_SNAPSHOT_TABLES)
        has_unpublished_changes = (
            live_digest != str(current_row["snapshot_sha256"])
            if current_row else has_live_map_data
        )
        return {
            "current": self._map_revision_metadata(current_row) if current_row else None,
            "draft": self._map_revision_metadata(drafts[0]) if drafts else None,
            "revisions": [self._map_revision_metadata(row) for row in revisions],
            "has_unpublished_changes": has_unpublished_changes,
        }

    def published_map_snapshot(self, property_id: str) -> dict[str, Any] | None:
        """Return the integrity-checked currently published map snapshot."""
        with self._connect() as db:
            return self._published_map_snapshot(db, property_id)

    def _publish_legacy_maps(self) -> None:
        """Treat pre-revision SQLite map data as the existing published baseline."""
        with self._connect() as db:
            property_ids: set[str] = set()
            for table in _MAP_SNAPSHOT_TABLES:
                # Table names come only from the fixed module-level mapping.
                property_ids.update(
                    str(row["property_id"])
                    for row in db.execute(f"SELECT DISTINCT property_id FROM {table}")  # nosec B608
                    if row["property_id"]
                )
            if property_ids:
                db.execute("BEGIN IMMEDIATE")
            for property_id in sorted(property_ids):
                if self._current_map_revision_id(db, property_id):
                    continue
                snapshot = self._capture_map_snapshot(db, property_id)
                revision = self._insert_map_revision(
                    db,
                    property_id,
                    snapshot,
                    status="published",
                    revision_kind="snapshot",
                    created_by="legacy-migration",
                    published_by="legacy-migration",
                    published_at=_now(),
                )
                self._set_current_map_revision(db, property_id, revision["revision_id"], _now(), "legacy-migration")

    def _published_map_snapshot(self, db: Any, property_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """SELECT r.* FROM map_revision_publications p
               JOIN map_revisions r ON r.revision_id=p.revision_id AND r.property_id=p.property_id
               WHERE p.property_id=?""",
            (property_id,),
        ).fetchone()
        return self._read_map_revision_snapshot(row, property_id, db) if row else None

    def _begin_map_revision_transaction(self, db: Any, property_id: str) -> None:
        db.execute("BEGIN IMMEDIATE")
        if database_url_configured():
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", (property_id,))

    @staticmethod
    def _map_revision_actor(value: str | None) -> str | None:
        actor = _safe_text(value, 120) if value is not None else ""
        return actor or None

    def _capture_map_snapshot(self, db: Any, property_id: str) -> dict[str, Any]:
        tables: dict[str, list[dict[str, Any]]] = {}
        for table, primary_key in _MAP_SNAPSHOT_TABLES.items():
            # Table and key names come from the fixed module-level mapping.
            rows = db.execute(
                f"SELECT * FROM {table} WHERE property_id=? ORDER BY {primary_key}",  # nosec B608
                (property_id,),
            ).fetchall()
            tables[table] = [dict(row) for row in rows]
        snapshot = {"format": 1, "property_id": property_id, "tables": tables}
        self._validate_map_snapshot(db, property_id, snapshot)
        return snapshot

    @staticmethod
    def _map_snapshot_json(snapshot: dict[str, Any]) -> str:
        try:
            return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Map revision snapshot contains invalid data.") from exc

    def _map_snapshot_digest(self, snapshot: dict[str, Any]) -> str:
        return hashlib.sha256(self._map_snapshot_json(snapshot).encode("utf-8")).hexdigest()

    def _map_revision_preview(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        tables = snapshot["tables"]
        floor_buildings = {item["building_id"]: item["name"] for item in tables["buildings"]}
        zones_by_floor: dict[str, int] = {}
        for zone in tables["zones"]:
            zones_by_floor[zone["floor_id"]] = zones_by_floor.get(zone["floor_id"], 0) + 1
        maps_by_floor: dict[str, int] = {}
        for item in tables["floor_maps"]:
            maps_by_floor[item["floor_id"]] = maps_by_floor.get(item["floor_id"], 0) + 1
        facilities_by_zone: dict[str, int] = {}
        for item in tables["facilities"]:
            facilities_by_zone[item["zone_id"]] = facilities_by_zone.get(item["zone_id"], 0) + 1
        zones = {item["zone_id"]: item for item in tables["zones"]}
        facilities_by_floor: dict[str, int] = {}
        for item in tables["facilities"]:
            zone = zones.get(item["zone_id"])
            if zone:
                floor_id = zone["floor_id"]
                facilities_by_floor[floor_id] = facilities_by_floor.get(floor_id, 0) + 1
        counts = {name: len(tables[name]) for name in _MAP_SNAPSHOT_TABLES}
        return {
            "counts": counts,
            "floors": [
                {
                    "floor_id": floor["floor_id"],
                    "name": floor["name"],
                    "building_name": floor_buildings.get(floor["building_id"], ""),
                    "zone_count": zones_by_floor.get(floor["floor_id"], 0),
                    "facility_count": facilities_by_floor.get(floor["floor_id"], 0),
                    "floor_plan_count": maps_by_floor.get(floor["floor_id"], 0),
                }
                for floor in tables["floors"]
            ],
        }

    def _insert_map_revision(
        self,
        db: Any,
        property_id: str,
        snapshot: dict[str, Any],
        *,
        status: str,
        revision_kind: str,
        created_by: str | None,
        published_by: str | None = None,
        published_at: int | None = None,
        restored_from_revision_id: str | None = None,
        rollback_backup_revision_id: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"draft", "published"}:
            raise ValueError("Unsupported map revision status.")
        if revision_kind not in {"snapshot", "rollback", "rollback_backup"}:
            raise ValueError("Unsupported map revision kind.")
        snapshot_json = self._map_snapshot_json(snapshot)
        revision_number = int(db.execute(
            "SELECT COALESCE(MAX(revision_number),0)+1 AS next_number FROM map_revisions WHERE property_id=?",
            (property_id,),
        ).fetchone()["next_number"])
        record = {
            "revision_id": _record_id("maprev"),
            "property_id": property_id,
            "revision_number": revision_number,
            "status": status,
            "revision_kind": revision_kind,
            "snapshot_json": snapshot_json,
            "snapshot_sha256": self._map_snapshot_digest(snapshot),
            "preview_json": json.dumps(self._map_revision_preview(snapshot), sort_keys=True, separators=(",", ":")),
            "created_at": _now(),
            "created_by": created_by,
            "published_at": published_at,
            "published_by": published_by,
            "restored_from_revision_id": restored_from_revision_id,
            "rollback_backup_revision_id": rollback_backup_revision_id,
        }
        db.execute(
            """INSERT INTO map_revisions
            (revision_id,property_id,revision_number,status,revision_kind,snapshot_json,snapshot_sha256,
             preview_json,created_at,created_by,published_at,published_by,restored_from_revision_id,
             rollback_backup_revision_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(record[key] for key in (
                "revision_id", "property_id", "revision_number", "status", "revision_kind",
                "snapshot_json", "snapshot_sha256", "preview_json", "created_at", "created_by",
                "published_at", "published_by", "restored_from_revision_id", "rollback_backup_revision_id",
            )),
        )
        row = db.execute(
            "SELECT * FROM map_revisions WHERE property_id=? AND revision_id=?",
            (property_id, record["revision_id"]),
        ).fetchone()
        return dict(row)

    def _read_map_revision_snapshot(self, row: Any, property_id: str, db: Any) -> dict[str, Any]:
        if row["property_id"] != property_id:
            raise KeyError("Map revision not found.")
        try:
            snapshot = json.loads(row["snapshot_json"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Map revision snapshot is corrupt.") from exc
        if not isinstance(snapshot, dict) or self._map_snapshot_digest(snapshot) != row["snapshot_sha256"]:
            raise ValueError("Map revision snapshot integrity check failed.")
        self._validate_map_snapshot(db, property_id, snapshot)
        return snapshot

    def _validate_map_snapshot(self, db: Any, property_id: str, snapshot: Any) -> None:
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("format") != 1
            or snapshot.get("property_id") != property_id
            or not isinstance(snapshot.get("tables"), dict)
            or set(snapshot["tables"]) != set(_MAP_SNAPSHOT_TABLES)
        ):
            raise ValueError("Map revision snapshot is invalid or belongs to another property.")
        tables = snapshot["tables"]
        records: dict[str, dict[str, dict[str, Any]]] = {}
        for table, primary_key in _MAP_SNAPSHOT_TABLES.items():
            rows = tables.get(table)
            expected_columns = table_columns(db, table)
            if not isinstance(rows, list):
                raise ValueError("Map revision snapshot is invalid.")
            keyed: dict[str, dict[str, Any]] = {}
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or set(row) != expected_columns
                    or row.get("property_id") != property_id
                    or not isinstance(row.get(primary_key), str)
                    or not row[primary_key]
                    or row[primary_key] in keyed
                ):
                    raise ValueError("Map revision snapshot contains an invalid or cross-property record.")
                keyed[row[primary_key]] = row
            records[table] = keyed

        buildings = records["buildings"]
        floors = records["floors"]
        zones = records["zones"]
        nodes = records["navigation_nodes"]
        for floor in floors.values():
            if floor["building_id"] not in buildings:
                raise ValueError("Map revision snapshot contains a floor outside its building set.")
        for table in ("floor_maps", "zones", "navigation_nodes"):
            if any(row["floor_id"] not in floors for row in records[table].values()):
                raise ValueError("Map revision snapshot contains an object outside its floor set.")
        for table in ("facilities", "access_points"):
            if any(row["zone_id"] not in zones for row in records[table].values()):
                raise ValueError("Map revision snapshot contains an object outside its zone set.")
        for node in nodes.values():
            if node["zone_id"] is not None and node["zone_id"] not in zones:
                raise ValueError("Map revision snapshot contains a waypoint outside its zone set.")
        for edge in records["navigation_edges"].values():
            if edge["from_node_id"] not in nodes or edge["to_node_id"] not in nodes:
                raise ValueError("Map revision snapshot contains a route outside its waypoint set.")
        for map_record in records["floor_maps"].values():
            self._validate_revision_map_asset(property_id, map_record)

    @staticmethod
    def _validate_revision_map_asset(property_id: str, record: dict[str, Any]) -> Path:
        content_type = record.get("content_type")
        if content_type not in FLOOR_PLAN_TYPES:
            raise ValueError("Map revision references an unsupported floor plan format.")
        root = Path(UPLOAD_ROOT).resolve()
        if not property_id or "/" in property_id or "\\" in property_id or property_id in {".", ".."}:
            raise ValueError("Map revision has an invalid property-scoped upload path.")
        property_directory = root / property_id
        floor_map_directory = property_directory / "floor_maps"
        if property_directory.resolve() != property_directory or floor_map_directory.resolve() != floor_map_directory:
            raise ValueError("Map revision has an unsafe floor plan directory.")
        try:
            path = Path(str(record.get("storage_path") or "")).resolve(strict=True)
            path.relative_to(floor_map_directory)
            path.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError("Map revision references a floor plan outside its property upload directory.") from exc
        if not path.is_file():
            raise ValueError("Map revision floor plan asset is missing.")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ValueError("Map revision floor plan asset cannot be read.") from exc
        if not raw or len(raw) > MAX_FLOOR_MAP_BYTES:
            raise ValueError("Map revision floor plan asset is invalid.")
        _validate_floor_map(content_type, raw)
        return path

    def _restore_map_snapshot(self, db: Any, property_id: str, snapshot: dict[str, Any]) -> None:
        self._validate_map_snapshot(db, property_id, snapshot)
        for table in _MAP_SNAPSHOT_DELETE_ORDER:
            db.execute(f"DELETE FROM {table} WHERE property_id=?", (property_id,))  # nosec B608: fixed table names.
        for table in _MAP_SNAPSHOT_INSERT_ORDER:
            columns = tuple(table_columns(db, table))
            # Use the actual table columns only after exact row-shape validation;
            # ordering is normalized below so bindings match across databases.
            columns = tuple(sorted(columns))
            placeholders = ",".join("?" for _ in columns)
            row_sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"  # nosec B608: names come from fixed schema introspection.
            for row in snapshot["tables"][table]:
                db.execute(row_sql, tuple(row[column] for column in columns))

    @staticmethod
    def _current_map_revision_id(db: Any, property_id: str) -> str | None:
        row = db.execute(
            "SELECT revision_id FROM map_revision_publications WHERE property_id=?",
            (property_id,),
        ).fetchone()
        return row["revision_id"] if row else None

    @staticmethod
    def _set_current_map_revision(
        db: Any,
        property_id: str,
        revision_id: str,
        published_at: int,
        published_by: str | None,
    ) -> None:
        db.execute(
            """INSERT INTO map_revision_publications(property_id,revision_id,published_at,published_by)
            VALUES (?,?,?,?)
            ON CONFLICT(property_id) DO UPDATE SET revision_id=excluded.revision_id,
            published_at=excluded.published_at,published_by=excluded.published_by""",
            (property_id, revision_id, published_at, published_by),
        )

    @staticmethod
    def _map_revision_metadata(row: Any) -> dict[str, Any]:
        return {
            "revision_id": row["revision_id"],
            "property_id": row["property_id"],
            "revision_number": int(row["revision_number"]),
            "status": row["status"],
            "revision_kind": row["revision_kind"],
            "created_at": int(row["created_at"]),
            "created_by": row["created_by"],
            "published_at": int(row["published_at"]) if row["published_at"] is not None else None,
            "published_by": row["published_by"],
            "restored_from_revision_id": row["restored_from_revision_id"],
            "rollback_backup_revision_id": row["rollback_backup_revision_id"],
            "preview": _load(row["preview_json"], fallback={}),
        }

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
        distance = _route_distance(payload.get("distance", 0))
        transition_type, accessible = self._edge_transition(
            property_id,
            edge["from_node_id"],
            edge["to_node_id"],
            payload.get("transition_type", edge["transition_type"]),
            payload.get("accessible", bool(edge["accessible"])),
        )
        with self._connect() as db:
            db.execute(
                """UPDATE navigation_edges SET distance=?,bidirectional=?,guest_visible=?,
                transition_type=?,accessible=?,updated_at=?
                WHERE edge_id=? AND property_id=?""",
                (
                    distance,
                    1 if payload.get("bidirectional", True) else 0,
                    1 if payload.get("guest_visible", True) else 0,
                    transition_type,
                    accessible,
                    _now(),
                    edge_id,
                    property_id,
                ),
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
        transition_type, accessible = self._edge_transition(
            property_id,
            from_node_id,
            to_node_id,
            payload.get("transition_type", "path"),
            payload.get("accessible", False),
        )
        now = _now()
        record = {
            "edge_id": _record_id("edge"),
            "property_id": property_id,
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "distance": _route_distance(payload.get("distance", 1)),
            "bidirectional": 1 if payload.get("bidirectional", True) else 0,
            "guest_visible": 1 if payload.get("guest_visible", True) else 0,
            "transition_type": transition_type,
            "accessible": 1 if accessible else 0,
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as db:
            db.execute(
                """INSERT INTO navigation_edges
                (edge_id,property_id,from_node_id,to_node_id,distance,bidirectional,guest_visible,
                 transition_type,accessible,created_at,updated_at)
                VALUES (:edge_id,:property_id,:from_node_id,:to_node_id,:distance,:bidirectional,:guest_visible,
                 :transition_type,:accessible,:created_at,:updated_at)""",
                record,
            )
        return self._public(record)

    def _edge_transition(
        self,
        property_id: str,
        from_node_id: str,
        to_node_id: str,
        transition_type: Any,
        accessible: Any,
    ) -> tuple[str, bool]:
        allowed_transitions = {"path", "elevator", "stairs", "ramp"}
        if not isinstance(transition_type, str) or transition_type.strip().casefold() not in allowed_transitions:
            raise ValueError("Route transition type must be path, elevator, stairs, or ramp.")
        transition_type = transition_type.strip().casefold()
        if not isinstance(accessible, bool):
            raise ValueError("Route accessibility must be explicitly true or false.")
        if transition_type == "stairs" and accessible:
            raise ValueError("Stair routes cannot be marked accessible.")

        with self._connect() as db:
            rows = db.execute(
                """SELECT n.node_id,n.floor_id,f.building_id
                FROM navigation_nodes n JOIN floors f ON f.floor_id=n.floor_id
                WHERE n.property_id=? AND n.node_id IN (?,?)""",
                (property_id, from_node_id, to_node_id),
            ).fetchall()
        nodes = {row["node_id"]: row for row in rows}
        if from_node_id not in nodes or to_node_id not in nodes:
            raise ValueError("Route endpoints are not available on configured floors.")
        from_node, to_node = nodes[from_node_id], nodes[to_node_id]
        if from_node["floor_id"] != to_node["floor_id"]:
            if from_node["building_id"] != to_node["building_id"]:
                raise ValueError("Cross-building transitions require separately verified route data.")
            if transition_type not in {"elevator", "stairs", "ramp"}:
                raise ValueError("Cross-floor routes require an explicit elevator, stairs, or ramp transition.")
        elif transition_type != "path":
            raise ValueError("Elevator, stairs, and ramp transitions must connect different floors.")
        return transition_type, accessible

    def overview(self, property_id: str, guest: bool = False) -> dict[str, Any]:
        with self._connect() as db:
            if guest:
                snapshot = self._published_map_snapshot(db, property_id)
                tables = snapshot["tables"] if snapshot else {name: [] for name in _MAP_SNAPSHOT_TABLES}
                buildings = sorted(tables["buildings"], key=lambda item: str(item.get("name") or "").casefold())
                floors = sorted(tables["floors"], key=lambda item: (item.get("building_id", ""), item.get("level", 0)))
                maps = [self._map_row(item) for item in sorted(
                    tables["floor_maps"], key=lambda item: (-int(item.get("created_at_us") or 0), item.get("map_id", ""))
                )]
                zones = [self._public(item) for item in tables["zones"] if item.get("guest_visible") in (1, True)]
                facilities = [self._public(item) for item in tables["facilities"] if item.get("guest_visible") in (1, True)]
                nodes = [self._public(item) for item in tables["navigation_nodes"] if item.get("guest_visible") in (1, True)]
                edges = [self._public(item) for item in tables["navigation_edges"] if item.get("guest_visible") in (1, True)]
                zones.sort(key=lambda item: str(item.get("name") or "").casefold())
                facilities.sort(key=lambda item: str(item.get("name") or "").casefold())
                nodes.sort(key=lambda item: str(item.get("label") or "").casefold())
                aps = []
            else:
                buildings = [dict(row) for row in db.execute("SELECT * FROM buildings WHERE property_id=? ORDER BY name", (property_id,))]
                floors = [dict(row) for row in db.execute("SELECT * FROM floors WHERE property_id=? ORDER BY building_id, level", (property_id,))]
                maps = [self._map_row(row) for row in db.execute("SELECT * FROM floor_maps WHERE property_id=? ORDER BY created_at_us DESC,map_id ASC", (property_id,))]
                zones = [self._public(row) for row in db.execute("SELECT * FROM zones WHERE property_id=? ORDER BY name", (property_id,))]
                facilities = [self._public(row) for row in db.execute("SELECT * FROM facilities WHERE property_id=? ORDER BY name", (property_id,))]
                nodes = [self._public(row) for row in db.execute("SELECT * FROM navigation_nodes WHERE property_id=? ORDER BY label", (property_id,))]
                edges = [self._public(row) for row in db.execute("SELECT * FROM navigation_edges WHERE property_id=?", (property_id,))]
                aps = [dict(row) for row in db.execute("SELECT * FROM access_points WHERE property_id=? ORDER BY name", (property_id,))]
        return {"buildings": buildings, "floors": floors, "maps": maps, "zones": zones, "facilities": facilities, "access_points": aps, "navigation_nodes": nodes, "navigation_edges": edges}

    def route(
        self,
        property_id: str,
        from_node_id: str,
        to_node_id: str,
        guest: bool = True,
        accessible: bool = False,
    ) -> dict[str, Any]:
        """Find a shortest route, requiring explicit accessible edges when requested."""
        return self._route(
            property_id,
            from_node_id,
            to_node_id,
            guest=guest,
            accessible=accessible,
        )

    def _route(
        self,
        property_id: str,
        from_node_id: str,
        to_node_id: str,
        *,
        guest: bool,
        accessible: bool,
    ) -> dict[str, Any]:
        if not isinstance(accessible, bool):
            raise ValueError("Route accessibility must be explicitly true or false.")
        graph: dict[str, list[tuple[str, float, str, bool]]] = {}
        labels: dict[str, str] = {}
        node_floors: dict[str, str] = {}
        floor_labels: dict[str, str] = {}
        buildings: dict[str, str] = {}
        with self._connect() as db:
            if guest:
                snapshot = self._published_map_snapshot(db, property_id)
                tables = snapshot["tables"] if snapshot else {name: [] for name in _MAP_SNAPSHOT_TABLES}
                floors = {item["floor_id"]: item for item in tables["floors"]}
                floor_rows = [
                    {
                        "node_id": item["node_id"],
                        "label": item["label"],
                        "floor_id": item["floor_id"],
                        "floor_label": floors[item["floor_id"]]["name"],
                        "building_id": floors[item["floor_id"]]["building_id"],
                    }
                    for item in tables["navigation_nodes"]
                    if item.get("guest_visible") in (1, True) and item.get("floor_id") in floors
                ]
                edge_rows = [item for item in tables["navigation_edges"] if item.get("guest_visible") in (1, True)]
            else:
                floor_rows = db.execute(
                    """SELECT n.node_id,n.label,n.floor_id,f.name AS floor_label,f.building_id
                    FROM navigation_nodes n JOIN floors f ON f.floor_id=n.floor_id
                    WHERE n.property_id=?""",
                    (property_id,),
                ).fetchall()
                edge_rows = db.execute(
                    "SELECT * FROM navigation_edges WHERE property_id=?",
                    (property_id,),
                ).fetchall()
            for row in floor_rows:
                labels[row["node_id"]] = row["label"]
                node_floors[row["node_id"]] = row["floor_id"]
                floor_labels[row["floor_id"]] = row["floor_label"]
                buildings[row["node_id"]] = row["building_id"]
                graph[row["node_id"]] = []
            for row in edge_rows:
                start_node = row["from_node_id"]
                end_node = row["to_node_id"]
                if start_node not in graph or end_node not in graph:
                    continue
                try:
                    weight = _route_distance(row["distance"])
                except ValueError as exc:
                    raise ValueError("Navigation graph contains an invalid route distance.") from exc
                transition_type = row["transition_type"]
                if row["accessible"] not in (0, 1):
                    continue
                edge_accessible = row["accessible"] == 1
                if transition_type not in {"path", "elevator", "stairs", "ramp"}:
                    continue
                if transition_type == "stairs" and edge_accessible:
                    continue
                from_floor, to_floor = node_floors[start_node], node_floors[end_node]
                if from_floor == to_floor:
                    if transition_type != "path":
                        continue
                elif (
                    buildings[start_node] != buildings[end_node]
                    or transition_type not in {"elevator", "stairs", "ramp"}
                ):
                    # Legacy cross-floor edges have no verified transition type.
                    continue
                if accessible and not edge_accessible:
                    continue
                graph[start_node].append((end_node, weight, transition_type, edge_accessible))
                if row["bidirectional"]:
                    graph[end_node].append((start_node, weight, transition_type, edge_accessible))
        if from_node_id not in graph or to_node_id not in graph:
            raise ValueError("Route endpoints are not available.")
        distances = {from_node_id: 0.0}
        previous: dict[str, tuple[str, str, bool]] = {}
        queue = [(0.0, from_node_id)]
        while queue:
            queue.sort(reverse=True)
            distance, node = queue.pop()
            if node == to_node_id:
                break
            for neighbor, weight, transition_type, edge_accessible in graph[node]:
                candidate = distance + weight
                if not math.isfinite(candidate):
                    raise ValueError("Navigation route distance overflowed.")
                if candidate < distances.get(neighbor, math.inf):
                    distances[neighbor] = candidate
                    previous[neighbor] = (node, transition_type, edge_accessible)
                    queue.append((candidate, neighbor))
        if to_node_id not in distances:
            raise ValueError("No route exists between these nodes.")
        path = [to_node_id]
        transitions = []
        while path[-1] != from_node_id:
            previous_node, transition_type, edge_accessible = previous[path[-1]]
            transitions.append({
                "from_node_id": previous_node,
                "to_node_id": path[-1],
                "type": transition_type,
                "accessible": edge_accessible,
                "from_floor_id": node_floors[previous_node],
                "to_floor_id": node_floors[path[-1]],
            })
            path.append(previous_node)
        path.reverse()
        transitions.reverse()
        floor_ids = list(dict.fromkeys(node_floors[node_id] for node_id in path))
        steps = [
            {
                "node_id": node_id,
                "label": labels[node_id],
                "floor_id": node_floors[node_id],
                "floor_label": floor_labels[node_floors[node_id]],
            }
            for node_id in path
        ]
        return {
            "node_ids": path,
            "labels": [labels[item] for item in path],
            "distance": distances[to_node_id],
            "floor_ids": floor_ids,
            "steps": steps,
            "transitions": transitions,
            "accessible": accessible,
        }

    def floor_map_path(self, property_id: str, map_id: str, *, guest: bool = False) -> Path:
        if guest:
            snapshot = self.published_map_snapshot(property_id)
            if snapshot is None or not any(
                item.get("map_id") == map_id for item in snapshot["tables"]["floor_maps"]
            ):
                raise KeyError("Floor map not found.")
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
        for key in ("guest_visible", "bidirectional", "accessible"):
            if key in data:
                data[key] = bool(data[key])
        return data
