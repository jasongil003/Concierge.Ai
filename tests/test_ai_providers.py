import asyncio
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from fastapi.testclient import TestClient

from app.ai_providers import (
    AIChatRequest,
    AIChatResponse,
    AIMessage,
    AIModelService,
    AIProviderStore,
    AIUsageLimitError,
    ClaudeProviderAdapter,
    GeminiProviderAdapter,
    OpenAICompatibleProvider,
    ProviderBulkheadFull,
    ProviderCircuitOpen,
    ProviderStreamInterrupted,
)
import app.ai_providers as ai_provider_module
from app.llm import build_prompt
from app.main import app
import app.main as main_module


def test_provider_store_redacts_and_encrypts_credentials(tmp_path: Path):
    store = AIProviderStore(tmp_path / "concierge.db")
    store.get_settings("tenant-a")
    store.save_connection(
        "tenant-a",
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
    synthetic_credential = "gsk" + ("x" * 16) + "3456"
    store.save_credential("tenant-a", "groq", "api_key", synthetic_credential)

    provider = store.get_connection("tenant-a", "groq")
    assert provider["credentials"][0]["display_hint"] == "gsk••••3456"
    assert "gsk_test_secret" not in str(provider)
    assert store.credentials_for("tenant-a", "groq")["api_key"] == synthetic_credential


def test_local_only_rejects_cloud_default(tmp_path: Path):
    store = AIProviderStore(tmp_path / "concierge.db")
    store.get_settings("tenant-a")

    try:
        store.save_settings("tenant-a", {"default_provider": "openai", "local_only": True})
    except ValueError as exc:
        assert "Local-only" in str(exc)
    else:
        raise AssertionError("Cloud provider should be rejected in local-only mode")


def test_guest_chat_does_not_escape_property_provider_chain_on_outage(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def unavailable_provider(**kwargs):
        raise RuntimeError("configured provider unavailable")

    monkeypatch.setattr(main_module.ai_models, "concierge_chat", unavailable_provider)
    started = admin_client.post("/api/session/start", json={"client_id": "provider-outage-guest"})
    assert started.status_code == 200, started.text

    response = admin_client.post(
        "/api/chat",
        json={"session_id": started.json()["session_id"], "message": "Where can I find a quiet reading spot?", "mode": "advanced"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "concierge_contact"
    assert payload["contact_concierge"] is True
    assert "configured provider unavailable" not in payload["answer"]


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


def test_gemini_model_refresh_error_does_not_return_or_log_api_key(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    property_id = "test-property"
    sentinel = "synthetic-gemini-model-refresh-key-7f31"
    main_module.ai_provider_store.save_credential(property_id, "gemini", "api_key", sentinel)

    class FailingGeminiAdapter:
        async def list_models(self, config, credential):
            del config
            assert credential["api_key"] == sentinel
            request = httpx.Request(
                "GET",
                f"https://generativelanguage.googleapis.com/v1beta/models?key={credential['api_key']}",
            )
            response = httpx.Response(403, request=request)
            response.raise_for_status()

    monkeypatch.setattr(
        main_module.ai_models,
        "adapter_for",
        lambda provider_id, endpoint_url="": FailingGeminiAdapter(),
    )

    response = admin_client.post(
        f"/api/admin/properties/{property_id}/ai/providers/gemini/models/refresh"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication failed. Reconnect the provider or update the credential."
    assert sentinel not in response.text
    assert sentinel not in caplog.text


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
    store.get_settings("tenant-a")

    provider = store.get_connection("tenant-a", "openrouter")

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
        "Example Hotel",
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
        self.requests: list[AIChatRequest] = []

    async def send_message(self, request, credential):
        del credential
        self.calls.append(request.provider_id)
        self.requests.append(request)
        if self.error:
            raise self.error
        return AIChatResponse("safe response", request.provider_id, request.model, 10, 5)


def _enabled_provider(store: AIProviderStore, property_id: str, provider_id: str) -> None:
    store.save_connection(property_id, provider_id, {"enabled": True})


def test_fallback_chain_order_and_actual_provider_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ai_provider_module, "settings", replace(ai_provider_module.settings, ai_provider_retry_attempts=1))
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
    assert calls == ["gemini", "gemini", "openai"]
    usage = store.usage_rows("hotel-a")
    assert [(row["provider_id"], row["success"]) for row in usage] == [("gemini", 0), ("openai", 1)]
    assert sum(row["total_tokens"] or 0 for row in usage) == 15


@pytest.mark.parametrize(
    ("routing_mode", "expected_providers"),
    [
        ("fixed", []),
        ("automatic", ["groq"]),
        ("privacy_first", ["groq"]),
        ("cloud_first", ["groq"]),
    ],
)
def test_disabled_candidates_are_filtered_before_routing(
    tmp_path: Path,
    routing_mode: str,
    expected_providers: list[str],
):
    store = AIProviderStore(tmp_path / f"disabled-{routing_mode}.db")
    store.save_connection("hotel-a", "openai", {"enabled": False})
    store.save_connection("hotel-a", "groq", {"enabled": True})
    store.save_connection("hotel-a", "local", {"enabled": False})
    store.save_settings(
        "hotel-a",
        {
            "default_provider": "openai",
            "routing_mode": routing_mode,
            "fallback_chain": ["groq", "local"],
        },
    )

    service = AIModelService(store)
    connections = service.resolve_connections("hotel-a")
    selected = service.resolve_connection("hotel-a")

    assert [item["provider_id"] for item in connections] == expected_providers
    assert all(item["enabled"] for item in connections)
    assert (selected["provider_id"] if selected else None) == (expected_providers[0] if expected_providers else None)


@pytest.mark.parametrize(
    ("routing_mode", "expected_provider"),
    [
        ("fixed", None),
        ("automatic", "groq"),
        ("privacy_first", "groq"),
        ("cloud_first", "groq"),
    ],
)
def test_disabled_default_and_later_candidates_never_receive_guest_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    routing_mode: str,
    expected_provider: str | None,
):
    store = AIProviderStore(tmp_path / f"disabled-adapters-{routing_mode}.db")
    store.save_connection("hotel-a", "openai", {"enabled": False})
    store.save_connection("hotel-a", "groq", {"enabled": True})
    store.save_connection("hotel-a", "local", {"enabled": False})
    store.save_settings(
        "hotel-a",
        {
            "default_provider": "openai",
            "routing_mode": routing_mode,
            "fallback_chain": ["groq", "local"],
        },
    )
    adapters = {
        provider_id: _FakeAdapter(provider_id, [])
        for provider_id in ("openai", "groq", "local")
    }
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": adapters[provider_id])

    if expected_provider is None:
        with pytest.raises(RuntimeError, match="No enabled AI provider"):
            asyncio.run(
                service.concierge_chat(
                    "hotel-a",
                    "PROMPT-SENTINEL",
                    "Hotel A",
                    [{"answer": "KNOWLEDGE-SENTINEL"}],
                    live_context="LIVE-SENTINEL",
                    conversation_history=[{"role": "guest", "content": "HISTORY-SENTINEL"}],
                )
            )
    else:
        response = asyncio.run(
            service.concierge_chat(
                "hotel-a",
                "PROMPT-SENTINEL",
                "Hotel A",
                [{"answer": "KNOWLEDGE-SENTINEL"}],
                live_context="LIVE-SENTINEL",
                conversation_history=[{"role": "guest", "content": "HISTORY-SENTINEL"}],
            )
        )
        assert response.provider == expected_provider

    assert adapters["openai"].requests == []
    assert adapters["local"].requests == []
    assert len(adapters["groq"].requests) == (1 if expected_provider == "groq" else 0)


def test_disabled_fallback_later_in_chain_never_receives_fallback_traffic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AIProviderStore(tmp_path / "disabled-fallback.db")
    store.save_connection("hotel-a", "gemini", {"enabled": True})
    store.save_connection("hotel-a", "openai", {"enabled": False})
    store.save_connection("hotel-a", "groq", {"enabled": True})
    store.save_settings(
        "hotel-a",
        {"default_provider": "gemini", "routing_mode": "automatic", "fallback_chain": ["openai", "groq"]},
    )
    adapters = {
        "gemini": _FakeAdapter("gemini", [], TimeoutError("primary unavailable")),
        "openai": _FakeAdapter("openai", []),
        "groq": _FakeAdapter("groq", []),
    }
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": adapters[provider_id])
    monkeypatch.setattr(ai_provider_module, "settings", replace(ai_provider_module.settings, ai_provider_retry_attempts=0))

    response = asyncio.run(service.concierge_chat("hotel-a", "PROMPT-SENTINEL", "Hotel A", []))

    assert response.provider == "groq"
    assert len(adapters["gemini"].requests) == 1
    assert adapters["openai"].requests == []
    assert len(adapters["groq"].requests) == 1


def test_local_only_never_routes_to_configured_cloud_providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AIProviderStore(tmp_path / "strict-local-only.db")
    store.save_connection("hotel-a", "local", {"enabled": True})
    store.save_connection("hotel-a", "openai", {"enabled": True})
    store.save_connection("hotel-a", "gemini", {"enabled": True})
    store.save_settings(
        "hotel-a",
        {
            "default_provider": "local",
            "routing_mode": "automatic",
            "fallback_chain": ["openai", "gemini"],
            "local_only": True,
        },
    )
    adapters = {
        provider_id: _FakeAdapter(provider_id, [])
        for provider_id in ("local", "openai", "gemini")
    }
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": adapters[provider_id])

    response = asyncio.run(service.concierge_chat("hotel-a", "PROMPT-SENTINEL", "Hotel A", []))

    assert response.provider == "local"
    assert len(adapters["local"].requests) == 1
    assert adapters["openai"].requests == []
    assert adapters["gemini"].requests == []


def test_guest_external_processing_consent_filters_cloud_fallback_candidates(tmp_path: Path):
    store = AIProviderStore(tmp_path / "guest-consent-routing.db")
    store.save_connection("hotel-a", "groq", {"enabled": True})
    store.save_connection("hotel-a", "local", {"enabled": True})
    store.save_settings("hotel-a", {
        "default_provider": "groq",
        "routing_mode": "automatic",
        "fallback_chain": ["local"],
    })

    service = AIModelService(store)

    assert [item["provider_id"] for item in service.resolve_connections("hotel-a")] == ["groq", "local"]
    assert [item["provider_id"] for item in service.resolve_connections("hotel-a", allow_cloud=False)] == ["local"]


def test_guest_chat_passes_explicit_external_processing_consent_to_provider_router(admin_client, monkeypatch):
    calls = []

    class ModelResult:
        provider = "local"
        model = "synthetic-model"
        text = "A paper airplane crossed the moonlit room."

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return ModelResult()

    monkeypatch.setattr(main_module.ai_models, "concierge_chat", fake_chat)
    started = admin_client.post("/api/session/start", json={
        "client_id": "external-processing-consent-test", "property_id": "test-property",
    })
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    message = "Could you help me organize my thoughts?"

    private_response = admin_client.post("/api/chat", json={
        "session_id": session_id, "message": message, "mode": "advanced",
    })
    assert private_response.status_code == 200, private_response.text
    assert calls[-1]["allow_cloud"] is False

    granted = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"external_data_processing": True},
    })
    assert granted.status_code == 200, granted.text
    consented_response = admin_client.post("/api/chat", json={
        "session_id": session_id, "message": message, "mode": "advanced",
    })
    assert consented_response.status_code == 200, consented_response.text
    assert calls[-1]["allow_cloud"] is True


def test_all_disabled_providers_return_contact_fallback_without_adapter_calls(
    admin_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = AIProviderStore(tmp_path / "no-enabled-provider.db")
    for provider_id in ("openai", "gemini", "local"):
        store.save_connection("test-property", provider_id, {"enabled": False})
    store.save_settings(
        "test-property",
        {
            "default_provider": "openai",
            "routing_mode": "automatic",
            "fallback_chain": ["gemini", "local"],
        },
    )
    service = AIModelService(store)
    adapter_requests: list[AIChatRequest] = []

    class SpyAdapter:
        async def send_message(self, request, credential):
            del credential
            adapter_requests.append(request)
            return AIChatResponse("should not be called", request.provider_id, request.model)

    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": SpyAdapter())
    monkeypatch.setattr(main_module, "ai_models", service)
    started = admin_client.post("/api/session/start", json={"client_id": "all-ai-disabled-guest"})
    assert started.status_code == 200, started.text

    response = admin_client.post(
        "/api/chat",
        json={
            "session_id": started.json()["session_id"],
            "message": "Where can I find a quiet reading spot?",
            "mode": "advanced",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["source"] == "concierge_contact"
    assert response.json()["contact_concierge"] is True
    assert adapter_requests == []


def test_provider_routing_is_property_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AIProviderStore(tmp_path / "property-provider-isolation.db")
    store.save_connection("hotel-a", "openai", {"enabled": True})
    store.save_connection("hotel-a", "gemini", {"enabled": False})
    store.save_connection("hotel-b", "openai", {"enabled": False})
    store.save_connection("hotel-b", "gemini", {"enabled": True})
    store.save_settings("hotel-a", {"default_provider": "openai", "routing_mode": "fixed"})
    store.save_settings("hotel-b", {"default_provider": "gemini", "routing_mode": "fixed"})
    adapters = {
        provider_id: _FakeAdapter(provider_id, [])
        for provider_id in ("openai", "gemini")
    }
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": adapters[provider_id])

    response_a = asyncio.run(service.concierge_chat("hotel-a", "A-ONLY-PROMPT", "Hotel A", []))
    response_b = asyncio.run(service.concierge_chat("hotel-b", "B-ONLY-PROMPT", "Hotel B", []))

    assert response_a.provider == "openai"
    assert response_b.provider == "gemini"
    assert [item.property_id for item in adapters["openai"].requests] == ["hotel-a"]
    assert [item.property_id for item in adapters["gemini"].requests] == ["hotel-b"]
    assert "B-ONLY-PROMPT" not in str(adapters["openai"].requests)
    assert "A-ONLY-PROMPT" not in str(adapters["gemini"].requests)


def test_provider_bulkhead_limits_concurrency_and_bounds_waiters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = replace(
        ai_provider_module.settings,
        ai_provider_concurrency_limit=1,
        ai_provider_concurrency_limits={"local": 1},
        ai_provider_queue_capacity=1,
        ai_provider_queue_wait_seconds=0.5,
        ai_provider_retry_attempts=0,
    )
    monkeypatch.setattr(ai_provider_module, "settings", settings)
    service = AIModelService(AIProviderStore(tmp_path / "bulkhead.db"))
    wait_observations_before = ai_provider_module.metrics.REGISTRY.get_sample_value(
        "concierge_ai_provider_queue_wait_seconds_count", {"provider": "local"}
    ) or 0

    class SlowAdapter:
        async def send_message(self, _request, _credential):
            await asyncio.sleep(0.12)
            return AIChatResponse("ok", "local", "local", 1, 1)

    request = AIChatRequest("hotel-a", "local", "model", [AIMessage("user", "hello")], timeout_seconds=2)

    async def run():
        first = asyncio.create_task(service._send_with_resilience("local", SlowAdapter(), request, {}))
        await asyncio.sleep(0.005)
        second = asyncio.create_task(service._send_with_resilience("local", SlowAdapter(), request, {}))
        await asyncio.sleep(0.005)
        with pytest.raises(ProviderBulkheadFull):
            await service._send_with_resilience("local", SlowAdapter(), request, {})
        await asyncio.gather(first, second)

    asyncio.run(run())
    wait_observations_after = ai_provider_module.metrics.REGISTRY.get_sample_value(
        "concierge_ai_provider_queue_wait_seconds_count", {"provider": "local"}
    ) or 0
    assert wait_observations_after - wait_observations_before >= 3


def test_provider_circuit_opens_and_allows_one_recovery_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = replace(
        ai_provider_module.settings,
        ai_provider_retry_attempts=0,
        ai_provider_circuit_failures=2,
        ai_provider_circuit_cooldown_seconds=0.05,
    )
    monkeypatch.setattr(ai_provider_module, "settings", settings)
    service = AIModelService(AIProviderStore(tmp_path / "circuit.db"))
    calls = []
    bad = _FakeAdapter("local", calls, TimeoutError("provider timeout"))
    request = AIChatRequest("hotel-a", "local", "model", [AIMessage("user", "hello")], timeout_seconds=2)

    async def run():
        for _ in range(2):
            with pytest.raises(TimeoutError):
                await service._send_with_resilience("local", bad, request, {})
        with pytest.raises(ProviderCircuitOpen):
            await service._send_with_resilience("local", bad, request, {})
        await asyncio.sleep(0.06)
        healthy = _FakeAdapter("local", calls)
        response = await service._send_with_resilience("local", healthy, request, {})
        assert response.text == "safe response"

    asyncio.run(run())
    assert calls == ["local", "local", "local"]


def test_provider_limit_blocks_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AIProviderStore(tmp_path / "limits.db")
    _enabled_provider(store, "hotel-a", "local")
    store.save_settings("hotel-a", {"limits": {"requests_per_minute": 1}})
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": _FakeAdapter(provider_id, []))
    asyncio.run(service.concierge_chat("hotel-a", "first", "Hotel A", []))
    with pytest.raises(AIUsageLimitError, match="requests_per_minute"):
        asyncio.run(service.concierge_chat("hotel-a", "second", "Hotel A", []))


def test_local_ai_endpoint_must_be_explicitly_trusted_at_save_and_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ai_provider_module,
        "settings",
        replace(
            ai_provider_module.settings,
            ollama_base_url="http://ollama.hotel-lan.test:11434",
            local_ai_allowed_endpoints=("http://lmstudio.hotel-lan.test:1234",),
        ),
    )
    store = AIProviderStore(tmp_path / "local-endpoint-allowlist.db")
    allowed = store.save_connection(
        "hotel-a",
        "local",
        {"enabled": True, "endpoint_url": "http://lmstudio.hotel-lan.test:1234"},
    )
    assert allowed["endpoint_url"] == "http://lmstudio.hotel-lan.test:1234"
    with pytest.raises(ValueError, match="LOCAL_AI_ALLOWED_ENDPOINTS"):
        store.save_connection(
            "hotel-a",
            "local",
            {"enabled": True, "endpoint_url": "http://169.254.169.254/latest/meta-data"},
        )

    # Old or manually modified database rows are checked again before any provider request.
    with store._connect() as db:
        db.execute(
            "UPDATE ai_provider_connections SET endpoint_url=? WHERE property_id=? AND provider_id='local'",
            ("http://127.0.0.1:2375", "hotel-a"),
        )
    service = AIModelService(store)
    with pytest.raises(ValueError, match="LOCAL_AI_ALLOWED_ENDPOINTS"):
        service.adapter_for("local", store.get_connection("hotel-a", "local")["endpoint_url"])


def test_property_a_usage_not_counted_against_property_b(tmp_path: Path):
    store = AIProviderStore(tmp_path / "tenant-limits.db")
    for property_id in ("hotel-a", "hotel-b"):
        store.save_settings(property_id, {"limits": {"requests_per_minute": 1}})
        store.reserve_request(property_id)
    with pytest.raises(AIUsageLimitError):
        store.reserve_request("hotel-a")
    with pytest.raises(AIUsageLimitError):
        store.reserve_request("hotel-b")


@pytest.mark.parametrize(
    ("provider", "credential", "stream_body", "expected"),
    [
        (
            OpenAICompatibleProvider("openai", "https://provider.test"),
            {"api_key": "test-key"},
            'data: {"choices":[{"delta":{"content":"Hello "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
            "data: [DONE]\n\n",
            ["Hello ", "world"],
        ),
        (
            GeminiProviderAdapter(),
            {"api_key": "test-key"},
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello "}]}}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"world"}]}}]}\n\n',
            ["Hello ", "world"],
        ),
        (
            ClaudeProviderAdapter(),
            {"api_key": "test-key"},
            'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello "}}\n\n'
            'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}\n\n',
            ["Hello ", "world"],
        ),
    ],
)
def test_provider_adapters_parse_native_sse_deltas(
    monkeypatch: pytest.MonkeyPatch,
    provider,
    credential: dict,
    stream_body: str,
    expected: list[str],
):
    import httpx

    requests = []
    original_client = ai_provider_module.httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=stream_body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        ai_provider_module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(*args, transport=transport, **kwargs),
    )
    request = AIChatRequest(
        "hotel-a", provider.provider_id, "test-model", [AIMessage("user", "Hi")], timeout_seconds=3,
    )

    async def collect():
        return [chunk async for chunk in provider.stream_message(request, credential)]

    assert asyncio.run(collect()) == expected
    assert len(requests) == 1
    sent = __import__("json").loads(requests[0].content)
    if provider.provider_id == "openai":
        assert sent["stream"] is True
    elif provider.provider_id == "claude":
        assert sent["stream"] is True
    else:
        assert requests[0].url.path.endswith(":streamGenerateContent")


class _StreamingFakeAdapter(_FakeAdapter):
    def __init__(self, provider_id: str, calls: list[str], *, fail_before: bool = False, fail_after: bool = False):
        super().__init__(provider_id, calls)
        self.fail_before = fail_before
        self.fail_after = fail_after
        self.closed = False

    def get_capabilities(self):
        return {"streaming": True}

    async def stream_message(self, request, credential):
        del request, credential
        self.calls.append(self.provider_id)
        try:
            if self.fail_before:
                raise TimeoutError("provider timed out before first delta")
            yield "partial "
            if self.fail_after:
                raise TimeoutError("provider timed out after a delta")
            yield "complete"
        finally:
            self.closed = True


def test_provider_stream_falls_back_only_before_first_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ai_provider_module, "settings", replace(ai_provider_module.settings, ai_provider_retry_attempts=0))
    store = AIProviderStore(tmp_path / "stream-fallback.db")
    for provider_id in ("gemini", "openai"):
        _enabled_provider(store, "hotel-a", provider_id)
    store.save_settings("hotel-a", {
        "default_provider": "gemini", "routing_mode": "automatic", "fallback_chain": ["openai"],
    })
    calls: list[str] = []
    primary = _StreamingFakeAdapter("gemini", calls, fail_before=True)
    fallback = _FakeAdapter("openai", calls)
    service = AIModelService(store)
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": primary if provider_id == "gemini" else fallback)
    chunks = []

    async def on_delta(chunk):
        chunks.append(chunk)

    result = asyncio.run(service.concierge_chat_stream("hotel-a", "hello", "Hotel A", [], on_delta))
    assert result.streamed is False
    assert result.response.provider == "openai"
    assert chunks == []
    assert calls == ["gemini", "openai"]

    partial_calls: list[str] = []
    partial = _StreamingFakeAdapter("gemini", partial_calls)
    partial.fail_after = True
    calls.clear()
    monkeypatch.setattr(service, "adapter_for", lambda provider_id, endpoint_url="": partial if provider_id == "gemini" else fallback)
    with pytest.raises(ProviderStreamInterrupted):
        asyncio.run(service.concierge_chat_stream("hotel-a", "hello", "Hotel A", [], on_delta))
    assert chunks == ["partial "]
    assert partial_calls == ["gemini"]
    assert len(fallback.requests) == 1
    assert partial.closed is True


def test_concurrent_property_streams_keep_deltas_isolated(tmp_path: Path):
    store = AIProviderStore(tmp_path / "concurrent-property-streams.db")
    for property_id in ("hotel-a", "hotel-b"):
        _enabled_provider(store, property_id, "openai")
        store.save_settings(property_id, {"default_provider": "openai", "routing_mode": "fixed"})
    started: set[str] = set()
    both_started = asyncio.Event()

    class PropertyStreamingAdapter(_StreamingFakeAdapter):
        async def stream_message(self, request, credential):
            del credential
            property_id = request.property_id
            started.add(property_id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=2)
            try:
                yield f"{property_id}-first"
                await asyncio.sleep(0)
                yield f"{property_id}-last"
            finally:
                self.closed = True

    service = AIModelService(store)
    adapter = PropertyStreamingAdapter("openai", [])
    service.adapter_for = lambda provider_id, endpoint_url="": adapter

    async def run_property(property_id: str) -> list[str]:
        received: list[str] = []

        async def on_delta(chunk: str) -> None:
            received.append(chunk)

        result = await service.concierge_chat_stream(property_id, f"prompt-{property_id}", property_id, [], on_delta)
        assert result.response.provider == "openai"
        return received

    async def run() -> tuple[list[str], list[str]]:
        return tuple(await asyncio.gather(run_property("hotel-a"), run_property("hotel-b")))

    hotel_a, hotel_b = asyncio.run(run())
    assert hotel_a == ["hotel-a-first", "hotel-a-last"]
    assert hotel_b == ["hotel-b-first", "hotel-b-last"]
    assert started == {"hotel-a", "hotel-b"}
    assert adapter.closed is True


def test_provider_stream_cancellation_closes_provider_and_releases_slot(tmp_path: Path):
    store = AIProviderStore(tmp_path / "stream-cancel.db")
    _enabled_provider(store, "hotel-a", "openai")
    store.save_settings("hotel-a", {"default_provider": "openai", "routing_mode": "fixed"})
    started = asyncio.Event()
    closed = asyncio.Event()

    class CancellableAdapter(_FakeAdapter):
        def get_capabilities(self):
            return {"streaming": True}

        async def stream_message(self, request, credential):
            del request, credential
            try:
                yield "first"
                started.set()
                await asyncio.Event().wait()
            finally:
                closed.set()

    service = AIModelService(store)
    service.adapter_for = lambda provider_id, endpoint_url="": CancellableAdapter(provider_id, [])
    chunks = []
    available_before = service._slots_for("openai").semaphore._value

    async def run():
        async def on_delta(chunk):
            chunks.append(chunk)
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(service.concierge_chat_stream("hotel-a", "hello", "Hotel A", [], on_delta))
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return service._slots_for("openai").semaphore._value

    available = asyncio.run(run())
    assert chunks == ["first"]
    assert closed.is_set()
    assert available == available_before


def test_provider_stream_stops_at_intelligent_ui_text_protocol_limit(tmp_path: Path):
    store = AIProviderStore(tmp_path / "stream-limit.db")
    _enabled_provider(store, "hotel-a", "openai")
    store.save_settings("hotel-a", {"default_provider": "openai", "routing_mode": "fixed"})
    delivered: list[str] = []
    closed = False

    class OversizedAdapter(_FakeAdapter):
        def get_capabilities(self):
            return {"streaming": True}

        async def stream_message(self, request, credential):
            nonlocal closed
            del request, credential
            try:
                yield "a" * 5999
                yield "b" * 2
            finally:
                closed = True

    service = AIModelService(store)
    service.adapter_for = lambda provider_id, endpoint_url="": OversizedAdapter(provider_id, [])

    async def on_delta(chunk):
        delivered.append(chunk)

    with pytest.raises(ProviderStreamInterrupted):
        asyncio.run(service.concierge_chat_stream("hotel-a", "hello", "Hotel A", [], on_delta))

    assert sum(map(len, delivered)) == 5999
    assert closed is True
