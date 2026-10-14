# Concierge.AI guest experience redesign

Date: 2026-10-14  
Scope: local implementation and isolated preview; no deployment or commit.

## 1. Existing features reused

- The property opt-in Intelligent UI route and server-wide kill switch.
- Property-grounded guest knowledge, structured restaurant/facility/policy/map blocks, map assets and published navigation data.
- Existing service catalog, review-and-confirm service request APIs, session cookies, request authorization, stay context, and request lifecycle.
- Admin-managed property content, authentication, RBAC, property resolution, network guardrails, and the legacy guest interface fallback.

## 2. Missing features implemented

- Greetings and casual conversation now receive a direct response instead of the verified-fact fallback.
- Follow-up turns use the existing session history to resolve conversational references.
- Guests can ask for request status and see a typed status card populated only from requests linked to their current guest session or active stay.
- Guests can ask for directions between named locations. The response uses configured, published guest-visible map nodes and edges, renders an ordered route, and does not invent distances or hidden locations.
- The chat-first surface now has a compact welcome, contextual dining/facilities/nearby/service prompts, clearer rich response cards, and safer spacing around the persistent composer.
- Responsive touch targets, wrapping, focus styles, semantic status/list structures, and reduced-motion support were retained or improved.

## 3. Remaining gaps

- The production-wide Intelligent UI switch remains in its configured rollout state; only the local preview uses the switch and property opt-in. The legacy interface remains the fallback.
- The local Hotel De Luna home currently has no published property highlights. Guests will see only content administrators have published; no demo hotel facts were added to production logic or committed.
- Indoor directions require an admin-configured floor map and guest-visible route. The local sample journey uses synthetic map data created inside the isolated E2E database.
- Keyboard/focus/touch behavior and reduced-motion support were checked, but a manual screen-reader review and quantitative color-contrast audit were not performed.
- The mobile, tablet, and desktop checks ran in Chromium viewports, not on physical devices.

## 4. Screenshots

Responsive welcome and confirmed request-status screenshots are in this folder:

- `welcome-390x844.png`, `welcome-768x1024.png`, `welcome-1440x900.png`
- `greeting-390x844.png`, `greeting-768x1024.png`, `greeting-1440x900.png`
- `request-status-390x844.png`, `request-status-768x1024.png`, `request-status-1440x900.png`

The status screenshots show the backend-confirmed towel request above the composer at all three viewport widths. `evidence.json` records the visual observations and content states.

## 5. Backend and API changes

- No routes were added. The existing intelligent-chat response schema now accepts typed `request_status` and `directions` blocks.
- Existing chat orchestration now fast-paths greetings and request tracking, resolves follow-up context, and creates route blocks only from verified guest-visible map data.
- The frontend validates and renders those blocks. Service requests still require explicit confirmation and a successful backend response before the guest sees a submitted state.

## 6. Test results

- Python: 46 passed, 2 dependency deprecation warnings.
- Playwright Chromium: 74 passed across `guest.spec.js` and `guest-premium.spec.js` (final run: 50.1 seconds).
- Coverage included greeting, hotel information, dining, facilities, nearby attractions, configured maps and directions, service confirmation/cancellation/status, empty/error/loading/expired-session states, property isolation, and mobile/tablet/desktop layouts.
- `node --check app/guest_v2/app.js`, `git diff --check`, and the frontend evidence checker passed.

## 7. Security impact

- Authentication, RBAC, property isolation, guest-session validation, and request confirmation were preserved.
- Request status is scoped to the current guest session and linked active stay. Direction output excludes unpublished or non-guest-visible nodes.
- The local server binds only to `127.0.0.1`, uses a copy of state under `/private/tmp/concierge-preview-t4_ndjqn`, and disables background workers. The source database is not used by that preview.
- The production rollout defaults were not changed. No deployment or commit was made.

## 8. Migrations

None required.

## 9. Acceptance criteria

| Criterion | Result | Evidence / limit |
| --- | --- | --- |
| Concierge is the primary guest interaction with a compact welcome and integrated composer | Pass | Responsive welcome screenshots; chat-first route enabled only for the local opted-in property |
| Contextual chips cover dining, facilities, nearby discovery, and service requests | Pass | Four default prompts and responsive touch-target checks |
| Greetings do not trigger missing-knowledge fallbacks | Pass | Unit and Playwright greeting journeys |
| Hotel facts and rich cards use published property sources | Pass | Existing grounded retrieval and Playwright dining/facility/hotel/map journeys |
| Request creation requires review/confirmation and status is genuine | Pass | E2E confirmation plus backend-created request-status journey |
| Maps/directions do not invent routes, distances, or hidden facilities | Pass | Configured-route E2E and guest-visible node filtering; location without an explicit route gets a safe fallback |
| Authentication, RBAC, property/session isolation remain intact | Pass | Existing auth/property-isolation E2E plus current guest-session scoping |
| Responsive layouts work at mobile, tablet, and desktop sizes | Pass | 390x844, 768x1024, 1440x900 screenshots; no horizontal overflow or composer overlap |
| Accessible keyboard/touch behavior | Pass with review gap | Keyboard Enter, focus styling, 44px suggestion targets, semantic lists/status, and reduced motion checked; manual screen-reader and quantitative contrast reviews remain |
| Current hotel content is fully ready for a production rollout | Not verified | The local Hotel De Luna home has no published highlights; admins need to review/publish their property’s content and maps before rollout |

## Local preview

- Guest: `http://127.0.0.1:8080/`
- Admin: `http://127.0.0.1:8080/admin`
- Username: `admin`
- Password: `ChangeMe123!`

The admin page is already authenticated in the local preview tab. The guest page opens the redesigned chat-first experience.
