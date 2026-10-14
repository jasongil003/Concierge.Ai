# Full feature acceptance

Date: 2026-10-14 (Asia/Manila)  
Reviewed commit: `6bc9fbba880389c08d8fc011383fc2274e632665`  
Test data: isolated SQLite and synthetic property records. No live hotel content, guest data, AI provider, PMS, gateway, or production service was used.

## Status definitions

- **Implemented** — the code path exists; the listed evidence does not establish end-to-end acceptance.
- **Verified** — the stated local behavior passed fresh automated tests in this review.
- **Partially verified** — some local behaviors passed, while property truth, full surface coverage, or live dependencies remain unverified.
- **Missing** — no dedicated implementation was found for the named feature.
- **Blocked** — acceptance depends on external data, credentials, devices, services, or permissions unavailable here.

## Guest experience and content

| Requirement | Status | Evidence and remaining boundary |
|---|---|---|
| Guest shell, navigation, conversation restoration, draft preservation, loading/error recovery, responsive composer and scroll continuity | **Verified** | `npm run test:e2e`: 334 passed. `tests/e2e/guest.spec.js`, `guest-premium.spec.js`, and `manual-qa-responsive.spec.js` cover named flows and 9 Chromium viewport sizes plus Pixel 7 emulation. No physical device or screen reader was used. |
| Multi-turn dining context: “I'm hungry” → Japanese food → menu → “Where is it?” | **Partially verified** | `tests/test_intelligent_ui.py::test_restaurant_menu_and_location_followups_keep_the_unique_property_selection` verifies the deterministic sequence against two synthetic restaurants, retaining the selected property restaurant and returning its published location. Live model behavior and approved hotel records remain unverified. |
| Hotel overview, check-in/out, amenities, restaurants, menus, hours, facilities, entertainment, attractions, policies, transport, and accessibility retrieval | **Partially verified** | Property-scoped published-content retrieval and multiple specific content journeys are covered. No property owner supplied authoritative content for all categories, so factual completeness and accuracy are not established. |
| Restaurant recommendations, published menu items/prices, hours, location, images, and follow-up context | **Partially verified** | Browser and backend tests verify synthetic restaurant cards, published menu filtering, configured hours, image fallback, and restaurant follow-up. Real availability, prices, hours, images, rights, and locations need property approval. |
| Missing information handled without invented facts or directions | **Verified** for tested paths | Grounding tests return only configured property data; map tests report unavailable routes when geometry is absent. This is not a proof for every provider response. |
| Guest request proposal, explicit confirmation, one persisted ticket, reference/status, cancellation, replay idempotency, and concurrent duplicate protection | **Verified** locally | E2E now includes “Can I have two extra pillows?” → “Extra Pillow,” then explicit confirmation and a created response; request status/cancellation flows also pass. `tests/test_guest_personal_home.py` verifies replay behavior; `tests/test_service_catalog.py` verifies concurrent same-key submissions create one ticket. These tests do not verify real hotel fulfilment or notifications. |
| Conversation isolation when changing properties and expiry/revocation handling | **Verified** in synthetic tests | Browser session-resume, cross-property host, expiry recovery, and revocation cases pass; backend tenancy/session regressions pass. No live hotel domain or identity infrastructure was used. |
| Physical-device behavior, captive mini-browser behavior, screen-reader support, and assistive technology | **Blocked** | Only desktop Chromium and Pixel 7 emulation ran. No physical iPhone/iPad/Android, Safari, captive browser, or screen reader was available. |

## Admin portal and publishing

| Requirement | Status | Evidence and remaining boundary |
|---|---|---|
| Property, restaurant, menu, facility, map, policy, and guest-page management without source edits | **Partially verified** | E2E covers named onboarding, restaurant CRUD/publish/archive, facilities, map editing, appearance, knowledge, and configuration workflows. The full surface and every validation/error state were not behaviorally exercised. |
| Published versus draft/unpublished guest content | **Verified** for tested records | Backend publication regressions and E2E upload/review/publish flows verify draft/review content does not become guest content before publication. Synthetic fixtures only. |
| Staff requests, conversation queue, user management, roles, and permission boundaries | **Verified** for covered workflows | Browser admin request, staff conversation, user, role, and permission flows pass; backend RBAC/property/department/restaurant-scope tests pass. This is not a complete third-party security certification. |
| Dashboard metrics, reports, and exports | **Verified** with synthetic data | E2E operations/analytics flows and backend reporting/PDF/XLSX tests pass. No real hotel dataset or production-scale metrics were used. |
| Every visible control and every permission/error path | **Partially verified** | Control inventory covers 42 admin destinations, 5 guest views, and 2,125 visible controls; it found 0 enabled non-focusable controls and 0 missing accessible names. The inventory explicitly does not click every control; named workflows cover selected functions. |
| Image/map uploads, path containment, traversal, symlink escape, and cross-property media isolation | **Verified** for tested cases | Backend security tests cover upload validation, hash-named media, traversal and symlink boundaries, and property scope. Real content licenses and map accuracy remain blocked on owners. |

## Maps, AI, and integrations

| Requirement | Status | Evidence and remaining boundary |
|---|---|---|
| Multiple buildings/floors, facilities, markers, destination search, route graph, map controls, and text alternative | **Partially verified** | E2E verifies synthetic maps, floor switching, search, route rendering, zoom, and a text alternative. Approved geometry and on-site route accuracy were not available. |
| Accessible routing and real indoor directions | **Blocked** | Requires approved floor plans, accessible-path rules, and on-site validation. No fictional route is accepted as evidence. |
| OpenAI/Gemini/Groq-compatible/Anthropic/Ollama provider adapters, provider selection, mock fallback, streaming, masking, usage accounting, and property context | **Partially verified** | Adapters and fixture-backed routing, masking, fallback, scope, and streaming tests exist and pass. No paid/live provider call was made; live response quality, latency, cost, quotas, privacy terms, and failover are unverified. |
| Live ANTlabs SG5, PMS, WLAN/RADIUS/ACS, checkout, roaming, and captive login | **Blocked** | Contract/mock tests are not live network admission. No authorized staging gateway, PMS, WLAN, or guest device was available. |
| Dedicated QR/NFC guest product flow | **Missing** | No dedicated product flow was found; sharing a canonical URL is not QR/NFC acceptance. |
| Guest location/AP consent, opt-out, checkout expiry, retention, export, and deletion lifecycle | **Partially verified** | Some storage/retention hooks exist, but the complete owner-approved property policy and end-to-end lifecycle tests remain incomplete. This blocks a hotel pilot. |

## Deployment, reliability, and capacity

| Requirement | Status | Evidence and remaining boundary |
|---|---|---|
| SQLite development and local persistence | **Verified** for automated local tests | Full backend suite passed and the persistent repository SQLite database hash and journal/WAL sidecars were unchanged. |
| PostgreSQL production, SQLite-to-PostgreSQL migration, PostgreSQL backup/restore, and Redis integration | **Blocked** | 14 PostgreSQL-related cases and 2 Redis-related cases skipped because no `DATABASE_URL` or `REDIS_TEST_URL` services were configured. Docker daemon was unavailable. |
| Docker Compose configuration | **Verified** at configuration-parse level | Compose parsed with synthetic required settings; omitting the production bootstrap password failed closed as intended. Container build/start/health/persistence were not run. |
| Docker runtime, clean Ubuntu/macOS install, system services, upgrade, rollback, and reboot recovery | **Partially verified** | Installer/configuration and local recovery tests exist; `systemd-analyze` was unavailable and no clean target host or Docker daemon was available. Native target installation/reboot acceptance remains outstanding. |
| SQLite backup/restore and restart recovery | **Partially verified** | SQLite backup/restore unit tests pass; no fresh target-host restart/restore rehearsal was run. |
| Encrypted off-host backups and key recovery | **Blocked** | No separate recovery target or owner-held key recovery rehearsal was available. |
| 30,000 concurrent guests, soak, and production SLOs | **Blocked** | No representative load environment or load/soak run was performed. Unit/E2E tests and local smoke behavior do not prove this capacity. |

## Fresh test summary

- Backend: **1,185 passed, 18 skipped, 0 failed**. Skips: PostgreSQL, Redis, Linux memory-limit, and `systemd-analyze` requirements.
- Playwright: **334 passed, 38 project-specific skips, 0 failed** across Chromium and Pixel 7 emulation.
- Python dependency audit: **no known vulnerabilities**.
- Node dependency audit: **0 vulnerabilities across 3 packages**.
- Bandit configured Medium/High scan: **0 findings**.
- Gitleaks: current worktree has one unclassified local `.env` match; forced full history scan reports the three known historical credential copies. See `SECURITY_REMEDIATION.md`.
