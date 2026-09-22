from pathlib import Path

from fastapi.testclient import TestClient

from app.ai_providers import AIProviderStore
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
