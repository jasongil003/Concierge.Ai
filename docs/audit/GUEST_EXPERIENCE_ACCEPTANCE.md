# Guest experience acceptance

**Audit target:** `d5d006e89c38c0d901256d545679fee753175ef8`  
**Date:** 2026-10-14 (Asia/Manila)  
**Test data:** synthetic property content and isolated temporary SQLite. No hotel-approved content or live provider was available.

## Results

| Journey | Result | Evidence |
|---|---|---|
| Load home, navigate Home/Explore/Requests/My Stay/Concierge, submit chat, retain drafts on failure | **PASS in browser emulation** | `tests/e2e/guest.spec.js:217-280,526-778`; `app/static/app.js:150-220`. |
| Keep a persistent composer usable across mobile, tablet and desktop; maintain chat scroll anchor | **PASS in Chromium and Pixel 7 emulation** | `tests/e2e/guest.spec.js:614,2212-2260,2388-2495`; `tests/e2e/guest-premium.spec.js:381-472`. Full responsive view matrix: 9/9 passed after the favicon correction. |
| Resume session on reload and reject cross-property replay or expired/revoked credentials | **PASS in isolated tests** | `tests/e2e/guest-premium.spec.js:257-365`; `tests/e2e/guest.spec.js:2496-2605`; backend session regressions. |
| Show restaurant cards, published menu items/prices, configured hours, maps and directions | **PASS for synthetic published fixtures** | `tests/e2e/guest.spec.js:922-1008,1374-1960`; backend guest grounding tests. The fixtures prove rendering and retrieval paths, not actual property truth. |
| Build a guest-service proposal, require confirmation, persist it, show reference/status and allow cancellation | **PASS for local synthetic request workflows** | `tests/e2e/guest.spec.js:1090-1158,1277-1373,2011-2192`; API routes in `app/main.py:1729-1848`. No fulfillment is implied. Duplicate request idempotency and a live staff workflow remain unverified. |
| Property-map graph, multi-floor directions, accessible routes and text alternative | **PARTIAL** | Synthetic graph and map tests pass (`tests/e2e/guest.spec.js:1374-1960`). Actual building/floor geometry, accessible paths, and route accuracy need owner-provided maps and site review. |
| Requested contextual sequence across turns | **NOT ACCEPTED** | The application has guest context/grounding and separate tests for restaurant selection, menus, published facts and directions. No test or live provider run demonstrates the exact sequence “I'm hungry” → Japanese restaurants → actual menu → “Where is it?” without restating the venue. Treat the whole feature as **PARTIAL** until that acceptance passes with approved content and a supported provider. |

## Truth and content rules

Guest cards and structured responses are scoped to the property records available in local test fixtures. Do not use synthetic menu prices, images, hours, availability, locations, or policies as hotel facts. Published menu filtering, configured business hours, and map links have local automated coverage; content accuracy and rights require property approval. When a facility has no approved indoor geometry, the product must not invent coordinates or a route; the property owner must supply the authoritative map before navigation is accepted.

## Device and accessibility limits

Automated Chromium and Pixel 7 emulation passed the exercised journeys, responsive layouts, focus containment/restoration, touch-target/layout assertions, and privacy copy checks. There was no physical iPhone/iPad, Android handset, Safari, screen reader, voice-control, captive mini-browser, or hardware-keyboard test. This is not a complete WCAG audit.
