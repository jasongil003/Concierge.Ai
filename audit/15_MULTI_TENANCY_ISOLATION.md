# 15 — Multi-Tenancy Isolation (operator guide)

Model: one process, one DB, N properties. Tenant boundary = property_id at the API layer (guest path) or can_access_property (admin). Tenants are real hotel brands hosted by one operator.

## Isolators verified
- Guest: PropertyGuard binds property to host-header; wrong property in body while Host matches brand → PermissionError (verified). Single-property default deployment → body accepted; when multi-brand, disable (05).
- Session data scoped by (property_id, session_id); session_start requires property_id for multi-brand.
- Admin: property-scoped endpoints apply can_access_property; super-admin bypasses to global.
- Memory/store boundaries: hospitality/zones/intro/analytics tables all keyed property_id; no cross-read found in runtime paths inspected.

## Gaps/risks
1. Body-selective property (05/SEC-004) — enable host-binding rule before adding a 2nd brand.
2. AI provider credentials: per-provider, shared across properties unless bound; a tenant could call a provider bound to another brand only if it knows the provider_id — surface only "their" providers in the admin UI (verify).
3. Shared encryption secret for all tenant credentials — single compromt of DB + file = all tenants; acceptable for on-prem single-org, document for franchise ops.
4. Observability/audit events not namespaced by tenant (raw log lines only).
5. Reporting exports are property-scoped; ensure worker export endpoints check can_access_property (code confirms paths guarded).

## Recommendation
Ship `multi-brand onboarding checklist`: set ALLOW_BODY_PROPERTY_SELECTION=false, bind host→property for every brand, run cross-tenant probe script (audit_proof property-hop section) as CI, review per-tenant provider visibility.