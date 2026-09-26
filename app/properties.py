import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .database import connect_database

from .guardrails import public_guardrails


SAFE_FONTS = {
    "Geist",
    "Inter",
    "Manrope",
    "DM Sans",
    "Poppins",
    "Montserrat",
    "Lato",
    "Merriweather",
    "Playfair Display",
    "system-ui",
}
HEX_FIELDS = {
    "background",
    "surface",
    "textPrimary",
    "textSecondary",
    "accent",
    "accentText",
    "border",
    "userMessageBackground",
    "userMessageText",
    "assistantText",
    "composerBackground",
    "buttonColor",
}

AUTHENTICATION_RULES = {
    "complimentary": {
        "fields": ["code", "plan"],
        "guest_guidance": "Use this when the hotel provides a complimentary access code or free internet plan.",
    },
    "local": {
        "fields": ["username", "password"],
        "guest_guidance": "Use this when the guest has a locally managed username and password.",
    },
    "radius": {
        "fields": ["username", "password", "plan"],
        "guest_guidance": "Use this for external RADIUS account authentication.",
    },
    "pms": {
        "fields": ["room", "last_name"],
        "guest_guidance": "Use this for room or reservation based guest authentication.",
    },
    "credit_card": {
        "fields": ["card_payment", "plan"],
        "guest_guidance": "Use this when the guest must purchase internet access by card.",
    },
    "access_code": {
        "fields": ["access_code"],
        "guest_guidance": "Use this when the guest has a hotel-issued access code.",
    },
    "global_account": {
        "fields": ["username", "password"],
        "guest_guidance": "Use this when the guest has a global roaming or group account.",
    },
    "global_code": {
        "fields": ["global_code"],
        "guest_guidance": "Use this when the guest has a global access code.",
    },
    "user_form": {
        "fields": ["name", "email"],
        "guest_guidance": "Use this when the hotel requires a guest registration form.",
    },
    "social_network": {
        "fields": ["social_provider"],
        "guest_guidance": "Use this when social login is enabled for the hotel.",
    },
}


def default_design_config(
    hotel_name: str = "",
    concierge_name: str = "Concierge",
    welcome: str = "How can I help with your stay?",
    quick_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    suggestions = []
    for index, action in enumerate(quick_actions or []):
        prompt = action.get("prompt") or action.get("label") or ""
        suggestions.append(
            {
                "label": action.get("label") or prompt[:28] or "Suggestion",
                "icon": "",
                "prompt": prompt,
                "enabled": True,
                "order": index,
            }
        )
    return {
        "branding": {
            "hotelName": hotel_name,
            "conciergeName": concierge_name,
            "logoUrl": "",
            "logoDisplay": "mark_name",
            "conciergeAvatarUrl": "",
            "faviconUrl": "",
        },
        "theme": {
            "font": "Geist",
            "background": "#fbfbfa",
            "surface": "#ffffff",
            "textPrimary": "#18181b",
            "textSecondary": "#71717a",
            "accent": "#18181b",
            "accentText": "#ffffff",
            "border": "#e4e4e7",
            "userMessageBackground": "#eeeeee",
            "userMessageText": "#18181b",
            "assistantText": "#18181b",
            "composerBackground": "#ffffff",
            "buttonColor": "#18181b",
            "radius": 14,
            "density": "comfortable",
            "backgroundImageUrl": "",
            "backgroundOverlay": 0,
        },
        "typography": {
            "fontFamily": "Geist",
            "baseFontSize": 15,
            "headingWeight": 600,
            "bodyWeight": 400,
            "letterSpacing": 0,
        },
        "layout": {
            "contentWidth": 840,
            "messageWidth": 680,
            "messageSpacing": 24,
            "composerWidth": 840,
            "composerPosition": "bottom",
            "suggestionLayout": "stack",
        },
        "header": {
            "enabled": True,
            "showLogo": True,
            "showHotelName": True,
            "showConciergeName": True,
            "subtitle": "",
            "sticky": True,
            "background": "#fbfbfa",
            "border": True,
        },
        "welcome": {
            "greeting": "Good evening.",
            "headline": welcome,
            "description": "",
        },
        "composer": {
            "placeholder": "Ask about your stay...",
            "attachments": False,
            "voice": False,
            "border": True,
            "radius": 24,
            "background": "#ffffff",
            "sendButtonStyle": "filled",
        },
        "messages": {
            "userStyle": "bubble",
            "assistantStyle": "minimal",
            "radius": 18,
            "messageSpacing": 24,
            "avatarVisibility": False,
            "timestampVisibility": False,
        },
        "suggestions": suggestions,
    }


def validate_design_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = default_design_config()
    for section, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(section), dict):
            merged[section].update(value)
        else:
            merged[section] = value

    theme = merged["theme"]
    typography = merged["typography"]
    layout = merged["layout"]
    composer = merged["composer"]
    messages = merged["messages"]

    font = typography.get("fontFamily") or theme.get("font") or "Geist"
    if font not in SAFE_FONTS:
        raise ValueError("Unsupported font family.")
    theme["font"] = font
    typography["fontFamily"] = font

    for field in HEX_FIELDS:
        value = theme.get(field)
        if not isinstance(value, str) or not _is_hex(value):
            raise ValueError(f"Invalid color value for {field}.")

    for field, minimum, maximum in (
        ("radius", 0, 32),
        ("backgroundOverlay", 0, 70),
    ):
        theme[field] = _bounded_int(theme.get(field), minimum, maximum, field)

    typography["baseFontSize"] = _bounded_int(typography.get("baseFontSize"), 12, 20, "baseFontSize")
    typography["headingWeight"] = _bounded_int(typography.get("headingWeight"), 400, 800, "headingWeight")
    typography["bodyWeight"] = _bounded_int(typography.get("bodyWeight"), 300, 700, "bodyWeight")
    typography["letterSpacing"] = _bounded_float(typography.get("letterSpacing"), -0.02, 0.08, "letterSpacing")
    layout["contentWidth"] = _bounded_int(layout.get("contentWidth"), 320, 1100, "contentWidth")
    layout["messageWidth"] = _bounded_int(layout.get("messageWidth"), 280, 900, "messageWidth")
    layout["messageSpacing"] = _bounded_int(layout.get("messageSpacing"), 10, 44, "messageSpacing")
    layout["composerWidth"] = _bounded_int(layout.get("composerWidth"), 320, 1100, "composerWidth")
    composer["radius"] = _bounded_int(composer.get("radius"), 8, 32, "composer radius")
    messages["radius"] = _bounded_int(messages.get("radius"), 0, 28, "message radius")
    messages["messageSpacing"] = _bounded_int(messages.get("messageSpacing"), 10, 44, "message spacing")

    if theme.get("density") not in {"compact", "comfortable"}:
        raise ValueError("Invalid density.")
    if layout.get("suggestionLayout") not in {"stack", "grid", "inline"}:
        raise ValueError("Invalid suggestion layout.")
    if messages.get("userStyle") not in {"bubble", "minimal"}:
        raise ValueError("Invalid user message style.")
    if messages.get("assistantStyle") not in {"minimal", "bubble"}:
        raise ValueError("Invalid assistant message style.")
    if composer.get("sendButtonStyle") not in {"filled", "minimal"}:
        raise ValueError("Invalid send button style.")
    if merged["branding"].get("logoDisplay") not in {"mark_name", "logo_only", "name_only"}:
        raise ValueError("Invalid logo display mode.")

    suggestions = []
    for index, suggestion in enumerate(merged.get("suggestions", [])):
        if not isinstance(suggestion, dict):
            continue
        label = str(suggestion.get("label", "")).strip()[:48]
        prompt = str(suggestion.get("prompt", "")).strip()[:500]
        if not label or not prompt:
            continue
        suggestions.append(
            {
                "label": label,
                "icon": str(suggestion.get("icon", "")).strip()[:32],
                "prompt": prompt,
                "enabled": bool(suggestion.get("enabled", True)),
                "order": int(suggestion.get("order", index)),
            }
        )
    suggestions.sort(key=lambda item: item["order"])
    merged["suggestions"] = suggestions[:12]
    return merged


def _is_hex(value: str) -> bool:
    if len(value) != 7 or not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def _bounded_float(value: Any, minimum: float, maximum: float, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {name}.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


@dataclass
class PropertyRecord:
    property_id: str
    hotel_name: str
    description: str = ""
    domain: str = ""
    deployment_mode: str = "on-prem"
    timezone: str = "UTC"
    latitude: float | None = None
    longitude: float | None = None
    address: str = ""
    contact_details: dict[str, Any] = field(default_factory=dict)
    logo_url: str = ""
    brand_assets: dict[str, Any] = field(default_factory=dict)
    concierge_name: str = "Concierge"
    concierge_avatar_url: str = ""
    primary_color: str = "#171717"
    secondary_color: str = "#f4f3ef"
    background: str = ""
    languages: list[str] = field(default_factory=lambda: ["en"])
    facilities: list[dict[str, Any]] = field(default_factory=list)
    dining: list[dict[str, Any]] = field(default_factory=list)
    spa: dict[str, Any] = field(default_factory=dict)
    pool: dict[str, Any] = field(default_factory=dict)
    gym: dict[str, Any] = field(default_factory=dict)
    policies: list[dict[str, Any]] = field(default_factory=list)
    support_contacts: list[dict[str, Any]] = field(default_factory=list)
    quick_actions: list[dict[str, Any]] = field(default_factory=list)
    ai_settings: dict[str, Any] = field(default_factory=dict)
    antlabs_config: dict[str, Any] = field(default_factory=dict)
    knowledge_sources: list[dict[str, Any]] = field(default_factory=list)
    rooms: list[dict[str, Any]] = field(default_factory=list)
    guest_modules: list[dict[str, Any]] = field(default_factory=list)
    personality: dict[str, Any] = field(default_factory=dict)
    guardrails: dict[str, Any] = field(default_factory=dict)
    app_settings: dict[str, Any] = field(default_factory=dict)
    welcome: str = "How can I help?"
    design_draft: dict[str, Any] = field(default_factory=default_design_config)
    design_published: dict[str, Any] = field(default_factory=default_design_config)
    design_versions: list[dict[str, Any]] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0

    def to_dict(self, include_secrets: bool = False) -> dict[str, Any]:
        payload = {
            "property_id": self.property_id,
            "hotel_name": self.hotel_name,
            "description": self.description,
            "domain": self.domain,
            "deployment_mode": self.deployment_mode,
            "timezone": self.timezone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "contact_details": self.contact_details,
            "logo_url": self.logo_url,
            "brand_assets": self.brand_assets,
            "concierge_name": self.concierge_name,
            "concierge_avatar_url": self.concierge_avatar_url,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "background": self.background,
            "languages": self.languages,
            "facilities": self.facilities,
            "dining": self.dining,
            "spa": self.spa,
            "pool": self.pool,
            "gym": self.gym,
            "policies": self.policies,
            "support_contacts": self.support_contacts,
            "quick_actions": self.quick_actions,
            "ai_settings": self.ai_settings,
            "antlabs_config": self.antlabs_config,
            "knowledge_sources": self.knowledge_sources,
            "rooms": self.rooms,
            "guest_modules": self.guest_modules,
            "personality": self.personality,
            "guardrails": self.guardrails,
            "app_settings": self.app_settings,
            "welcome": self.welcome,
            "design_draft": self.design_draft,
            "design_published": self.design_published,
            "design_versions": self.design_versions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if not include_secrets:
            payload["guardrails"] = public_guardrails(self.guardrails)
        return payload

    @property
    def public_profile(self) -> dict[str, Any]:
        authentication_types = self.antlabs_config.get("authentication_types", {})
        enabled_authentication_types = [
            {
                "id": auth_id,
                "label": value.get("label", auth_id.replace("_", " ").title()),
                "fields": AUTHENTICATION_RULES.get(auth_id, {}).get("fields", []),
                "guest_guidance": AUTHENTICATION_RULES.get(auth_id, {}).get("guest_guidance", ""),
            }
            for auth_id, value in authentication_types.items()
            if isinstance(value, dict) and value.get("enabled")
        ]
        return {
            "property_id": self.property_id,
            "name": self.hotel_name,
            "description": self.description,
            "domain": self.domain,
            "deployment_mode": self.deployment_mode,
            "timezone": self.timezone,
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "address": self.address,
            },
            "logo_url": self.logo_url,
            "concierge_name": self.concierge_name,
            "concierge_avatar_url": self.concierge_avatar_url,
            "theme": {
                "primary_color": self.primary_color,
                "secondary_color": self.secondary_color,
                "background": self.background,
            },
            "languages": self.languages,
            "facilities": self.facilities,
            "dining": self.dining,
            "spa": self.spa,
            "pool": self.pool,
            "gym": self.gym,
            "policies": self.policies,
            "support_contacts": self.support_contacts,
            "quick_actions": self.quick_actions,
            "rooms": self.rooms,
            "guest_modules": [item for item in self.guest_modules if item.get("enabled", True)],
            "locations": [item for item in (self.app_settings.get("locations") or []) if item.get("guest_visible", True)],
            "application": {
                "default_language": (self.app_settings.get("application") or {}).get("default_language", self.languages[0] if self.languages else "en"),
                "maintenance_enabled": bool((self.app_settings.get("application") or {}).get("maintenance_enabled", False)),
                "maintenance_message": (self.app_settings.get("application") or {}).get("maintenance_message", ""),
            },
            "welcome": self.welcome,
            "ai": self.ai_settings,
            "authentication": {
                "enabled_types": enabled_authentication_types,
            },
            "design": self.design_published,
        }


class PropertyStore:
    JSON_COLUMNS = {
        "contact_details",
        "brand_assets",
        "languages",
        "facilities",
        "dining",
        "spa",
        "pool",
        "gym",
        "policies",
        "support_contacts",
        "quick_actions",
        "ai_settings",
        "antlabs_config",
        "knowledge_sources",
        "rooms",
        "guest_modules",
        "personality",
        "guardrails",
        "app_settings",
        "design_draft",
        "design_published",
        "design_versions",
    }

    COLUMNS = (
        "property_id",
        "hotel_name",
        "description",
        "domain",
        "deployment_mode",
        "timezone",
        "latitude",
        "longitude",
        "address",
        "contact_details",
        "logo_url",
        "brand_assets",
        "concierge_name",
        "concierge_avatar_url",
        "primary_color",
        "secondary_color",
        "background",
        "languages",
        "facilities",
        "dining",
        "spa",
        "pool",
        "gym",
        "policies",
        "support_contacts",
        "quick_actions",
        "ai_settings",
        "antlabs_config",
        "knowledge_sources",
        "rooms",
        "guest_modules",
        "personality",
        "guardrails",
        "app_settings",
        "welcome",
        "design_draft",
        "design_published",
        "design_versions",
        "created_at",
        "updated_at",
    )
    UPSERT_SQL = """
        INSERT INTO properties ({columns})
        VALUES ({placeholders})
        ON CONFLICT(property_id) DO UPDATE SET {updates}
    """.format(
        columns=", ".join(COLUMNS),
        placeholders=", ".join("?" for _ in COLUMNS),
        updates=", ".join(
            f"{column} = excluded.{column}" for column in COLUMNS if column != "property_id"
        ),
    )

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS properties (
                    property_id TEXT PRIMARY KEY,
                    hotel_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    domain TEXT NOT NULL DEFAULT '',
                    deployment_mode TEXT NOT NULL DEFAULT 'on-prem',
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    latitude REAL,
                    longitude REAL,
                    address TEXT NOT NULL DEFAULT '',
                    contact_details TEXT NOT NULL DEFAULT '{}',
                    logo_url TEXT NOT NULL DEFAULT '',
                    brand_assets TEXT NOT NULL DEFAULT '{}',
                    concierge_name TEXT NOT NULL DEFAULT 'Concierge',
                    concierge_avatar_url TEXT NOT NULL DEFAULT '',
                    primary_color TEXT NOT NULL DEFAULT '#171717',
                    secondary_color TEXT NOT NULL DEFAULT '#f4f3ef',
                    background TEXT NOT NULL DEFAULT '',
                    languages TEXT NOT NULL DEFAULT '["en"]',
                    facilities TEXT NOT NULL DEFAULT '[]',
                    dining TEXT NOT NULL DEFAULT '[]',
                    spa TEXT NOT NULL DEFAULT '{}',
                    pool TEXT NOT NULL DEFAULT '{}',
                    gym TEXT NOT NULL DEFAULT '{}',
                    policies TEXT NOT NULL DEFAULT '[]',
                    support_contacts TEXT NOT NULL DEFAULT '[]',
                    quick_actions TEXT NOT NULL DEFAULT '[]',
                    ai_settings TEXT NOT NULL DEFAULT '{}',
                    antlabs_config TEXT NOT NULL DEFAULT '{}',
                    knowledge_sources TEXT NOT NULL DEFAULT '[]',
                    rooms TEXT NOT NULL DEFAULT '[]',
                    guest_modules TEXT NOT NULL DEFAULT '[]',
                    personality TEXT NOT NULL DEFAULT '{}',
                    guardrails TEXT NOT NULL DEFAULT '{}',
                    app_settings TEXT NOT NULL DEFAULT '{}',
                    welcome TEXT NOT NULL DEFAULT 'How can I help?',
                    design_draft TEXT NOT NULL DEFAULT '{}',
                    design_published TEXT NOT NULL DEFAULT '{}',
                    design_versions TEXT NOT NULL DEFAULT '[]',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            self._ensure_column(db, "design_draft", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(db, "design_published", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(db, "design_versions", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "rooms", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "guest_modules", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(db, "personality", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(db, "guardrails", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(db, "app_settings", "TEXT NOT NULL DEFAULT '{}'")

    def list(self) -> list[PropertyRecord]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM properties ORDER BY hotel_name").fetchall()
        return [self._record_from_row(row) for row in rows]

    def get(self, property_id: str) -> PropertyRecord | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM properties WHERE property_id = ?",
                (property_id,),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def upsert(self, record: PropertyRecord) -> PropertyRecord:
        now = int(time.time())
        existing = self.get(record.property_id)
        record.created_at = existing.created_at if existing else now
        record.updated_at = now
        payload = self._serialize_record(record)
        with self._connect() as db:
            db.execute(self.UPSERT_SQL, [payload[column] for column in self.COLUMNS])
        return record

    def delete(self, property_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM properties WHERE property_id = ?", (property_id,))
            return cursor.rowcount > 0

    def save_design_draft(self, property_id: str, config: dict[str, Any]) -> PropertyRecord:
        record = self.get(property_id)
        if record is None:
            raise KeyError(property_id)
        record.design_draft = validate_design_config(config)
        record.updated_at = int(time.time())
        return self.upsert(record)

    def publish_design(self, property_id: str, published_by: str = "local-admin") -> PropertyRecord:
        record = self.get(property_id)
        if record is None:
            raise KeyError(property_id)
        published = validate_design_config(record.design_draft)
        now = int(time.time())
        record.design_published = published
        versions = list(record.design_versions)
        next_version = max((v["version"] for v in versions), default=0) + 1
        versions.append(
            {
                "version": next_version,
                "published_at": now,
                "published_by": published_by,
                "config": published,
            }
        )
        record.design_versions = versions[-10:]
        record.updated_at = now
        return self.upsert(record)

    def restore_design_version(self, property_id: str, version: int) -> PropertyRecord:
        record = self.get(property_id)
        if record is None:
            raise KeyError(property_id)
        match = next((item for item in record.design_versions if item.get("version") == version), None)
        if match is None:
            raise ValueError("Version not found.")
        record.design_draft = validate_design_config(match["config"])
        record.updated_at = int(time.time())
        return self.upsert(record)

    def seed_from_hotel_json(self, property_id: str, hotel_json_path: Path) -> PropertyRecord:
        existing = self.get(property_id)
        if existing:
            return existing

        data = json.loads(hotel_json_path.read_text(encoding="utf-8"))
        location = data.get("location", {})
        record = PropertyRecord(
            property_id=property_id,
            hotel_name=data.get("name", ""),
            concierge_name=data.get("concierge_name", "Concierge"),
            welcome=data.get("welcome", "How can I help?"),
            quick_actions=data.get("quick_actions", []),
            ai_settings=data.get("ai", {}),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            address=location.get("label", ""),
            knowledge_sources=[
                {
                    "type": "seed_json",
                    "path": str(hotel_json_path),
                    "status": "active",
                }
            ],
        )
        record.design_draft = default_design_config(
            hotel_name=record.hotel_name,
            concierge_name=record.concierge_name,
            welcome=record.welcome,
            quick_actions=record.quick_actions,
        )
        record.design_published = record.design_draft
        return self.upsert(record)

    def _serialize_record(self, record: PropertyRecord) -> dict[str, Any]:
        data = record.to_dict(include_secrets=True)
        for column in self.JSON_COLUMNS:
            data[column] = json.dumps(data[column], separators=(",", ":"))
        return data

    def _record_from_row(self, row: sqlite3.Row) -> PropertyRecord:
        data = dict(row)
        for column in self.JSON_COLUMNS:
            data[column] = json.loads(data[column])
        if not data.get("design_draft"):
            data["design_draft"] = default_design_config(
                hotel_name=data.get("hotel_name", ""),
                concierge_name=data.get("concierge_name", "Concierge"),
                welcome=data.get("welcome", "How can I help?"),
                quick_actions=data.get("quick_actions", []),
            )
        if not data.get("design_published"):
            data["design_published"] = data["design_draft"]
        return PropertyRecord(**data)

    def _ensure_column(self, db: sqlite3.Connection, name: str, definition: str) -> None:
        allowed_definitions = {
            "design_draft": "TEXT NOT NULL DEFAULT '{}'",
            "design_published": "TEXT NOT NULL DEFAULT '{}'",
            "design_versions": "TEXT NOT NULL DEFAULT '[]'",
            "rooms": "TEXT NOT NULL DEFAULT '[]'",
            "guest_modules": "TEXT NOT NULL DEFAULT '[]'",
            "personality": "TEXT NOT NULL DEFAULT '{}'",
            "guardrails": "TEXT NOT NULL DEFAULT '{}'",
            "app_settings": "TEXT NOT NULL DEFAULT '{}'",
        }
        if allowed_definitions.get(name) != definition:
            raise ValueError("Unsupported property schema column migration.")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(properties)").fetchall()}
        if name not in columns:
            db.execute(f"ALTER TABLE properties ADD COLUMN {name} {definition}")  # nosec B608
