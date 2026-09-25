import base64
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .database import connect_database

from .zones import ANIMATION_TYPES, UPLOAD_ROOT


INTRO_PRESETS = {
    "none",
    "minimal_fade",
    "fade_scale",
    "luxury_reveal",
    "particle_assemble",
    "line_draw",
    "glass_blur",
    "split_reveal",
    "logo_to_chat_header",
}


class IntroExperienceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS intro_experience_configs (
                    property_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'none',
                    preset TEXT NOT NULL DEFAULT 'none',
                    duration_ms INTEGER NOT NULL DEFAULT 1400,
                    background TEXT NOT NULL DEFAULT '#fbfbfa',
                    brand_color TEXT NOT NULL DEFAULT '#18181b',
                    welcome_message TEXT NOT NULL DEFAULT '',
                    transition TEXT NOT NULL DEFAULT 'fade',
                    first_visit_only INTEGER NOT NULL DEFAULT 1,
                    allow_skip INTEGER NOT NULL DEFAULT 1,
                    asset_url TEXT NOT NULL DEFAULT '',
                    asset_type TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def get(self, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM intro_experience_configs WHERE property_id=?", (property_id,)).fetchone()
        if not row:
            return self._default(property_id)
        return self._row(row)

    def save(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "none")
        if mode not in {"none", "generate_from_logo", "custom_upload"}:
            raise ValueError("Invalid intro mode.")
        preset = str(payload.get("preset") or "none")
        if preset not in INTRO_PRESETS:
            raise ValueError("Invalid intro preset.")
        record = self.get(property_id)
        record.update(
            {
                "mode": mode,
                "preset": preset,
                "duration_ms": max(300, min(8000, int(payload.get("duration_ms") or 1400))),
                "background": str(payload.get("background") or "#fbfbfa")[:32],
                "brand_color": str(payload.get("brand_color") or "#18181b")[:32],
                "welcome_message": str(payload.get("welcome_message") or "")[:240],
                "transition": str(payload.get("transition") or "fade")[:40],
                "first_visit_only": bool(payload.get("first_visit_only", True)),
                "allow_skip": bool(payload.get("allow_skip", True)),
                "updated_at": int(time.time()),
            }
        )
        with self._connect() as db:
            db.execute(
                """INSERT INTO intro_experience_configs VALUES
                (:property_id,:mode,:preset,:duration_ms,:background,:brand_color,:welcome_message,:transition,
                :first_visit_only,:allow_skip,:asset_url,:asset_type,:updated_at)
                ON CONFLICT(property_id) DO UPDATE SET
                mode=excluded.mode,preset=excluded.preset,duration_ms=excluded.duration_ms,background=excluded.background,
                brand_color=excluded.brand_color,welcome_message=excluded.welcome_message,transition=excluded.transition,
                first_visit_only=excluded.first_visit_only,allow_skip=excluded.allow_skip,asset_url=excluded.asset_url,
                asset_type=excluded.asset_type,updated_at=excluded.updated_at""",
                self._db_record(record),
            )
        return self.get(property_id)

    def upload_asset(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        content_type = str(payload.get("content_type") or "")
        if content_type not in ANIMATION_TYPES:
            raise ValueError("Unsupported animation file type.")
        raw = base64.b64decode(str(payload.get("content_base64") or ""), validate=True)
        if not raw or len(raw) > 12 * 1024 * 1024:
            raise ValueError("Animation asset must be between 1 byte and 12 MB.")
        asset_id = "intro_" + uuid.uuid4().hex[:16]
        directory = UPLOAD_ROOT / property_id / "intro"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{asset_id}{ANIMATION_TYPES[content_type]}"
        path.write_bytes(raw)
        record = self.get(property_id)
        record["asset_url"] = f"/api/admin/properties/{property_id}/intro/assets/{asset_id}{ANIMATION_TYPES[content_type]}"
        record["asset_type"] = content_type
        record["mode"] = "custom_upload"
        self.save(property_id, record)
        return self.get(property_id)

    def asset_path(self, property_id: str, filename: str) -> Path:
        clean = Path(filename).name
        path = UPLOAD_ROOT / property_id / "intro" / clean
        resolved_root = (UPLOAD_ROOT / property_id / "intro").resolve()
        resolved_path = path.resolve()
        if resolved_root not in resolved_path.parents:
            raise ValueError("Invalid asset path.")
        if not resolved_path.exists():
            raise KeyError("Intro asset not found.")
        return resolved_path

    def _default(self, property_id: str) -> dict[str, Any]:
        return {
            "property_id": property_id,
            "mode": "none",
            "preset": "none",
            "duration_ms": 1400,
            "background": "#fbfbfa",
            "brand_color": "#18181b",
            "welcome_message": "",
            "transition": "fade",
            "first_visit_only": True,
            "allow_skip": True,
            "asset_url": "",
            "asset_type": "",
            "updated_at": int(time.time()),
        }

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["first_visit_only"] = bool(record["first_visit_only"])
        record["allow_skip"] = bool(record["allow_skip"])
        return record

    def _db_record(self, record: dict[str, Any]) -> dict[str, Any]:
        copy = dict(record)
        copy["first_visit_only"] = 1 if copy["first_visit_only"] else 0
        copy["allow_skip"] = 1 if copy["allow_skip"] else 0
        return copy
