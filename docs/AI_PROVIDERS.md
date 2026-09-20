# AI Provider and Model Management

Concierge.Ai now uses a provider-independent AI layer so each property can choose the engine that powers guest chat without changing the chat controller.

## Admin Experience

Go to `Settings > AI Models` in the admin platform. The page supports:

- organization/property AI defaults
- fixed routing mode for the MVP
- Local-Only Mode
- provider cards with connection status, auth method, selected model, endpoint, and credential hint
- provider configuration drawer
- server-side credential save/remove
- model refresh where the provider exposes a model list
- connection testing with customer-friendly errors

Guests do not choose providers. Guest chat resolves the provider from the session property.

## Supported Providers

| Provider | Current auth in Concierge.Ai | Notes |
| --- | --- | --- |
| Google Gemini | API key now; OAuth-ready credential architecture | Gemini has official OAuth documentation for approved workflows. Use OAuth only through Google’s documented consent and token flow. |
| Groq | API key | Stored server-side and sent only from backend requests. |
| OpenAI | API key | OpenAI API usage is separate from ChatGPT Plus/Pro consumer login. |
| Anthropic Claude | API key | Uses Anthropic’s documented Messages API authentication. |
| GitHub Copilot | Unavailable placeholder | Requires eligible official GitHub Copilot SDK/API integration and licensing. No unofficial implementation is provided. |
| Local AI | No cloud key | Supports Ollama now, with structure for LM Studio/OpenAI-compatible local endpoints. |

Do not scrape consumer AI websites, reuse browser cookies, extract session tokens, or automate consumer web sessions.

## Architecture

The app stores provider configuration in SQLite tables created at startup:

- `ai_provider_connections`
- `provider_credentials`
- `property_ai_settings`
- `ai_usage`
- `ai_audit_logs`

The provider abstraction lives in `app/ai_providers.py`:

- `AIProvider`
- `AIModelService`
- provider adapters for Gemini, Groq/OpenAI-compatible APIs, OpenAI, Claude, Copilot placeholder, and Local AI
- normalized `AIMessage`, `AIChatRequest`, and `AIChatResponse`

Guest chat calls `AIModelService.concierge_chat(...)`, which resolves:

```text
Session property
  -> property_ai_settings
  -> default provider
  -> provider connection
  -> credential lookup
  -> provider adapter
```

The existing hotel knowledge retrieval remains before model execution, so provider switching does not bypass RAG/context grounding.

## Local AI and Docker

For on-prem deployments, Local AI is first-class. If Concierge.Ai runs in Docker, `localhost` points at the container, not the host machine. Common endpoints:

```text
http://host.docker.internal:11434
http://192.168.1.20:11434
http://ollama.hotel-lan.local:11434
```

For Ollama, the model refresh button calls `/api/tags`. LM Studio and other OpenAI-compatible servers should expose `/v1/models` when configured as compatible endpoints.

## Local-Only Mode

When enabled, the backend rejects cloud defaults. The UI disables cloud providers in the default-provider selector. This is enforced server-side by `AIProviderStore.save_settings(...)` and again during provider resolution.

## Secret Handling

Credentials are encrypted at rest with `CREDENTIAL_ENCRYPTION_SECRET` using Fernet. Saved secrets are never returned to the browser. Admin responses include only a display hint such as `gsk••••3456`.

Set a strong secret in production:

```env
CREDENTIAL_ENCRYPTION_SECRET=replace-with-a-long-random-secret
```

Rotating this secret requires re-entering provider credentials unless a migration/decryption process is added.

## Usage and Audit

Each AI call records provider, model, latency, success/failure, and token counts when available. Prompt text is not stored by default. Provider and credential changes are written to `ai_audit_logs` without secret values.

## Adding a Provider

1. Add metadata to `PROVIDER_DEFINITIONS`.
2. Implement an `AIProvider` adapter with `send_message`, `list_models`, and `test_connection`.
3. Register it in `AIModelService.adapter_for`.
4. Add tests with mocked external calls.
5. Document authentication and model discovery behavior.

## Current Limits

- OAuth button flows are not fully implemented yet; the data model and credential types are ready for official Gemini/GitHub OAuth flows.
- Streaming is represented in the provider protocol, but the guest endpoint still returns non-streamed JSON.
- Automatic failover schema exists through settings/fallback fields, but the MVP routing mode is `fixed`.
- RBAC and CSRF protection depend on a future admin authentication system; current endpoints are under `/api/admin` but this local MVP has no login layer yet.
