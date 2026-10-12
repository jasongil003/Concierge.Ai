# Concierge.AI Intelligent UI architecture baseline

Reviewed checkout: `feature/intelligent-guest-ui-v2`, based on `fbf9d50635c427f5340098cac48e7bb8eb7ef7a2` (the October 10 guest/admin UI update). The working tree was clean before the requested branch was created.

## Existing application

- FastAPI starts in `app/main.py`. It owns guest routing, property resolution, middleware, admin route authorization, sessions, rate limits, and API handlers.
- The legacy guest experience is a dependency-free static application: `app/static/index.html`, `app/static/app.js`, and `app/static/styles.css`. The October 10 commit updated this UI and added browser tests and screenshots. Those guest files remain intact.
- The admin portal is `app/static/admin.html`, `admin.js`, and `admin.css`. It is served at `/admin` and remains the same application; this change adds only property-level guest-interface fields to its existing settings page.
- Guest sessions start and resume through `/api/session/start` and `/api/session/resume`. The server issues session-specific HttpOnly cookies and checks the property and network on later requests.
- Guest chat is `POST /api/chat`. It owns message sanitization, rate limits, staff takeover state, deterministic hotel facts, property-scoped retrieval, provider selection, AI response validation, and outage fallback. The response remains unchanged.
- Guest actions already have separate proposal and confirmation routes. Service requests are matched to the current property's guest-visible catalog, require explicit confirmation, use a signed session/property-bound proposal token, and have an idempotent request key.
- Property data and configuration live in `PropertyRecord`; `app_settings` is JSON-backed. Property configuration updates use the existing authenticated admin path and do not need a database migration.
- SQLite and PostgreSQL are supported. Development and browser tests configure isolated state; tests assert that the persistent local SQLite database did not change.
- `package.json` contains Playwright only. There is no React, TypeScript, frontend bundler, or browser build pipeline.

## Security and tenant boundaries found

`PropertyGuard.resolve` selects the property from the request context; `_guest_session` verifies the current session, cookie credentials, and property match. Guest network policy is evaluated server-side. Browser writes pass the existing origin checks. Admin property routes pass the central authenticated, CSRF-protected route policy and property permission checks. Property-scoped catalog queries filter by `property_id`.

The current checkout includes the high-RBAC boundary fixes at the reviewed base commit. The repository's prior security audit marks its listed High findings fixed and still documents operational and Medium-level external validation work; see `audit/VULNERABILITY_FINDINGS.md` and `audit/CURRENT_READINESS.md`. This implementation does not replace that audit or certify production routing.

## Architecture decision

Add a separate static guest shell under `app/guest_v2/`, served only by the root route after secure property resolution and the server-side feature check. Keep its JS and CSS outside `/static`; the new asset route checks the feature flag on every request. The shell calls the existing session and service APIs and a new presentation adapter in front of `/api/chat`.

Use small dependency-free JavaScript components rather than React + TypeScript for this first local slice. The current app has no frontend build tool or TypeScript dependencies, and a separate framework bundle would add install, build, and deployment steps before it improves this vertical slice. Runtime schemas use the backend's existing Pydantic stack, and a browser allowlist renders only known blocks. A later frontend build decision can be revisited if the component set grows.

The v2 endpoint wraps the existing chat response; it does not introduce a second provider path, retrieval implementation, or action executor. Property configuration is stored in the existing `app_settings.guest_experience` JSON key. No schema migration is required.

## New request paths

- `GET /`: legacy static HTML unless the global switch and resolved property's `guest_experience.intelligent_ui.enabled` are both true.
- `GET /intelligent-ui/{app.js|styles.css}`: allowlisted v2 assets, gated by the same property and global check.
- `GET /api/guest/intelligent-config`: safe welcome copy and suggested prompts for the enabled property.
- `POST /api/guest/intelligent-chat`: validates the active guest session and property flag, calls the established `chat` handler, then serializes a versioned block response.

The `POST /api/chat` contract and legacy UI stay available. The v2 chat surface uses session-scoped browser-tab storage only; no new transcript database or migration was added.

## Current implementation boundary

Implemented locally: conversation-first shell, property branding, welcome prompts, text/suggestion blocks, property-scoped dining cards, explicit service-request review and confirmation, tab-scoped refresh recovery, safe text rendering, responsive layouts, and rollback.

Not implemented in this slice: SSE/streaming, server-side conversation history, full history browsing, maps with a map provider, persistent client telemetry, a separately compiled TypeScript bundle, and live provider quality evaluation. See the implementation report for verification evidence and limitations.
