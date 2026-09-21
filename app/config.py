import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


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
    upload_root: Path = Path(os.getenv("UPLOAD_ROOT", "")) if os.getenv("UPLOAD_ROOT") else Path("")  # resolved below
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "30"))
    admin_session_ttl_minutes: int = int(os.getenv("ADMIN_SESSION_TTL_MINUTES", "480"))
    admin_lockout_attempts: int = int(os.getenv("ADMIN_LOCKOUT_ATTEMPTS", "5"))
    admin_lockout_minutes: int = int(os.getenv("ADMIN_LOCKOUT_MINUTES", "15"))
    admin_bootstrap_username: str = os.getenv("ADMIN_BOOTSTRAP_USERNAME", "admin").strip()
    admin_bootstrap_password: str = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "ChangeMe123!")
    admin_cookie_secure: bool = _bool("ADMIN_COOKIE_SECURE", False)

    ai_provider_mode: str = os.getenv("AI_PROVIDER_MODE", "auto").strip().lower()
    ai_guest_mode_switch: bool = _bool("AI_GUEST_MODE_SWITCH", True)
    ai_default_mode: str = os.getenv("AI_DEFAULT_MODE", "auto").strip().lower()
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "160"))
    credential_encryption_secret: str = os.getenv("CREDENTIAL_ENCRYPTION_SECRET", "").strip()

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45"))
    ollama_think: bool = _bool("OLLAMA_THINK", False)

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
    antlabs_room_field: str = os.getenv("ANTLABS_ROOM_FIELD", "room").strip()
    antlabs_last_name_field: str = os.getenv("ANTLABS_LAST_NAME_FIELD", "last_name").strip()
    antlabs_session_field: str = os.getenv("ANTLABS_SESSION_FIELD", "").strip()
    antlabs_session_context_key: str = os.getenv("ANTLABS_SESSION_CONTEXT_KEY", "").strip()
    antlabs_passthrough_fields: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("ANTLABS_PASSTHROUGH_FIELDS", "").split(",")
        if value.strip()
    )


settings = Settings()
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
if not settings.upload_root.parts:
    object.__setattr__(settings, "upload_root", settings.db_path.parent / "uploads")
settings.upload_root.mkdir(parents=True, exist_ok=True)
