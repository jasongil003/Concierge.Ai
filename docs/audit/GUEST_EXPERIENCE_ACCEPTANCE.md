# Guest experience acceptance

**Starting HEAD:** `e4bbd7493fe9d90a513d8224749b54c9e25ddc90`
**Implementation and tested commit:** `a30f95eb8db2ff05151c3473e453f9f38d0dec2d`
**Earlier audit code baseline:** `d5d006e89c38c0d901256d545679fee753175ef8`
**Date:** 2026-10-14 (Asia/Manila)
**Test data:** synthetic property content and isolated temporary SQLite. No hotel-approved content or live provider was available.

## Results

| Journey | Result | Evidence |
|---|---|---|
| Load home, navigate Home/Explore/Requests/My Stay/Concierge, submit chat, retain drafts on failure | **PASS in browser emulation** | `tests/e2e/guest.spec.js:217-280,526-778`; `app/static/app.js:150-220`. |
| Keep a persistent composer usable across mobile, tablet and desktop; maintain chat scroll anchor | **PASS in Chromium and Pixel 7 emulation** | `tests/e2e/guest.spec.js:614,2218-2266,2394-2501`; `tests/e2e/guest-premium.spec.js:390-472`. Full responsive view matrix: all 9/9 Chromium sizes passed in the full suite. |
| Resume session on reload and reject cross-property replay or expired/revoked credentials | **PASS in isolated tests** | `tests/e2e/guest-premium.spec.js:257-365`; `tests/e2e/guest.spec.js:2496-2605`; backend session regressions. |
| Show restaurant cards, published menu items/prices, configured hours, maps and directions | **PASS for synthetic published fixtures** | `tests/e2e/guest.spec.js:922-1008,1374-1966`; backend guest grounding tests. The fixtures prove rendering and retrieval paths, not actual property truth. |
| Build a guest-service proposal, require confirmation, persist it, show reference/status and allow cancellation | **PASS for local synthetic request workflows** | `tests/e2e/guest.spec.js:1090-1158,1277-1373,2017-2198`; API routes in `app/main.py:1729-1848`. Repeating the same proposal returns the existing ticket, and concurrent calls with the same idempotency key create one ticket (`tests/test_guest_personal_home.py`, `tests/test_service_catalog.py`). No fulfillment is implied. |
| Property-map graph, multi-floor directions, accessible routes and text alternative | **PARTIAL** | Synthetic graph and map tests pass (`tests/e2e/guest.spec.js:1374-1960`). Actual building/floor geometry, accessible paths, and route accuracy need owner-provided maps and site review. |
| Requested contextual sequence across turns | **PASS for deterministic synthetic content; live acceptance PARTIAL** | `tests/test_intelligent_ui.py::test_restaurant_menu_and_location_followups_keep_the_unique_property_selection` exercises “I'm hungry.” → “Do you have Japanese food?” → “Show me the menu.” → “Where is it?” with two property-scoped restaurants. The menu response includes only the Japanese restaurant's published item, description, price and image URL; the final response returns its published lobby location and says indoor routing is not configured. The exact flow now passes locally without a live AI provider. Approved hotel content, real images and live provider quality remain unverified. |

## Truth and content rules

Guest cards and structured responses are scoped to the property records available in local test fixtures. Do not use synthetic menu prices, images, hours, availability, locations, or policies as hotel facts. Published menu filtering, configured business hours, and map links have local automated coverage; content accuracy and rights require property approval. When a facility has no approved indoor geometry, the product must not invent coordinates or a route; the property owner must supply the authoritative map before navigation is accepted.

## Device and accessibility limits

The full Playwright suite passed with 334 tests passed and 38 expected project-specific skips across Chromium and Pixel 7 emulation. Automated journeys, responsive layouts, focus containment/restoration, touch-target/layout assertions, and privacy copy checks passed. There was no physical iPhone/iPad, Android handset, Safari, screen reader, voice-control, captive mini-browser, or hardware-keyboard test. This is not a complete WCAG audit.
