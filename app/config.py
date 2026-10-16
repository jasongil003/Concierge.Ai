import os
import json
import re
import tempfile
from dataclasses import dataclass, field
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()

SUPPORTED_ANTLABS_MODES = frozenset({"mock", "browser_handoff"})


def _provider_concurrency() -> dict[str, int]:
    try:
        parsed = json.loads(os.getenv("AI_PROVIDER_CONCURRENCY_LIMITS", "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, int] = {}
    for provider, value in parsed.items():
        if provider not in {"gemini", "groq", "openai", "openrouter", "claude", "local"}:
            continue
        try:
            result[provider] = max(1, min(int(value), 256))
        except (TypeError, ValueError):
            continue
    return result


def validate_antlabs_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in SUPPORTED_ANTLABS_MODES:
        raise ValueError(
            f"Unsupported ANTLABS_MODE '{mode}'. Supported modes are: "
            + ", ".join(sorted(SUPPORTED_ANTLABS_MODES))
            + "."
        )
    return normalized


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _looks_like_production_name(value: str) -> bool:
    parts = re.findall(r"[a-z0-9]+", value.casefold())
    return bool({"prod", "production", "live"}.intersection(parts))


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Concierge.Ai")
    app_environment: str = os.getenv("APP_ENVIRONMENT", "development").strip().lower()
    deployment_mode: str = os.getenv("CONCIERGE_DEPLOYMENT_MODE", "source").strip().lower()
    property_id: str = os.getenv("PROPERTY_ID", "").strip()
    db_path: Path = Path(os.getenv("DB_PATH", "state/concierge.db"))
    state_directory: Path = Path(os.getenv("STATE_DIRECTORY", "")) if os.getenv("STATE_DIRECTORY") else Path("")
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    metrics_token: str = os.getenv("METRICS_TOKEN", "").strip()
    background_workers_enabled: bool = _bool("ENABLE_BACKGROUND_WORKERS", True)
    retention_maintenance_interval_seconds: int = max(
        30, min(int(os.getenv("RETENTION_MAINTENANCE_INTERVAL_SECONDS", "300")), 86400)
    )
    guest_notification_retention_days: int = max(
        0, min(int(os.getenv("GUEST_NOTIFICATION_RETENTION_DAYS", "7")), 365)
    )
    guest_data_retention_days: int = max(
        0, min(int(os.getenv("GUEST_DATA_RETENTION_DAYS", "2")), 60)
    )
    db_pool_size: int = max(1, int(os.getenv("DB_POOL_SIZE", "8")))
    db_max_overflow: int = max(0, int(os.getenv("DB_MAX_OVERFLOW", "4")))
    db_pool_timeout_seconds: float = max(0.1, float(os.getenv("DB_POOL_TIMEOUT_SECONDS", "5")))
    db_pool_recycle_seconds: int = max(60, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")))
    db_statement_timeout_ms: int = max(100, int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "5000")))
    db_connect_timeout_seconds: int = max(1, int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5")))
    upload_root: Path = Path(os.getenv("UPLOAD_ROOT", "")) if os.getenv("UPLOAD_ROOT") else Path("")  # resolved below
    knowledge_max_file_bytes: int = int(os.getenv("KNOWLEDGE_MAX_FILE_BYTES", str(25 * 1024 * 1024)))
    knowledge_max_files_per_upload: int = int(os.getenv("KNOWLEDGE_MAX_FILES_PER_UPLOAD", "5"))
    knowledge_max_files_per_property: int = int(os.getenv("KNOWLEDGE_MAX_FILES_PER_PROPERTY", "500"))
    knowledge_storage_quota_bytes: int = int(os.getenv("KNOWLEDGE_STORAGE_QUOTA_BYTES", str(2 * 1024 * 1024 * 1024)))
    knowledge_max_extracted_chars: int = int(os.getenv("KNOWLEDGE_MAX_EXTRACTED_CHARS", "500000"))
   