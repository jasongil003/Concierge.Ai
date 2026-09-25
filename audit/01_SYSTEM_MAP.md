# 01 — System Map & Data Flow

Platform: Concierge.Ai v0.2.0 — on-prem hotel concierge + operations console.
Repo root: C:\Users\JasonGil\Documents\GitHub\Concierge.Ai (branch feature/onprem-mvp).

## Runtime topology

- FastAPI app (`app/main.py`, ~2790 lines) on ASGI; served via `uvicorn`, configured host/port via env (default 0.0.0.0:8080).
- SQLite single file `state/concierge.db` shared by every store (guest sessions, properties, hospitality, zones, intro, location analytics, AI providers/credentials spent, webhooks, improvement loop, reports, observability). Admin auth has its OWN store class (`AdminAuthStore`) but the same SQLite file is used for it by default (`settings.db_path`).
- Static frontends mounted at `/static`: guest app (`index.html` + `app.js`), admin console (`admin.html` + `admin.js`), admin login (`admin-login.*`).
- AI: provider adapters (Gemini, OpenAI, Groq, OpenRouter, Claude, OpenAI-compatible, local Ollama/LM Studio). Cloud credential secrets stored Fernet-encrypted in DB (`CREDENTIAL_ENCRYPTION_SECRET`).
- ANTlabs gateway via `AntlabsAdapter` (mock | live). Google Places is the only outbound internet tool from the guest AI path.
- Data seeds: hotel JSON (`data/lunara.json`) + `lunara_seed.py` demo property `lunara-mnl-001`.
- Docker: `python:3.12-slim`, volume `concierge-state:/state`, Ollama via `host.docker.internal:11434`. (Audit fix adds non-root user + healthcheck; see 19.)

## Component inventory (app/*.py)

| Module | Responsibility | Notes |
|---|---|---|
| main.py | Routes, middleware, orchestration | Single central app; keeps logic inline |
| config.py | env settings | Pydantic-free dataclass |
| admin_auth.py | Admin users/roles/sessions/audit/reset | RBAC permissions model |
| session_store.py | Guest sessions (TTL, staff messages, conversation state) | |
| guest_identity.py | Device ids (HMAC), stays, memory | |
| properties.py | Property records, design config | |
| guardrails.py | NetworkGuard, PropertyGuard, ActionGuard, PrivacyGuard, InternetGuard, GatewayGuard, RateLimiter, SecurityAuditLogger, AI sanitizers | Central trust layer |
| hospitality.py | Facilities, dining, services, service requests, events, menus | |
| operations.py | Departments, knowledge, webhooks, email settings | |
| antlabs.py | Gateway auth (mock + live) | |
| places.py | Google Places search | |
| ai.py | Legacy AIOrchestrator (fallback chat across providers) | Used as exception fallback in /api/chat |
| ai_providers.py | AIProviderStore + AIModelService (provider-spanning) | New, primary path |
| llm.py | Local Ollama + fallback chain system prompt | |
| zones.py | Zone/map objects, APs, floor maps | |
| intro.py | Branding/intro assets | |
| location_analytics.py | WiFi location aggregation | |
| operations.py not needed above | | |
| observability.py | Request telemetry, diagnostics registry | |
| reporting.py | XLSX/CSV/PDF exports | inlineStr cells mitigate formula injection |
| improvement_loop.py | Self-review loop w/ provider | Off by default |
| lunara_seed.py | Demo seed | |

## Guest flow (request path)

1. Guest loads `/` → `index.html`; `app.js` calls `POST /api/session/start` (client_id, optional property_id, gateway_context). Middleware: `_guest_property` → `PropertyGuard.resolve` (host mapping → property), `_enforce_guest_network` → `NetworkGuard` (IP vs allowed_cidrs), antlabs `GatewayGuard` when enabled. Session token (opaque) returned; stored server-side with 30 min TTL.
2. `POST /api/chat` → guest session revalidation → rate limit → `AIInputSanitizer.sanitize_text` → context assembled (ops knowledge + hotel knowledge + property context + optional auth guidance) → `PrivacyGuard.classify` fast path → `AIModelService.concierge_chat` (provider via `default_provider`) → on exception fallback `AIOrchestrator.chat` → `AIOutputValidator.validate` → response. Mode `advanced` dispatches `conversation.escalated` webhook.
3. `POST /api/guest/service-requests` → `ActionGuard.decide` (needs `confirmed:true`, feature flag) → rate limit → `HospitalityStore.create_service_request` → webhook `guest.request.created`.
4. `POST /api/authenticate` → Antlabs adapter auth (mock mode admits any valid-looking room+last_name).
5. Uploads → `POST /api/guest/uploads` (whitelisted MIME, base64, 1MB) → document context in chat.

## Admin flow

/ → /admin/login → `POST /api/admin/auth/login` (username+password, lockout) → `concierge_admin_session` cookie (HttpOnly, SameSite=Strict, secure in prod) + CSRF token in JSON → `GET /api/admin/auth/me`. All `/api/admin` requests: auth cookie → principal; permission check by path (`_required_admin_permission`); non-GET requires `X-CSRF-Token` (hmac compare); every property path checked via `can_access_property`.

## Auth/session trust boundary summary

- Guest trust secret = `session_id` bearer in body; no cookie; no Origin check (documented finding OBS-012).
- Admin trust secret = HttpOnly cookie + CSRF token in header.
- Cross-tenant isolation = property_id on guest path + host mapping; admin isolation = RBAC + `can_access_property`.
- AI boundary: all KB/property context is injected into the model prompt with no "untrusted context" instruction (finding SEC-008/PROMPT).

## Services & dependencies (in/out of scope)

- In scope: everything in app/, static/, tests/, docs/, Docker.
- Out of scope (external): Google Gemini/OpenAI/Ollama/Places API behaviour, ANTlabs firmware.