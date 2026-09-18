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
    property_id: str = os.getenv("PROPERTY_ID", "demo-hotel")
    hotel_config_path: Path = Path(os.getenv("HOTEL_CONFIG_PATH", "data/hotel.json"))
    db_path: Path = Path(os.getenv("DB_PATH", "state/concierge.db"))
    session_ttl_minutes: int = int(os.getenv("SESSION_TTL_MINUTES", "30"))

    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    ollama_timeout_seconds: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45"))
    ollama_think: bool = _bool("OLLAMA_THINK", False)
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "160"))

    antlabs_mode: str = os.getenv("ANTLABS_MODE", "mock").strip().lower()
    antlabs_auth_url: str = os.getenv("ANTLABS_AUTH_URL", "").strip()
    antlabs_auth_method: str = os.getenv("ANTLABS_AUTH_METHOD", "POST").strip().upper()
    antlabs_room_field: str = os.getenv("ANTLABS_ROOM_FIELD", "room").strip()
    antlabs_last_name_field: str = os.getenv("ANTLABS_LAST_NAME_FIELD", "last_name").strip()
    antlabs_session_field: str = os.getenv("ANTLABS_SESSION_FIELD", "session").strip()
    antlabs_passthrough_fields: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("ANTLABS_PASSTHROUGH_FIELDS", "").split(",")
        if value.strip()
    )


settings = Settings()
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
