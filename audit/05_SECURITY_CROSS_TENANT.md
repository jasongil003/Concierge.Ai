# 05 — Security: Cross-Tenant Isolation & Guest Boundary

## Property resolution semantics (verified via proof runs + code walk)

- Public guest property = `_guest_property` middleware → `PropertyGuard.resolve`.
  - Host header matches a property domain → that property.
  - No host match & exactly one property → the single default.
  - No host match & multiple properties → guest must supply `property_id` explicitly (host mismatch + provided property → PermissionError).
- This is the documented contract. With a single-property deployment it means the Host header is NOT binding. If the box later hosts multiple brands (or shares an IP), property hopping via the request body is possible. today single-property deployments (demo seed) are safe.

## Verified guest boundary behaviours

- Guest session token is an opaque random token bound to client_id; no cross-session reuse.
- Service requests are stored against (property_id, session_id); the guest API only reads back its own session contexts.
- Admin endpoints resolve service requests by property_id with `can_access_property` in front.
- Hospitality overview returns service_request rows that flow into admin UI text nodes (SEE-07 for XSS).

## Findings

- SEC-004 (MED): property selection not host-bound when Host does not match a mapped domain. Verified via `PropertyGuard.resolve(records, default, unknown-host, supplied_property)` → supplied accepted. Fix direction: reject unmapped Host when >1 property exists (403), or require property_id carve-out config (`ALLOW_BODY_PROPERTY_SELECTION=true` per brand).
- SEC-012 (LOW): guest mutations carry no Origin/Origin-referrer validation. Impacts are limited because effects are session-scoped writes (service requests, memory, session ctx). CSRF-style abuse only relevant if guests are unauthenticated state-changers on shared browsers (e.g., lobby kiosk). Add optional Origin allow-list for guest POST endpoints.

## Recommendations
1. Default `ALLOW_BODY_PROPERTY_SELECTION` off once multi-property is enabled; log host+property decisions at WARN when mismatched.
2. Add an Origin allow-list check on `/api/guest/*` mutating endpoints (config-driven) for kiosk-safe deployments.