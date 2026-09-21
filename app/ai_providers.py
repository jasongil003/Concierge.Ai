import base64
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

import httpx
from cryptography.fernet import Fernet

from .config import settings
from .llm import build_prompt


PROVIDER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gemini": {
        "name": "Google Gemini",
        "auth_methods": ["oauth", "api_key"],
        "default_auth_method": "api_key",
        "status_note": "Google OAuth is supported by Gemini API for approved workflows; API key remains available as fallback.",
        "default_model": "gemini-3.8-flash",
        "model_catalog": ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.8-pro"],
        "cloud": True,
    },
    "groq": {
        "name": "Groq",
        "auth_methods": ["api_key"],
        "default_auth_method": "api_key",
        "status_note": "Groq officially supports API-key authentication for API usage.",
        "default_model": "llama-3.3-70b-versatile",
        "model_catalog": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "cloud": True,
    },
    "openai": {
        "name": "OpenAI",
        "auth_methods": ["api_key"],
        "default_auth_method": "api_key",
        "status_note": "OpenAI API usage is separate from consumer ChatGPT plans and currently uses API credentials.",
        "default_model": "gpt-5.6-terra",
        "model_catalog": ["gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol"],
        "cloud": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "auth_methods": ["api_key"],
        "default_auth_method": "api_key",
        "status_note": "OpenRouter uses an OpenAI-compatible API and routes requests to multiple third-party model providers.",
        "default_model": "openai/gpt-4o-mini",
        "model_catalog": [
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-flash-1.5",
            "meta-llama/llama-3.1-70b-instruct",
        ],
        "cloud": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "auth_methods": ["api_key"],
        "default_auth_method": "api_key",
        "status_note": "Anthropic Messages API supports API-key and enterprise identity methods.",
        "default_model": "claude-sonnet-4-5",
        "model_catalog": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1"],
        "cloud": True,
    },
    "copilot": {
        "name": "GitHub Copilot",
        "auth_methods": ["github_oauth"],
        "default_auth_method": "github_oauth",
        "status_note": "Requires eligible GitHub Copilot SDK/API integration. No unofficial Copilot backend is implemented.",
        "default_model": "",
        "model_catalog": [],
        "cloud": True,
        "unavailable": True,
    },
    "local": {
        "name": "Local AI",
        "auth_methods": ["none", "api_key"],
        "default_auth_method": "none",
        "status_note": "Supports Ollama, LM Studio, and OpenAI-compatible local endpoints.",
        "default_model": settings.ollama_model,
        "model_catalog": [settings.ollama_model, "llama3.1:8b", "mistral:7b", "phi4:latest"],
        "cloud": False,
    },
}


@dataclass
class AIMessage:
    role: str
    content: str


@dataclass
class AIChatRequest:
    property_id: str
    provider_id: str
    model: str
    messages: list[AIMessage]
    temperature: float = 0.2
    max_tokens: int = 160
    timeout_seconds: int = 45


@dataclass
class AIChatResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(Protocol):
    provider_id: str

    async def send_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AIChatResponse:
        ...

    async def stream_message(
        self,
        request: AIChatRequest,
        credential: dict[str, Any],
    ) -> AsyncIterator[str]:
        ...

    async def list_models(self, config: dict[str, Any], credential: dict[str, Any]) -> list[dict[str, Any]]:
        ...

    async def test_connection(self, config: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        ...

    def get_capabilities(self) -> dict[str, bool]:
        ...


class SecretBox:
    def __init__(self, secret: str) -> None:
        if not secret:
            if settings.app_environment in ("production", "staging"):
                raise RuntimeError("CREDENTIAL_ENCRYPTION_SECRET must be set in production/staging.")
            secret = "local-development-secret"
        self.secret = secret
        digest = hashlib.sha256(self.secret.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")


def redact_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"{value[:3]}••••{value[-4:]}"


class AIProviderStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secrets = SecretBox(settings.credential_encryption_secret)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_provider_connections (
                    property_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'not_configured',
                    auth_method TEXT NOT NULL DEFAULT 'api_key',
                    selected_model TEXT NOT NULL DEFAULT '',
                    endpoint_url TEXT NOT NULL DEFAULT '',
                    temperature REAL NOT NULL DEFAULT 0.2,
                    max_output_tokens INTEGER NOT NULL DEFAULT 160,
                    timeout_seconds INTEGER NOT NULL DEFAULT 45,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    last_test_json TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (property_id, provider_id)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_credentials (
                    property_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    credential_type TEXT NOT NULL,
                    encrypted_value TEXT NOT NULL,
                    display_hint TEXT NOT NULL DEFAULT '',
                    expires_at INTEGER,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (property_id, provider_id, credential_type)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS property_ai_settings (
                    property_id TEXT PRIMARY KEY,
                    organization_default_provider TEXT NOT NULL DEFAULT 'local',
                    default_provider TEXT NOT NULL DEFAULT 'local',
                    routing_mode TEXT NOT NULL DEFAULT 'fixed',
                    local_only INTEGER NOT NULL DEFAULT 0,
                    fallback_chain_json TEXT NOT NULL DEFAULT '[]',
                    limits_json TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    latency_ms INTEGER,
                    success INTEGER NOT NULL,
                    error_type TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    provider_id TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT 'local-admin',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                )
                """
            )

    def get_settings(self, property_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM property_ai_settings WHERE property_id = ?", (property_id,)).fetchone()
        if not row:
            now = int(time.time())
            with self._connect() as db:
                db.execute(
                    """
                    INSERT INTO property_ai_settings
                    (property_id, organization_default_provider, default_provider, routing_mode, local_only, fallback_chain_json, limits_json, updated_at)
                    VALUES (?, 'local', 'local', 'fixed', 0, '[]', '{}', ?)
                    """,
                    (property_id, now),
                )
            return self.get_settings(property_id)
        return {
            "property_id": row["property_id"],
            "organization_default_provider": row["organization_default_provider"],
            "default_provider": row["default_provider"],
            "routing_mode": row["routing_mode"],
            "local_only": bool(row["local_only"]),
            "fallback_chain": json.loads(row["fallback_chain_json"]),
            "limits": json.loads(row["limits_json"]),
            "updated_at": row["updated_at"],
        }

    def save_settings(self, property_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_settings(property_id)
        default_provider = str(payload.get("default_provider") or current["default_provider"]).strip().lower()
        if default_provider not in PROVIDER_DEFINITIONS:
            raise ValueError("Unsupported provider.")
        local_only = bool(payload.get("local_only", current["local_only"]))
        if local_only and PROVIDER_DEFINITIONS[default_provider]["cloud"]:
            raise ValueError("Local-only mode cannot use a cloud provider.")
        routing_mode = str(payload.get("routing_mode") or current["routing_mode"]).strip().lower()
        if routing_mode not in {"fixed", "automatic", "privacy_first", "cloud_first"}:
            raise ValueError("Unsupported routing mode.")
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO property_ai_settings
                (property_id, organization_default_provider, default_provider, routing_mode, local_only, fallback_chain_json, limits_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(property_id) DO UPDATE SET
                    organization_default_provider = excluded.organization_default_provider,
                    default_provider = excluded.default_provider,
                    routing_mode = excluded.routing_mode,
                    local_only = excluded.local_only,
                    fallback_chain_json = excluded.fallback_chain_json,
                    limits_json = excluded.limits_json,
                    updated_at = excluded.updated_at
                """,
                (
                    property_id,
                    str(payload.get("organization_default_provider") or current["organization_default_provider"]),
                    default_provider,
                    routing_mode,
                    1 if local_only else 0,
                    json.dumps(payload.get("fallback_chain", current["fallback_chain"]), separators=(",", ":")),
                    json.dumps(payload.get("limits", current["limits"]), separators=(",", ":")),
                    now,
                ),
            )
        self.audit(property_id, "ai_settings_updated", default_provider, {"routing_mode": routing_mode, "local_only": local_only})
        return self.get_settings(property_id)

    def list_connections(self, property_id: str) -> list[dict[str, Any]]:
        settings_payload = self.get_settings(property_id)
        with self._connect() as db:
            rows = {
                row["provider_id"]: row
                for row in db.execute(
                    "SELECT * FROM ai_provider_connections WHERE property_id = ?",
                    (property_id,),
                ).fetchall()
            }
            credential_rows = db.execute(
                "SELECT provider_id, credential_type, display_hint, expires_at FROM provider_credentials WHERE property_id = ?",
                (property_id,),
            ).fetchall()
        credentials: dict[str, list[dict[str, Any]]] = {}
        for row in credential_rows:
            credentials.setdefault(row["provider_id"], []).append(
                {
                    "type": row["credential_type"],
                    "display_hint": row["display_hint"],
                    "expires_at": row["expires_at"],
                }
            )

        output = []
        for provider_id, definition in PROVIDER_DEFINITIONS.items():
            row = rows.get(provider_id)
            config = json.loads(row["config_json"]) if row else {}
            connection = {
                "provider_id": provider_id,
                "name": definition["name"],
                "auth_methods": definition["auth_methods"],
                "auth_method": row["auth_method"] if row else definition["default_auth_method"],
                "status": row["status"] if row else ("local" if provider_id == "local" else "not_configured"),
                "enabled": bool(row["enabled"]) if row else provider_id == settings_payload["default_provider"],
                "selected_model": row["selected_model"] if row and row["selected_model"] else definition["default_model"],
                "model_catalog": definition.get("model_catalog", []),
                "endpoint_url": row["endpoint_url"] if row else ("http://host.docker.internal:11434" if provider_id == "local" else ""),
                "temperature": row["temperature"] if row else 0.2,
                "max_output_tokens": row["max_output_tokens"] if row else settings.max_output_tokens,
                "timeout_seconds": row["timeout_seconds"] if row else settings.ollama_timeout_seconds,
                "credentials": credentials.get(provider_id, []),
                "last_test": json.loads(row["last_test_json"]) if row else {},
                "capabilities": capability_defaults(provider_id),
                "cloud": definition["cloud"],
                "unavailable": bool(definition.get("unavailable")),
                "status_note": definition["status_note"],
                "config": sanitize_config(config),
            }
            output.append(connection)
        return output

    def get_connection(self, property_id: str, provider_id: str) -> dict[str, Any]:
        return next(item for item in self.list_connections(property_id) if item["provider_id"] == provider_id)

    def save_connection(self, property_id: str, provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if provider_id not in PROVIDER_DEFINITIONS:
            raise ValueError("Unsupported provider.")
        definition = PROVIDER_DEFINITIONS[provider_id]
        auth_method = str(payload.get("auth_method") or definition["default_auth_method"]).strip()
        if auth_method not in definition["auth_methods"]:
            raise ValueError("Unsupported authentication method.")
        selected_model = str(payload.get("selected_model") or definition["default_model"]).strip()
        endpoint_url = str(payload.get("endpoint_url") or "").strip().rstrip("/")
        if provider_id == "local" and not endpoint_url:
            endpoint_url = settings.ollama_base_url
        enabled = bool(payload.get("enabled", False))
        if definition.get("unavailable"):
            enabled = False
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO ai_provider_connections
                (property_id, provider_id, enabled, status, auth_method, selected_model, endpoint_url,
                 temperature, max_output_tokens, timeout_seconds, config_json, last_test_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
                ON CONFLICT(property_id, provider_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    auth_method = excluded.auth_method,
                    selected_model = excluded.selected_model,
                    endpoint_url = excluded.endpoint_url,
                    temperature = excluded.temperature,
                    max_output_tokens = excluded.max_output_tokens,
                    timeout_seconds = excluded.timeout_seconds,
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
                """,
                (
                    property_id,
                    provider_id,
                    1 if enabled else 0,
                    "disabled" if not enabled else ("local" if provider_id == "local" else "not_configured"),
                    auth_method,
                    selected_model,
                    endpoint_url,
                    float(payload.get("temperature", 0.2)),
                    int(payload.get("max_output_tokens", settings.max_output_tokens)),
                    int(payload.get("timeout_seconds", 45)),
                    json.dumps(config, separators=(",", ":")),
                    now,
                ),
            )
        self.audit(property_id, "provider_configuration_saved", provider_id, {"model": selected_model, "enabled": enabled})
        return self.get_connection(property_id, provider_id)

    def save_credential(self, property_id: str, provider_id: str, credential_type: str, value: str) -> None:
        encrypted = self.secrets.encrypt(value)
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO provider_credentials
                (property_id, provider_id, credential_type, encrypted_value, display_hint, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(property_id, provider_id, credential_type) DO UPDATE SET
                    encrypted_value = excluded.encrypted_value,
                    display_hint = excluded.display_hint,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (property_id, provider_id, credential_type, encrypted, redact_secret(value), now),
            )
        self.audit(property_id, "credential_saved", provider_id, {"credential_type": credential_type})

    def remove_credential(self, property_id: str, provider_id: str, credential_type: str) -> None:
        with self._connect() as db:
            db.execute(
                "DELETE FROM provider_credentials WHERE property_id = ? AND provider_id = ? AND credential_type = ?",
                (property_id, provider_id, credential_type),
            )
        self.audit(property_id, "credential_removed", provider_id, {"credential_type": credential_type})

    def credentials_for(self, property_id: str, provider_id: str) -> dict[str, Any]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT credential_type, encrypted_value FROM provider_credentials WHERE property_id = ? AND provider_id = ?",
                (property_id, provider_id),
            ).fetchall()
        return {row["credential_type"]: self.secrets.decrypt(row["encrypted_value"]) for row in rows}

    def save_test_result(self, property_id: str, provider_id: str, result: dict[str, Any]) -> None:
        status = "connected" if result.get("ok") else "connection_failed"
        if result.get("auth_expired"):
            status = "authentication_expired"
        with self._connect() as db:
            db.execute(
                """
                UPDATE ai_provider_connections
                SET status = ?, last_test_json = ?, updated_at = ?
                WHERE property_id = ? AND provider_id = ?
                """,
                (status, json.dumps(result, separators=(",", ":")), int(time.time()), property_id, provider_id),
            )

    def audit(self, property_id: str, action: str, provider_id: str = "", metadata: dict[str, Any] | None = None) -> None:
        clean = sanitize_config(metadata or {})
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO ai_audit_logs (property_id, action, provider_id, actor, metadata_json, created_at)
                VALUES (?, ?, ?, 'local-admin', ?, ?)
                """,
                (property_id, action, provider_id, json.dumps(clean, separators=(",", ":")), int(time.time())),
            )

    def record_usage(
        self,
        property_id: str,
        provider_id: str,
        model: str,
        latency_ms: int,
        success: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error_type: str = "",
    ) -> None:
        total = None if input_tokens is None and output_tokens is None else (input_tokens or 0) + (output_tokens or 0)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO ai_usage
                (property_id, provider_id, model, input_tokens, output_tokens, total_tokens, latency_ms, success, error_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (property_id, provider_id, model, input_tokens, output_tokens, total, latency_ms, 1 if success else 0, error_type, int(time.time())),
            )


def sanitize_config(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("key", "secret", "token", "password")):
                clean[key] = "redacted"
            else:
                clean[key] = sanitize_config(item)
        return clean
    if isinstance(value, list):
        return [sanitize_config(item) for item in value]
    return value


def capability_defaults(provider_id: str) -> dict[str, bool]:
    return {
        "streaming": provider_id != "copilot",
        "tools": provider_id in {"openai", "openrouter", "gemini", "claude", "groq", "local"},
        "vision": provider_id in {"openai", "openrouter", "gemini", "claude", "local"},
    }


def split_messages(messages: list[AIMessage]) -> tuple[str, str]:
    system = "\n".join(message.content for message in messages if message.role == "system").strip()
    user_parts = [message.content for message in messages if message.role != "system"]
    return system, "\n\n".join(user_parts).strip()


class OpenAICompatibleProvider:
    provider_id = "openai"

    def __init__(self, provider_id: str, base_url: str, api_key_name: str = "api_key") -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key_name = api_key_name

    async def send_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AIChatResponse:
        api_key = credential.get(self.api_key_name) or credential.get("api_key") or ""
        if self.provider_id != "local" and not api_key:
            raise RuntimeError("Authentication failed. Add or replace the provider credential.")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": request.model,
            "messages": [message.__dict__ for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        answer = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = body.get("usage", {})
        return AIChatResponse(str(answer).strip(), self.provider_id, request.model, usage.get("prompt_tokens"), usage.get("completion_tokens"))

    async def stream_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AsyncIterator[str]:
        response = await self.send_message(request, credential)
        yield response.text

    async def list_models(self, config: dict[str, Any], credential: dict[str, Any]) -> list[dict[str, Any]]:
        api_key = credential.get(self.api_key_name) or credential.get("api_key") or ""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/v1/models", headers=headers)
            response.raise_for_status()
            body = response.json()
        models = body.get("data", [])
        return [{"id": item.get("id"), "name": item.get("id"), "owned_by": item.get("owned_by", "")} for item in models if item.get("id")]

    async def test_connection(self, config: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        models = await self.list_models(config, credential)
        return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000), "models_detected": len(models)}

    def get_capabilities(self) -> dict[str, bool]:
        return capability_defaults(self.provider_id)


class GeminiProviderAdapter:
    provider_id = "gemini"

    async def send_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AIChatResponse:
        api_key = credential.get("api_key")
        access_token = credential.get("oauth_access_token")
        if not api_key and not access_token:
            raise RuntimeError("Authentication failed. Connect Google or add a Gemini API key.")
        system, prompt = split_messages(request.messages)
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_tokens},
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent"
        if api_key:
            url = f"{url}?key={api_key}"
        else:
            headers["Authorization"] = f"Bearer {access_token}"
        async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        answer = "".join(part.get("text", "") for part in parts).strip()
        usage = body.get("usageMetadata", {})
        return AIChatResponse(answer, "gemini", request.model, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))

    async def stream_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AsyncIterator[str]:
        response = await self.send_message(request, credential)
        yield response.text

    async def list_models(self, config: dict[str, Any], credential: dict[str, Any]) -> list[dict[str, Any]]:
        api_key = credential.get("api_key")
        access_token = credential.get("oauth_access_token")
        if not api_key and not access_token:
            return []
        headers: dict[str, str] = {}
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        if api_key:
            url = f"{url}?key={api_key}"
        else:
            headers["Authorization"] = f"Bearer {access_token}"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            body = response.json()
        return [
            {"id": item.get("name", "").replace("models/", ""), "name": item.get("displayName") or item.get("name")}
            for item in body.get("models", [])
            if "generateContent" in item.get("supportedGenerationMethods", [])
        ]

    async def test_connection(self, config: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        models = await self.list_models(config, credential)
        return {"ok": True, "latency_ms": int((time.perf_counter() - started) * 1000), "models_detected": len(models)}

    def get_capabilities(self) -> dict[str, bool]:
        return capability_defaults("gemini")


class ClaudeProviderAdapter:
    provider_id = "claude"

    async def send_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AIChatResponse:
        api_key = credential.get("api_key")
        if not api_key:
            raise RuntimeError("Authentication failed. Add or replace the Anthropic credential.")
        system, prompt = split_messages(request.messages)
        payload = {
            "model": request.model,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        answer = "".join(item.get("text", "") for item in body.get("content", []) if item.get("type") == "text").strip()
        usage = body.get("usage", {})
        return AIChatResponse(answer, "claude", request.model, usage.get("input_tokens"), usage.get("output_tokens"))

    async def stream_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AsyncIterator[str]:
        response = await self.send_message(request, credential)
        yield response.text

    async def list_models(self, config: dict[str, Any], credential: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5"},
            {"id": "claude-opus-4-1", "name": "Claude Opus 4.1"},
        ]

    async def test_connection(self, config: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        if not credential.get("api_key"):
            raise RuntimeError("Authentication failed. Add or replace the Anthropic credential.")
        return {"ok": True, "latency_ms": 0, "models_detected": 2}

    def get_capabilities(self) -> dict[str, bool]:
        return capability_defaults("claude")


class LocalProviderAdapter(OpenAICompatibleProvider):
    provider_id = "local"

    def __init__(self, base_url: str) -> None:
        super().__init__("local", base_url)

    async def list_models(self, config: dict[str, Any], credential: dict[str, Any]) -> list[dict[str, Any]]:
        engine = config.get("engine", "ollama")
        async with httpx.AsyncClient(timeout=8) as client:
            if engine == "ollama":
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                body = response.json()
                return [{"id": item.get("name"), "name": item.get("name")} for item in body.get("models", []) if item.get("name")]
            return await super().list_models(config, credential)


class UnavailableProviderAdapter:
    provider_id = "copilot"

    async def send_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AIChatResponse:
        raise RuntimeError("GitHub Copilot is unavailable as a general backend AI provider until an eligible official integration is configured.")

    async def stream_message(self, request: AIChatRequest, credential: dict[str, Any]) -> AsyncIterator[str]:
        raise RuntimeError("GitHub Copilot integration is unavailable.")
        yield ""

    async def list_models(self, config: dict[str, Any], credential: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    async def test_connection(self, config: dict[str, Any], credential: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "Requires eligible GitHub Copilot SDK/API integration."}

    def get_capabilities(self) -> dict[str, bool]:
        return capability_defaults("copilot")


class AIModelService:
    def __init__(self, store: AIProviderStore) -> None:
        self.store = store

    def adapter_for(self, provider_id: str, endpoint_url: str = "") -> AIProvider:
        if provider_id == "gemini":
            return GeminiProviderAdapter()
        if provider_id == "groq":
            return OpenAICompatibleProvider("groq", "https://api.groq.com/openai")
        if provider_id == "openai":
            return OpenAICompatibleProvider("openai", "https://api.openai.com")
        if provider_id == "openrouter":
            return OpenAICompatibleProvider("openrouter", "https://openrouter.ai/api")
        if provider_id == "claude":
            return ClaudeProviderAdapter()
        if provider_id == "local":
            return LocalProviderAdapter((endpoint_url or settings.ollama_base_url).rstrip("/"))
        return UnavailableProviderAdapter()

    def resolve_connection(self, property_id: str) -> dict[str, Any]:
        ai_settings = self.store.get_settings(property_id)
        provider_id = ai_settings["default_provider"]
        if ai_settings["local_only"] and PROVIDER_DEFINITIONS[provider_id]["cloud"]:
            provider_id = "local"
        connection = self.store.get_connection(property_id, provider_id)
        return connection

    async def concierge_chat(
        self,
        property_id: str,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
        live_context: str = "",
        requested_mode: str = "auto",
    ) -> AIChatResponse:
        connection = self.resolve_connection(property_id)
        provider_id = connection["provider_id"]
        ai_settings = self.store.get_settings(property_id)
        if ai_settings["local_only"] and PROVIDER_DEFINITIONS[provider_id]["cloud"]:
            raise RuntimeError("Local-only mode is enabled. Cloud AI providers cannot be used.")
        model = connection["selected_model"] or PROVIDER_DEFINITIONS[provider_id]["default_model"]
        system, prompt = build_prompt(user_message, hotel_name, context, live_context)
        request = AIChatRequest(
            property_id=property_id,
            provider_id=provider_id,
            model=model,
            messages=[AIMessage("system", system), AIMessage("user", prompt)],
            temperature=float(connection["temperature"]),
            max_tokens=int(connection["max_output_tokens"]),
            timeout_seconds=int(connection["timeout_seconds"]),
        )
        adapter = self.adapter_for(provider_id, connection["endpoint_url"])
        credential = self.store.credentials_for(property_id, provider_id)
        started = time.perf_counter()
        try:
            response = await adapter.send_message(request, credential)
        except Exception as exc:
            self.store.record_usage(property_id, provider_id, model, int((time.perf_counter() - started) * 1000), False, error_type=exc.__class__.__name__)
            raise
        self.store.record_usage(
            property_id,
            provider_id,
            model,
            int((time.perf_counter() - started) * 1000),
            True,
            response.input_tokens,
            response.output_tokens,
        )
        return response

    async def list_models(self, property_id: str, provider_id: str) -> list[dict[str, Any]]:
        connection = self.store.get_connection(property_id, provider_id)
        credential = self.store.credentials_for(property_id, provider_id)
        adapter = self.adapter_for(provider_id, connection["endpoint_url"])
        return await adapter.list_models(connection.get("config", {}), credential)

    async def test_connection(self, property_id: str, provider_id: str) -> dict[str, Any]:
        connection = self.store.get_connection(property_id, provider_id)
        credential = self.store.credentials_for(property_id, provider_id)
        adapter = self.adapter_for(provider_id, connection["endpoint_url"])
        try:
            result = await adapter.test_connection(connection.get("config", {}), credential)
            result = {"ok": bool(result.get("ok")), "provider": provider_id, "model": connection["selected_model"], **result}
        except httpx.HTTPStatusError as exc:
            result = {"ok": False, "provider": provider_id, "error": friendly_http_error(exc.response.status_code)}
        except Exception as exc:
            result = {"ok": False, "provider": provider_id, "error": friendly_error(provider_id, exc)}
        self.store.save_test_result(property_id, provider_id, result)
        return result

    def validate_direct_connection(self, property_id: str, provider_id: str, model: str) -> None:
        if provider_id not in PROVIDER_DEFINITIONS:
            raise ValueError(f"Unknown AI provider '{provider_id}'.")
        if PROVIDER_DEFINITIONS[provider_id].get("unavailable"):
            raise ValueError(f"Provider '{provider_id}' is unavailable.")
        connection = self.store.get_connection(property_id, provider_id)
        if not connection.get("enabled"):
            raise RuntimeError(f"Enable {connection['name']} before using it in the improvement loop.")
        ai_settings = self.store.get_settings(property_id)
        if ai_settings.get("local_only") and PROVIDER_DEFINITIONS[provider_id].get("cloud"):
            raise RuntimeError("Local-only mode is enabled. Cloud AI providers cannot be used.")
        if not model or not model.strip():
            raise ValueError("A model must be specified.")

    async def direct_chat(
        self,
        property_id: str,
        provider_id: str,
        model: str,
        messages: list[AIMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: int | None = None,
    ) -> AIChatResponse:
        self.validate_direct_connection(property_id, provider_id, model)
        connection = self.store.get_connection(property_id, provider_id)
        temp = float(connection["temperature"]) if temperature is None else float(temperature)
        tokens = int(connection["max_output_tokens"]) if max_tokens is None else int(max_tokens)
        timeout = int(connection["timeout_seconds"]) if timeout_seconds is None else int(timeout_seconds)

        request = AIChatRequest(
            property_id=property_id,
            provider_id=provider_id,
            model=model,
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            timeout_seconds=timeout,
        )
        adapter = self.adapter_for(provider_id, connection.get("endpoint_url", ""))
        credential = self.store.credentials_for(property_id, provider_id)
        started = time.perf_counter()
        try:
            response = await adapter.send_message(request, credential)
        except Exception as exc:
            self.store.record_usage(
                property_id,
                provider_id,
                model,
                int((time.perf_counter() - started) * 1000),
                False,
                error_type=exc.__class__.__name__,
            )
            raise
        self.store.record_usage(
            property_id,
            provider_id,
            model,
            int((time.perf_counter() - started) * 1000),
            True,
            response.input_tokens,
            response.output_tokens,
        )
        return response


def friendly_http_error(status_code: int) -> str:
    if status_code in {401, 403}:
        return "Authentication failed. Reconnect the provider or update the credential."
    if status_code == 404:
        return "The provider endpoint or model was not found."
    return f"Provider request failed with status {status_code}."


def friendly_error(provider_id: str, exc: Exception) -> str:
    text = str(exc)
    if provider_id == "local" and ("ConnectError" in exc.__class__.__name__ or "ECONNREFUSED" in text):
        return "Unable to reach the Local AI server. Verify that Ollama/LM Studio is running and reachable from Concierge.Ai."
    if "Authentication failed" in text:
        return text
    return "Connection failed. Check the provider configuration and server logs."
