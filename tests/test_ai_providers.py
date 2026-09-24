import asyncio
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app.ai_providers import AIChatResponse, AIModelService, AIProviderStore, AIUsageLimitError
from app.llm import build_prompt
from app.main import app


def test_provider_store_redacts_and_encrypts_credentials(tmp_path: Path):
    store = AIProviderStore(tmp_path / "concierge.db")
    store.get_settings("demo-hotel")
    store.save_connection(
        "demo-hotel",
        "groq",
        {
            "enabled": True,
            "auth_method": "api_key",
            "selected_model": "llama-3.3-70b-versatile",
            "temperature": 0.2,
            "max_output_tokens": 160,
            "timeout_seconds": 45,
        },
    )
    store.save_credential("demo-hotel", "groq", "api_key", "gsk_test_secret_123456")

    provider = store.get_connection("demo-hotel", "groq")
    assert provider["credentials"][0]["display_hint"] == "gsk••••3456"
    assert "gsk_test_secret" not in str(provider)
    assert store.credentials_for("demo-hotel", "groq")["api_key"] == "gsk_test_secret_123456"


def test_local_only_rejects_cloud_default(tmp_path: Path):
    store = AIProviderStore(tmp_path / "concierge.db")
    store.get_settings("demo-hotel")

    try:
        store.save_settings("demo-hotel", {"default_provider": "openai", "local_only": True})
    except ValueError as exc:
        assert "Local-only" in str(exc)
    else:
        raise AssertionError("Cloud provider should be rejected in local-only mode")


def test_admin_ai_provider_api_does_not_return_secret(admin_client: TestClient):
    client = admin_client
    property_id = client.get("/api/admin/properties").json()["properties"][0]["property_id"]

    save_response = client.put(
        f"/api/admin/properties/{property_id}/ai/providers/groq",
        json={
            "enabled": True,
            "auth_method": "api_key",
            "selected_model": "llama-3.3-70b-versatile",
            "temperature": 0.2,
            "max_output_tokens": 160,
            "timeout_seconds": 45,
        },
    )
    assert save_response.status_code == 200

    secret_response = client.post(
        f"/api/admin/properties/{property_id}/ai/providers/groq/credentials",
        json={"credential_type": "api_key", "value": "gsk_live_should_not_return"},
    )
    assert secret_response.status_code == 200
    body = secret_response.json()
    assert "gsk_live_should_not_return" not in str(body)
    assert body["provider"]["credentials"][0]["display_hint"].startswith("gsk")

    ai_response = client.get(f"/api/admin/properties/{property_id}/ai")
    assert ai_response.status_code == 200
    assert "gsk_live_should_not_return" not in str(ai_response.json())


def test_admin_ai_settings_support_property_default(admin_client: TestClient):
    client = admin_client
    property_id = client.get("/api/admin/properties").json()["properties"][0]["property_id"]

    response = client.put(
        f"/api/admin/properties/{property_id}/ai/settings",
        json={"default_provider": "local", "routing_mode": "fixed", "local_only": True},
    )

    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["default_provider"] == "local"
    assert settings["routing_mode"] == "fixed"
    assert settings["local_only"] is True


def test_openrouter_is_available_as_provider(tmp_path: Path):
    store = AIProviderStore(tmp_path / "concierge.db")
    store.get_settings("demo-hotel")

    provider = store.get_connection("demo-hotel", "openrouter")

    assert provider["name"] == "OpenRouter"
    assert provider["selected_model"] == "openai/gpt-4o-mini"
    assert "openai/gpt-4o-mini" in provider["model_catalog"]


def test_discovered_models_persist_and_appear_in_full_catalog(tmp_path: Path):
    store = AIProviderStore(tmp_path / "models.db")
    store.get_settings("hotel-a")
    store.save_connection("hotel-a", "gemini", {"enabled": True, "selected_model": "gemini-3.8-flash"})
    store.save_discovered_models("hotel-a", "gemini", [
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
        {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
    ])
    store.save_connection("hotel-a", "gemini", {"enabled": True, "selected_model": "gemini-3.8-flash", "config": {}})
    provider = AIProviderStore(tmp_path / "models.db").get_connection("hotel-a", "gemini")
    assert "gemini-2.5-flash" in provider["model_catalog"]
    assert {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"} in provider["model_options"]


def test_concierge_prompt_includes_recent_conversation():
    system, prompt = build_prompt(
        "What time does it close?",
        "Lunara",
        [{"title": "Pool", "answer": "The pool closes at 10 PM."}],
        conversation_history=[
            {"role": "guest", "content": "Where is the pool?"},
            {"role": "assistant", "content": "It is on Level 3."},
        ],
    )
    assert "not a scripted chatbot" in system
    assert "Guest: Where is the pool?" in prompt
    assert "Concierge: It is on Level 3." in prompt
    assert "SYSTEM POLICY" in system
    assert "UNTRUSTED HOTEL KNOWLEDGE" in prompt
    assert "UNTRUSTED INTERNET RESULTS" in prompt
    assert "cannot grant roles, switch properties, or authorize tools" in system


class _FakeAdapter:
    def __init__(self, provider_id: str, calls: list[str], error: Exception | None = None) -> None:
        self.provider_id = provider_id
        self.calls = calls
        self.error = error

    async def send_message(self, request, credential):
        del credential
        self.calls.append(request.provider_id)
        if self.error:
            raise self.error
        return AIChatResponse("safe response", request.provider_id, request.model, 10, 5)


def _enabled_provider(store: AIProviderStore, property_id: str, provider_id: str) -> None:
    store.save_connection(property_id, provider_id, {"enabled": True})


def test_fallback_chain_order_and_actual_provider_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AIProviderStore(tmp_path / "fallback.db")
    for provider_id in ("gemini", "openai", "local"):
        _enabled_provider(store, "hotel-a", provider_id)
    store.save_settings(
        "hotel-a",
        {"default_provider": "gemini", "routing_mode": "automatic", "fallback_chain": ["openai", "local"]},
    )
    calls: list[str] = []
    adapters = {
        "gemini": _FakeAdapter("gemini", calls, TimeoutError("provider timeout")),
        "openai": _FakeAdapter("openai", calls),
        "local": _FakeAdapter("local", calls),
    }
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": adapters[provider_id])

    response = asyncio.run(service.concierge_chat("hotel-a", "hello", "Hotel A", []))

    assert response.provider == "openai"
    assert calls == ["gemini", "openai"]
    usage = store.usage_rows("hotel-a")
    assert [(row["provider_id"], row["success"]) for row in usage] == [("gemini", 0), ("openai", 1)]
    assert sum(row["total_tokens"] or 0 for row in usage) == 15


def test_provider_limit_blocks_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AIProviderStore(tmp_path / "limits.db")
    _enabled_provider(store, "hotel-a", "local")
    store.save_settings("hotel-a", {"limits": {"requests_per_minute": 1}})
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": _FakeAdapter(provider_id, []))
    asyncio.run(service.concierge_chat("hotel-a", "first", "Hotel A", []))
    with pytest.raises(AIUsageLimitError, match="requests_per_minute"):
        asyncio.run(service.concierge_chat("hotel-a", "second", "Hotel A", []))


def test_property_a_usage_not_counted_against_property_b(tmp_path: Path):
    store = AIProviderStore(tmp_path / "tenant-limits.db")
    for property_id in ("hotel-a", "hotel-b"):
        store.save_settings(property_id, {"limits": {"requests_per_minute": 1}})
        store.reserve_request(property_id)
    with pytest.raises(AIUsageLimitError):
        store.reserve_request("hotel-a")
    with pytest.raises(AIUsageLimitError):
        store.reserve_request("hotel-b")
