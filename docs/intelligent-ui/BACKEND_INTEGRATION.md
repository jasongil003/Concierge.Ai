# Intelligent UI backend integration

## Existing services reused

| Need | Existing source |
| --- | --- |
| Property profile and branding | `GET /api/hotel` after `_guest_property` and guest network policy |
| Guest session continuity | `POST /api/session/start`, `POST /api/session/resume`, session-specific HttpOnly credentials |
| Hotel facts, retrieval, provider routing, staff takeover | `POST /api/chat` and its existing handlers |
| Property dining inventory | `HospitalityStore.guest_facilities(property_id)`; database queries filter by `property_id` and exclude disabled/archived restaurants |
| Service catalog suggestions | `GET /api/guest/service-catalog` |
| Service proposal and review | `POST /api/guest/actions/propose` |
| Explicit authorized action | `POST /api/guest/actions/confirm` |

The UI does not send a property ID with chat messages. The server resolves the property from the trusted guest request context, checks the session/property match, and calls the existing backend.

## Protocol adapter

`POST /api/guest/intelligent-chat` accepts the same bounded `ChatRequest` data as the legacy handler. It verifies an authorized guest session and the server-side v2 flag. The adapter invokes `chat(payload, request)` and wraps only the answer text and deterministic property data in `IntelligentUIResponse`.

For dinner/dining prompts, the adapter may add a text-only collection of guest-visible restaurants from the current property. It does not include live-place URLs, image URLs, or model-generated entity IDs. If there are no configured venues, the adapter adds no cards.

## Service request workflow

1. The client detects a possible service request for routing only. This is not authorization.
2. It asks `/api/guest/actions/propose` to match the text against the current property's enabled service catalog.
3. A successful proposal displays a review panel with the signed token and requires a guest button press.
4. `/api/guest/actions/confirm` rechecks the current guest session, property, configured service, action guard, and proposal signature.
5. The UI reports success only after the endpoint returns `created` or idempotent `existing` with the request record.

An unsupported service is described as unsupported and the configured catalog is offered as an alternative. An ambiguous match is not submitted. A failed confirmation never renders success.

## Session, failure, and retries

The active session ID and v2 transcript are stored in `sessionStorage`; the stable anonymous client identifier remains in `localStorage`, matching the legacy session model. The transcript is keyed by session ID and is restored only after the server successfully resumes that same session on the current property. Changing the property drops the tab transcript. “New chat” removes its transcript and starts a new server session.

Messages stay visible while a request is pending. Network failures leave the text visible and do not automatically replay it. Service confirmation retries use the same signed proposal, which the backend deduplicates. Session expiry is shown to the guest and requires a new session.

## Deliberate limits

The adapter returns a whole JSON response. It does not implement SSE, streaming, cancellation, or server-side history. Maps and external place links remain unrendered. The current implementation uses the selected provider, retrieval, safety, and fallback behavior already present in the application.
