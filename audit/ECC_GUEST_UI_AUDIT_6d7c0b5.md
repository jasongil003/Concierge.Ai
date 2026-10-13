# ECC independent guest UI audit — `6d7c0b5`

Date: 2026-10-13 (Asia/Manila)  
Audited commit: `6d7c0b51f21eb9d3590154b563a0a8f0ba17cdf3`  
Workspace branch: `codex/guest-concierge-premium-2026-10-13`

## Release decision

**FAIL for a real hotel pilot.** The guest UI regressions found in routing and modal focus were corrected locally and the scoped backend and browser suites pass. The AI response path still has no deterministic check that property claims are supported by retrieved facts. Also, the GitHub Actions `browser-tests` job for the audited commit is red and its detailed log was not accessible from this environment. Do not release this candidate to hotel guests until those two gates are resolved.

All data used in local verification was isolated synthetic test data. The persistent SQLite safety check was unchanged. No production data, deployment, push, merge, or commit was performed. Workspace changes are uncommitted.

## Guest surface inventory

### Routes and page views

| Surface | Guest behavior | Implementation |
| --- | --- | --- |
| `/` | Legacy guest shell or property-enabled Intelligent Guest UI | `app/main.py`, `app/static/index.html` |
| `/{page_slug}` | Published, enabled, property-configured guest page deep link | `app/main.py`; startup and history in `app/static/app.js` |
| `/intelligent-ui/{asset_name}` | Allow-listed assets for the optional Intelligent Guest UI | `app/main.py` |
| Home | Property identity, greeting, hero, concierge CTA, published highlights, quick actions | `#home-view`; `renderHome` in `app/static/app.js` |
| Concierge | Conversation, suggested questions, composer, status/error, recommendations, links, actions | `#concierge-view`; `sendChat` and `renderMessages` in `app/static/app.js` |
| Explore | Published dining, facilities, events, promotions, recommendations, menus and map entry | `#explore-view`; `app/static/app.js` |
| Requests | Published service catalog, request confirmation, status and cancellation | `#requests-view`; `app/static/app.js` |
| My Stay | Stay verification/status, active requests, dining, events and preferences | `#stay-view`; `app/static/app.js` |
| Configured guest page | Published builder sections and configured actions at its own URL | `#custom-page-view`; `app/static/app.js` |

### Shared controls and interactions inspected

- Property identity, configured theme/branding, welcome hero, maintenance notice, intro experience, configured header/menu, configured or default bottom navigation.
- Chat composer, Enter/Shift+Enter, send/loading/error/retry and draft continuity, prompt suggestions, new conversation, privacy copy, personalization entry and settings.
- Hotel menu actions: property information, map, restaurant staff handoff, personalization, language, accessibility, privacy and help.
- Property-map dialog and markers/text labels; personalization dialog; native restaurant staff dialog.
- Explore filters/details/menu/directions, facility and restaurant cards, service request forms and confirmation, request status/cancel, configured builder actions.
- Guest entry and guest session resume; published home/restaurant/facility/map inventory; restaurant escalation; legacy chat and Intelligent Guest UI response rendering.

The existing [October 12–13 UI/UX audit](MASTER_UI_UX_REVIEW.md) and [guest premium review](GUEST_UI_PREMIUM_REVIEW_2026-10-13.md) were reviewed. Those reports recorded no physical iOS/Safari or screen-reader acceptance; this audit preserves that limitation.

## Findings

### ECC-GUEST-01 — Guest route/history state was incorrect — **P2, fixed locally**

**Root cause.** `setActiveView` only wrote history for custom page IDs, so navigation from a published custom page to a core guest view could leave the old URL in the address bar. The `popstate` handler also called `setActiveView` with its default history-writing behavior, which could add entries while processing Back/Forward.

**Change.** Core guest views now use their published slugs; Home uses `/`; `popstate` renders without pushing another entry.

**Files.** `app/static/app.js`; `tests/e2e/guest-audit-matrix.spec.js`; `app/static/index.html` cache version.

**Evidence.** The browser test enters `/guest-guide`, reloads, navigates to `/explore`, checks `history.state.guestPage`, traverses Back/Forward, reloads Explore, then returns Home and traverses Back. It passed in desktop Chromium and mobile Chrome emulation. See `capture configured synthetic guest views across the responsive matrix`.

### ECC-GUEST-02 — Menu-trigger focus was lost across dialogs — **P2, fixed locally**

**Root cause.** A configured header forwarded its click to the hidden default `#menu-button`. The menu action then captured/restored focus to the wrong control. The native restaurant dialog did not explicitly restore its initiating trigger or participate in the app's Tab boundary handling.

**Change.** Configured headers open the shared menu with their actual button as the return-focus target. Menu actions pass that target into dialogs. The restaurant dialog now has explicit Tab containment and close-focus restoration. Its heading is explicitly associated with the dialog for an accessible name.

**Files.** `app/static/app.js`; `app/static/index.html`; `tests/e2e/guest-premium.spec.js`.

**Evidence.** The browser test checks focus containment and restoration for Personalization, Property Map, and Restaurant Staff; checks `:modal` for the native dialog, its accessible name, inert behavior for custom dialogs, and restoration after Escape. Error routes check a readable live status for personalization failure and no background inert leak after a map outage. Desktop and mobile runs passed.

### ECC-GUEST-03 — Native staff dialog lacked an explicit accessible name — **P2, fixed locally**

**Root cause.** The `<dialog>` had a visible heading but no `aria-labelledby` relationship. The guest dialog contract should not depend on implicit browser naming heuristics.

**Change.** Added `aria-labelledby="restaurant-staff-title"` and an accessible-role assertion.

**Files.** `app/static/index.html`; `tests/e2e/guest-premium.spec.js`.

**Evidence.** `getByRole("dialog", { name: "Talk to Restaurant Staff" })` passes in the desktop and mobile guest runs.

### ECC-GUEST-04 — AI hotel facts are not deterministically grounded — **P1, open pilot blocker**

**Root cause.** `_chat_response` retrieves knowledge scoped to the current property and supplies hotel, guest, and optional live-place context to the configured model. The prompt asks the model not to invent facts, but `AIOutputValidator.validate` only rejects secret-shaped output and unverified transaction confirmations; otherwise it returns the model text unchanged. There is no post-generation evidence check for facilities, prices, availability, hours, or services.

**Reproduction/evidence.** Calling `AIOutputValidator.validate("The rooftop pool is open until 10 PM and day passes cost $45.")` returns that text unchanged. This confirms the validator cannot establish whether those claims exist in retrieved data. It does not prove a specific live provider will make that claim; no hotel AI credentials or production provider were exercised.

**Files changed.** None. A broad text heuristic would not safely verify arbitrary claims and could suppress legitimate answers; this needs a grounding design and provider-backed evaluation before the pilot gate can pass.

**Tests/evidence.** Full backend tests pass and verify empty-property facts, property scoping, and configured map/facility/action paths. The relevant current tests do not prove output grounding. See `app/llm.py`, `app/guardrails.py:487`, and `app/main.py:_chat_response`.

### ECC-GUEST-05 — GitHub browser check is red — **P1, unresolved CI blocker**

The GitHub Checks API for the audited SHA reports 10 jobs: **9 success, 1 failure**. The failing job is [`browser-tests`](https://github.com/jasongil003/Concierge.Ai/actions/runs/38348166556/job/115134286790); its functional Playwright step exited 1. The public annotations only show the generic process exit. Downloading the job log returned 403 and the Playwright report artifact returned 401, so the individual remote failing test could not be identified here.

**Files changed.** None for this remote status. It requires access to the job report or a clean rerun in GitHub Actions before the CI gate is cleared.

**Local comparison.** The final scoped guest suite passed locally on desktop and mobile. The full repository CI browser command was started locally and interrupted after the newly added test assertions exposed issues; after correcting those assertions, the complete scoped guest suites passed. This is useful local evidence but does not change the remote check result for the audited SHA.

## Intelligent concierge trace and scenario results

`POST /api/chat` resolves the guest session/property, searches `knowledge_management` and operations knowledge using that `property_id`, adds property and authorized guest context, conditionally searches nearby places under property guardrails, calls the configured property AI provider, then applies `AIOutputValidator`. The legacy guest renderer displays text and renders returned nearby places as interactive recommendation cards with details and directions.

The optional `/api/guest/intelligent-chat` adapter wraps the same chat service and adds property-scoped restaurant/facility card collections, a configured map component, request-review cards from the guest service catalog, and suggestion chips. General replies remain text blocks. Service requests require an explicit review/confirmation and backend verification before a persistent request record is created.

| Scenario | Result | Evidence and limit |
| --- | --- | --- |
| Restaurant query | **PASS, synthetic** | Existing restaurant recommendation/card/details/directions flows; property restaurant cards use guest-visible inventory. Live restaurant provider not exercised. |
| Hotel information | **PASS, configured data** | Guest menu hotel-information action and property-configured UI journey. General live-model factuality remains blocked by ECC-GUEST-04. |
| Local attractions | **PASS, synthetic stub** | Added backend test confirms attraction search context reaches the model for the current property; added browser test checks contextual result details and map target. No external Places provider was contacted. |
| Facility maps | **PASS, configured data** | Guest map view, markers and text alternative; map error path returns an accessible toast without leaking inert state. |
| Housekeeping/service request | **PASS, synthetic record** | Browser journey proposes, confirms, receives a request ID, displays status in My Requests, and cancels an active request. Existing backend tests cover property-scoped and idempotent creation. |
| Published inventory and empty property | **PASS locally** | Full backend suite; empty property UI; published data paths; cross-property session rejection and property-scoped inventory assertions. No fabricated inventory appears in empty UI states. |

## Responsive, visual and accessibility results

- Desktop screenshot matrix: Home, Concierge, Explore, Requests and My Stay plus a published custom page at **320, 375, 390, 430, 768, 1024, 1440 and 1920 px**. Empty-property screens were captured at 390 px. The responsive browser assertions check horizontal overflow and the composer/navigation relationship.
- Existing committed before/after evidence includes 93 screenshots. Representative comparisons: [Home 320 before](evidence/guest-premium-2026-10-13/before/home/320.png) → [after](evidence/guest-premium-2026-10-13/after/home/320.png); [Concierge 320 before](evidence/guest-premium-2026-10-13/before/concierge/320.png) → [after](evidence/guest-premium-2026-10-13/after/concierge/320.png); [Explore 1440 before](evidence/guest-premium-2026-10-13/before/explore/1440.png) → [after](evidence/guest-premium-2026-10-13/after/explore/1440.png); [empty Home 390](evidence/guest-premium-2026-10-13/after/empty-property/home/390.png); [custom page 1920](evidence/guest-premium-2026-10-13/after/custom-page/1920.png).
- Final local desktop matrix generated 53 PNGs under `/tmp/concierge-ecc-review-6d7c0b5/final-desktop`; the committed before/after evidence already retains the equivalent full matrix.
- Accessibility checks: Tab/Shift+Tab and Escape on each guest dialog; return focus; custom-dialog background inert toggling; native `showModal()` behavior; explicit staff dialog name; visible keyboard focus; privacy contrast ≥4.5:1 in tested themes; targeted touch sizes and composer boundaries. These are focused checks, not a complete WCAG audit.
- Console/page errors and failed network requests were asserted by the matrix and guest smoke journeys; none were recorded in the passing runs.
- Not assessed: screen readers, physical iOS/Safari/Android, real hotel content/branding, live AI and Places providers, proxy/captive network behavior, or production property provisioning.

## Test results

| Suite | Result |
| --- | --- |
| Full backend `pytest -q` | **1,134 passed, 18 skipped**, 2 dependency deprecation warnings; persistent SQLite safety check unchanged |
| Guest Playwright suite, desktop Chromium | **74 passed** |
| Guest Playwright suite, mobile Chrome / Pixel 7 emulation | **71 passed, 3 skipped** (responsive capture matrix and viewport metrics are Chromium-only; restaurant handoff test is skipped on mobile because it creates persistent conversation state) |
| JavaScript `node --check` for guest runtime and changed E2E specs | **PASS** |
| `git diff --check` | **PASS** |
| GitHub Actions on audited SHA | **FAIL** — `browser-tests`; other 9 checks pass |

## Changed local files

- `app/static/app.js` — route/history behavior and menu/dialog focus handling.
- `app/static/index.html` — accessible native dialog name and script cache version.
- `tests/e2e/guest-audit-matrix.spec.js` — direct custom/core route, refresh, Back/Forward and history-state regression.
- `tests/e2e/guest-premium.spec.js` — dialog focus/inert/error and session-continuity journeys.
- `tests/e2e/guest.spec.js` — synthetic local-attraction card and map-target journey.
- `tests/test_ai_context.py` — property-scoped live-place retrieval test using a synthetic stub.

## Final matrix

| Gate | Status |
| --- | --- |
| Guest views, responsive layout and key guest interactions | **PASS locally** |
| Custom page direct URL, refresh and browser history | **PASS after local fix** |
| Guest dialog focus, names, inert state and errors | **PASS after local fixes** |
| Inventory filtering, empty state, property scoping and request records | **PASS locally** |
| Contextual concierge UI and maps/actions | **PASS with synthetic providers/data** |
| Guarantee that the AI will not invent hotel facts | **FAIL / not established** |
| GitHub Actions `browser-tests` for this commit | **FAIL / individual test unavailable** |
| Full assistive-technology and physical-device acceptance | **NOT TESTED** |
| Real hotel pilot recommendation | **NO-GO** |
