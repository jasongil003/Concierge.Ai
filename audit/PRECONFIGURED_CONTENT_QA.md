# Preconfigured Content QA

Audit date: 2026-09-30  
Scope: fresh installation, first property creation, active defaults, legacy catalog upgrade, tenant isolation, empty-state UX, guest behavior, and test fixture boundaries.

## Executive Summary

**Does a fresh Concierge.AI property contain preconfigured hotel-specific data? NO.** A new property contains the administrator-entered property ID, name, and timezone plus neutral platform defaults. Its hotel content collections are empty.

The automatic service catalog seeding has been removed. An upgrade drops only its obsolete bookkeeping table and preserves all existing catalog rows. No operational template library is present. Existing appearance presets are explicit and affect appearance settings only.

## Fresh Install

The regression test uses an isolated `tmp_path` database. Before any property is created:

- `GET /health` returns `200` with `{"status":"ok"}`.
- Admin bootstrap login returns `200`.
- `GET /api/admin/properties` returns an empty `properties` list.
- `GET /api/hotel` returns `404 Property not found`; there is no hidden or automatically-created property.

A separate smoke check started the app in two distinct Uvicorn processes against a disposable database. It verified the same empty installation state before property creation and checked the blank property's APIs after the second process started.

## New Property State

The test created `qa-empty-property` with only `QA Empty Property` and `Asia/Manila`. APIs and the database showed:

| Area | Result immediately after creation |
| --- | --- |
| Rooms, facilities, restaurants, departments, services | Empty |
| Menus, menu items, promotions, events, recommendations | Empty |
| Knowledge items, managed documents, FAQs | Empty |
| Buildings, floors, maps, zones, access points, navigation | Empty |
| Guest sessions, stays, devices, service requests | Empty |
| Notification rules, notifications, deliveries | Empty |
| Property contact details, support contacts, guest modules | Empty |
| Domain, public URL, property ANTlabs config | Not configured |
| Property authentication | Disabled; no enabled authentication types |
| Domain and SSL deployment status | `not_configured` |
| PMS personalization | Disabled |

Direct SQLite counts were zero for `departments`, `service_catalog`, both facility tables, `restaurants`, `menus`, `menu_items`, `restaurant_promotions`, `hotel_events`, `recommendations`, operations and managed knowledge tables, buildings/floors/maps/zones, access points/navigation, sessions/stays/guest sessions/devices, service requests, notification tables, webhooks, and guest journey events. Rooms, policies, and some other profile settings are fields on the property record; those fields were also checked as empty. The `properties` table contained only the one administrator-created property.

The public property profile contained no rooms, facilities, dining, or enabled authentication methods. The UI showed empty states for Rooms, Facilities, Restaurants, Service Catalog, FAQs, and Documents. The guest home rendered without home cards or dining, facilities, events, promotions, or recommendation sections.

The guest-session API was empty in the initial snapshot. The test then deliberately created one session to exercise the empty guest home and action flow; that later test activity is not property seed data.

## Platform Defaults

These are safe platform or presentation defaults, not configured hotel facts:

- The administrator supplies the property identity and timezone. The data model's timezone fallback is UTC; the create-property flow requires a timezone.
- Concierge display name, generic welcome copy, English language default, and a neutral color/font/layout theme. Logo/contact fields and suggested actions remain blank.
- `on-prem` deployment-mode default, empty property profile arrays/objects, and empty design suggestions.
- Authentication method definitions and RBAC role/permission definitions exist as schemas. No property authentication method is enabled by default.
- Guardrails default to guest-network-only access, loopback-only allowed CIDRs, a 30-minute guest session, disabled ANTlabs gateway, disabled reservations and financial actions, and enabled audit logging. Rate limits and session/cookie controls are platform behavior; secure-cookie enforcement is environment-specific.
- Personalization defaults to private guest memory and disables PMS personalization. Consent and retention controls are platform policy.
- The system LLM policy in `app/llm.py` instructs the model not to invent hours, prices, availability, locations, guest records, or completed actions; it treats property knowledge and internet results as untrusted data and protects property/guest boundaries.
- Guest service actions are allowlisted, require a match to an active configured service, use a short-lived property/session-bound confirmation token, and re-check backend authorization before creating a request. Admin endpoints enforce property RBAC; existing restaurant workflow tests restrict staff and managers to assigned restaurants.

Internet search, directions, weather, and recommendation capabilities are configuration flags, not stored hotel content. Internet recommendations can still return external results when enabled; they do not create property-owned restaurant or recommendation records. The development/example ANTlabs mode is `mock`, which is a global simulator mode, not a property's active ANTlabs configuration. Production startup rejects mock mode.

## Hotel-Specific Defaults

**NONE active on a fresh property.** There are no seeded departments, services, rooms, facilities, restaurants, menus, hours, prices, addresses, recommendations, promotions, hotel policies, guest identities, room numbers, PMS records, phone/email contacts, ANTlabs property settings, or domains.

Generic categories and instructional examples remain in schemas and admin help—for example Housekeeping as a knowledge category, or towels as a service example. They do not create property records or assert that a property offers those services. Generic role names such as Concierge / Front Desk are RBAC definitions, not configured departments.

## Template Readiness

The application has appearance and welcome-style presets. They require an administrator action, update a design preview/draft, and are explicitly described in the UI as changing appearance settings only. They do not create operational property records.

There is no department, service, facility, or AI-personality template library and no operational template-copy flow to test. Recommended future flow: select and deselect template entries, edit and preview them, explicitly confirm, then copy them into property-scoped editable records. Template content should never be guest-visible or active before that confirmation and must not include identity, availability, price, hours, phone, email, or address claims.

## Guest Empty-State Behavior

The blank property's guest-home API returned empty inventory for restaurants, facilities, promotions, menu items, and recommendations, with no event cards. Browser checks confirmed the corresponding home sections remain hidden when empty, rather than showing sample content.

For “Where is the pool?”, the property fast-answer path returns no answer when no verified pool record exists; the model prompt requires the assistant to state when verified information is unavailable. An “extra towels” request against the empty catalog returns `unmatched`, has no service choices, and creates no service-request row. These tests verify backend behavior and safety instructions; they do not prove that every third-party model response will follow its prompt perfectly.

## Property Isolation

The two-property regression test configures a department, service, facility, restaurant, and FAQ only in Property A. Property B's hospitality, service-catalog, and knowledge APIs remain empty; an attempted delete through Property B returns `404` and leaves A's service intact. A guest session and home for B show empty inventory, and requesting A's service in B yields `unmatched`.

## Test Fixture Isolation

- Pytest onboarding databases use pytest temporary directories.
- Playwright uses a process-specific database under the operating-system temp directory (`concierge-ai-e2e-<pid>.db`). The E2E property, Fixture Bistro, Housekeeping, Baby Crib, and guest request data are created only by test setup/API calls in that database.
- Docker smoke scripts write synthetic records into a CI smoke-test container/volume; the CI workflow invokes them as runtime persistence checks. The application does not import test fixture modules.
- `Hotel A`/`Hotel B` also appear in test cases and the guardrails checklist as examples. Old audit notes under `audit/` retain historical references to the retired Lunara demo seed; they are archival documentation, not loaded by runtime code.
- Repository searches found no retired hotel identity or seeded-content call in active application code. Generic admin guidance and hotel categories are examples/schema values, not fixtures copied into storage.

## Database Verification

The fresh-property SQLite checks found no unexpected property-scoped content rows in the tables listed in **New Property State**. Required internal schema and system metadata are not treated as hotel content. One guest session was deliberately added only after the initial empty-state assertions for the guest experience check.

The new Alembic head is `20260930_0001`. The legacy-upgrade regression builds an older catalog state, applies the old and new revision operations, and verifies that the seed-state table is gone while its department, both services (including an administrator-created service), facility profile, and FAQ remain. It then opens the application against that database and verifies the API does not reseed content. Live PostgreSQL migration integration was not available because `DATABASE_URL` was not configured; PostgreSQL-specific tests were skipped.

## Automated Test Results

- `.venv/bin/python -m pytest -q`: **768 passed, 16 skipped**, 2 dependency deprecation warnings, 22.99 seconds.
- Skips are integration checks guarded by missing PostgreSQL (`DATABASE_URL`) or Redis (`REDIS_TEST_URL`) services.
- Migration graph: one head, `20260930_0001`, following `20260929_0006`.
- `git diff --check` and Python `compileall` passed.

## Browser Test Results

- `npm run test:e2e`: **231 passed, 33 skipped**, 4.7 minutes, across Chromium and mobile Chromium; no failures. The browser suite intentionally skips desktop-only/mobile-only and project-specific cases.
- After expanding the onboarding check to include empty Facilities and Restaurants UI plus hidden empty guest-home sections, the focused onboarding test passed in both projects: **2 passed**.
- The XSS regression was updated to explicitly create its own test service instead of relying on the removed starter catalog; XSS and onboarding passed in both browser projects: **4 passed**.
- The control inventory checked 42 admin destinations and 5 guest views: 2,065 visible control instances, 2,032 focusable, **0 enabled controls not focusable**, and **0 missing accessible names**. The prior keyboard-focus issue was not reproduced.

## Issues Found

- The first full browser run exposed stale test assumptions: the XSS test expected an automatically seeded service, and the onboarding test reused a property ID whose test rows survived property deletion in the shared E2E database. The tests failed; no assertions were weakened.
- With the seed removed, a property with no domain was reported as SSL `not_checked`, which implied a verification attempt. It now correctly reports `not_configured`.
- The ANTlabs status endpoint reported global connector status without clearly showing that the property had authentication disabled. It now returns separate property-level authentication state and enabled types.

## Fixes Made

- Removed the application-start and property-create calls to starter-catalog seeding and removed the production seeding method/table creation.
- Added migration `20260930_0001` to remove only obsolete seed-state metadata; existing departments and services are preserved.
- Expanded fresh-install, new-property, process/lifespan restart, database-row, guest-empty-state, property-isolation, legacy-upgrade, source-scan, and browser onboarding coverage.
- Updated test fixtures to create their own service records, and made onboarding use a unique property ID so old test rows cannot contaminate a newly created property.
- Updated `docs/DEPLOYMENT.md` with clean onboarding and legacy-record review guidance.

## Remaining Risks

- Existing databases keep all catalog rows. An administrator must review any legacy starter-looking rows and remove confirmed-unused content; deleting by name during migration could destroy administrator data.
- The AI non-invention policy is prompt-based. Backend matching and verified fast answers avoid creating unsupported service actions, but generative answers can still deviate from instructions. External search results are also separate from property-verified facts.
- Operational templates are not available yet. Live PostgreSQL migration integration also remains unverified until a PostgreSQL test service is configured.

## Recommendation

**PASS WITH MINOR FOLLOW-UP** — clean property onboarding is verified. Follow up by reviewing legacy catalogs on upgrades, providing a PostgreSQL migration test service, and considering an explicitly confirmed operational template library. The remaining AI generation caveat is documented above.
