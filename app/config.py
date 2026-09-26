import os
import json
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Concierge.Ai")
    app_environment: str = os.getenv("APP_ENVIRONMENT", "development").strip().lower()
    property_id: str = os.getenv("PROPERTY_ID", "demo-hotel")
    hotel_config_path: Path = Path(os.getenv("HOTEL_CONFIG_PATH", "data/hotel.json"))
    db_path: Path = Path(os.getenv("DB_PATH", "state/concierge.db"))
    database_url: str = os.getenv("DATABASE_URL", "").strip()
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    metrics_token: str = os.getenv("METRICS_TOKEN", "").strip()
    background_workers_enabled: bool = _bool("ENABLE_BACKGROUND_WORKERS", True)
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
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "30"))
    admin_session_ttl_minutes: int = int(os.getenv("ADMIN_SESSION_TTL_MINUTES", "480"))
    admin_lockout_attempts: int = int(os.getenv("ADMIN_LOCKOUT_ATTEMPTS", "5"))
    admin_lockout_minutes: int = int(os.getenv("ADMIN_LOCKOUT_MINUTES", "15"))
    admin_bootstrap_username: str = os.getenv("ADMIN_BOOTSTRAP_USERNAME", "admin").strip()
    admin_bootstrap_password: str = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "ChangeMe123!")
    admin_cookie_secure: bool = _bool("ADMIN_COOKIE_SECURE", False)
    app_debug: bool = _bool("APP_DEBUG", False)
    allow_body_property_selection: bool = _bool("ALLOW_BODY_PROPERTY_SELECTION", False)
    allow_demo_settings: bool = _bool("ALLOW_DEMO_SETTINGS", False)

    ai_provider_mode: str = os.getenv("AI_PROVIDER_MODE", "auto").strip().lower()
    ai_guest_mode_switch: bool = _bool("AI_GUEST_MODE_SWITCH", True)
    ai_default_mode: str = os.getenv("AI_DEFAULT_MODE", "auto").strip().lower()
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "160"))
    credential_encryption_secret: str = os.getenv("CREDENTIAL_ENCRYPTION_SECRET", "").strip()

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45"))
    ollama_think: bool = _bool("OLLAMA_THINK", False)
    ai_provider_concurrency_limit: int = max(1, int(os.getenv("AI_PROVIDER_CONCURRENCY_LIMIT", "8")))
    ai_provider_concurrency_limits: dict[str, int] = field(default_factory=_provider_concurrency)
    ai_provider_queue_wait_seconds: float = max(0.05, float(os.getenv("AI_PROVIDER_QUEUE_WAIT_SECONDS", "1.5")))
    ai_provider_queue_capacity: int = max(0, min(1024, int(os.getenv("AI_PROVIDER_QUEUE_CAPACITY", "32"))))
    ai_provider_retry_attempts: int = max(0, min(3, int(os.getenv("AI_PROVIDER_RETRY_ATTEMPTS", "1"))))
    ai_provider_retry_base_seconds: float = max(0.01, float(os.getenv("AI_PROVIDER_RETRY_BASE_SECONDS", "0.25")))
    ai_provider_circuit_failures: int = max(1, int(os.getenv("AI_PROVIDER_CIRCUIT_FAILURES", "4")))
    ai_provider_circuit_cooldown_seconds: float = max(1.0, float(os.getenv("AI_PROVIDER_CIRCUIT_COOLDOWN_SECONDS", "20")))

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_fast_model: str = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite").strip()
    gemini_advanced_model: str = os.getenv("GEMINI_ADVANCED_MODEL", "gemini-3.8-flash").strip()

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_fast_model: str = os.getenv("OPENAI_FAST_MODEL", "gpt-5.6-luna").strip()
    openai_advanced_model: str = os.getenv("OPENAI_ADVANCED_MODEL", "gpt-5.6-terra").strip()

    compatible_api_base_url: str = os.getenv("COMPATIBLE_API_BASE_URL", "").strip().rstrip("/")
    compatible_api_key: str = os.getenv("COMPATIBLE_API_KEY", "").strip()
    compatible_fast_model: str = os.getenv("COMPATIBLE_FAST_MODEL", "").strip()
    compatible_advanced_model: str = os.getenv("COMPATIBLE_ADVANCED_MODEL", "").strip()

    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    places_radius_meters: int = int(os.getenv("PLACES_RADIUS_METERS", "5000"))
    places_max_results: int = int(os.getenv("PLACES_MAX_RESULTS", "6"))

    antlabs_mode: str = os.getenv("ANTLABS_MODE", "mock").strip().lower()
    antlabs_auth_url: str = os.getenv("ANTLABS_AUTH_URL", "").strip()
    antlabs_auth_method: str = os.getenv("ANTLABS_AUTH_METHOD", "POST").strip().upper()
    antlabs_room_field: str = os.getenv("ANTLABS_ROOM_FIELD", "uid").strip()
    antlabs_last_name_field: str = os.getenv("ANTLABS_LAST_NAME_FIELD", "pwd").strip()
    antlabs_session_field: str = os.getenv("ANTLABS_SESSION_FIELD", "").strip()
    antlabs_session_context_key: str = os.getenv("ANTLABS_SESSION_CONTEXT_KEY", "").strip()
    antlabs_passthrough_fields: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("ANTLABS_PASSTHROUGH_FIELDS", "").split(",")
        if value.strip()
    )


DEFAULT_ENCRYPTION_SECRETS = {
    "",
    "change-me",
    "changeme",
    "default",
    "replace-me",
    "your-secret-here",
}


def validate_production_settings(value: Settings, *, check_filesystem: bool = True) -> None:
    """Fail closed before any production database or account initialization occurs."""
    if value.app_environment != "production":
        return
    errors: list[str] = []
    try:
        validate_antlabs_mode(value.antlabs_mode)
    except ValueError as exc:
        errors.append(str(exc))
    if value.antlabs_mode == "browser_handoff" and not value.antlabs_auth_url:
        errors.append("ANTLABS_AUTH_URL must be configured for browser_handoff mode")
    if value.admin_bootstrap_password == "ChangeMe123!" or len(value.admin_bootstrap_password) < 12:
        errors.append("ADMIN_BOOTSTRAP_PASSWORD must be changed to a strong value")
    encryption_secret = value.credential_encryption_secret.strip()
    if (
        encryption_secret.casefold() in DEFAULT_ENCRYPTION_SECRETS
        or "replace-with" in encryption_secret.casefold()
        or len(encryption_secret) < 32
    ):
        errors.append("CREDENTIAL_ENCRYPTION_SECRET must be a non-default value of at least 32 characters")
    if not value.admin_cookie_secure:
        errors.append("ADMIN_COOKIE_SECURE must be enabled")
    if value.app_debug:
        errors.append("APP_DEBUG must be disabled")
    if value.allow_body_property_selection:
        errors.append("ALLOW_BODY_PROPERTY_SELECTION must be disabled")
    if not value.allow_demo_settings and (value.property_id == "demo-hotel" or value.antlabs_mode == "mock"):
        errors.append("demo property and mock guest authentication settings are not allowed")
    if value.database_url and not value.database_url.lower().startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
        errors.append("DATABASE_URL must use PostgreSQL when a server database is configured")
    if value.redis_url and not value.redis_url.lower().startswith(("redis://", "rediss://")):
        errors.append("REDIS_URL must use redis:// or rediss://")
    if len(value.metrics_token) < 32 or "replace-with" in value.metrics_token.casefold():
        errors.append("METRICS_TOKEN must contain at least 32 characters")
    if not value.database_url and check_filesystem:
        parent = value.db_path.expanduser().resolve().parent
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            errors.append("DB_PATH parent directory must exist and be writable")
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors) + ".")


settings = Settings()
settings = Settings(antlabs_mode=validate_antlabs_mode(settings.antlabs_mode))
validate_production_settings(settings)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
if not settings.upload_root.parts:
    object.__setattr__(settings, "upload_root", settings.db_path.parent / "uploads")
settings.upload_root.mkdir(parents=True, exist_ok=True)
