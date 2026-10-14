# ECC guest experience audit

**Audit baseline:** `codex/guest-concierge-premium-2026-10-13` at `82f9df2bafb4b3a632912762364fd6c7dff4a532`, 14 October 2026. This report covers local code and isolated synthetic tests. Earlier screenshots and reports were used as leads, not proof of the current build. No live hotel data or remote system was used.

## Evidence and scope

- The guest entry route chooses the streamed shell only when the environment master flag, global operational flag, and property flag all allow it; otherwise it serves the legacy shell (`app/main.py:1262-1283`, `app/main.py:527-555`). Both paths matter to release readiness.
- Local command: `.venv/bin/python -m pytest -q tests/test_guest_grounding.py tests/test_guest_personal_home.py tests/test_restaurant_workflows.py tests/test_floor_map_upload_security.py tests/test_intelligent_ui.py` — **67 passed**, 2 dependency deprecation warnings. The test harness reported the persistent `state/concierge.db` and journal files unchanged (`tests/conftest.py:11-69`). These are backend checks, not physical phone or browser evidence.
- Browser evidence: final `npm run test:e2e -- --grep-invert @visual` completed **332 passed, 38 skipped, 0 failed** across desktop Chromium and Pixel 7 mobile Chrome emulation. The new long-reply regression also passed separately in both projects (`npx playwright test tests/e2e/guest-scrollbar.spec.js --project=chromium --grep 'newly completed long reply'`: **1 passed**; same command with `--project=mobile-chrome`: **1 passed**). Both use a disposable local server and synthetic property data.

## Conversational behavior

| Query or workflow | Result supported by current evidence | Evidence and remaining limit |
|---|---|---|
| Hotel facts, checkout, policies | Property-scoped structured and published knowledge retrieval is implemented; unsupported claims use a contact fallback. **Backend verified.** | `app/main.py:6180-6360`, `tests/test_guest_grounding.py`, `tests/test_intelligent_ui.py:847-920`. Actual provider wording and every possible language remain unverified. |
| “I'm hungry”, dining, menu, follow-up | The streamed adapter builds restaurant and published menu cards, uses recent restaurant context, and checks source freshness. **Backend verified.** | `app/main.py:6628-6648`, `app/main.py:7000-7130`, `tests/test_intelligent_ui.py:353-603`, `tests/test_restaurant_workflows.py`. |
| “What's open now?” | Static `live_status`/`status` gates dining results. **Partially implemented.** | `_guest_relevant_restaurants` filters `status == "open"` at `app/main.py:7821-7886`; `hospitality.guest_facilities` returns configured hours and status at `app/hospitality.py:1668-1710`. The code does not calculate current opening from the hours and property timezone. The label “open now” therefore needs a trusted live status feed or a validated, timezone-aware schedule before it can be considered reliable. |
| Swimming pool, maps, directions | Property floor maps, guest-visible markers and published route nodes are implemented; missing route data produces an explicit fallback. **Backend verified; browser unverified.** | `app/main.py:1459-1570`, `app/main.py:6740-6840`, `tests/test_intelligent_ui.py:191-291`, `tests/test_intelligent_ui.py:921-1039`, `tests/test_roadmap_foundation.py:27-76`. |
| Extra pillows, towels, housekeeping, maintenance | Clear action phrases use a configured service proposal and require explicit confirmation. Confirmed requests persist with an idempotency key. **Backend verified.** | `app/main.py:1728-1842`, `app/main.py:8502-8526`, `tests/test_intelligent_ui.py:1214-1224`, `tests/test_service_catalog.py:38-120`. Unknown services fall back to a truthful message. |
| Request tracking | A guest session can retrieve its recent requests and the streamed UI has a typed status block. **Backend verified.** | `app/main.py:1647-1654`, `app/main.py:6705-6738`, `tests/test_intelligent_ui.py:114-190`. No real staff fulfillment cycle was exercised. |
| Nearby places | Structured recommendation and optional live place paths exist. **Partially implemented.** | `app/main.py:1609-1614`, `app/main.py:6360-6590`, `tests/test_intelligent_ui.py:124-165`; external data freshness, quota behavior, and provider correctness were not exercised. |

## Dynamic content and tenant scope

Admin-managed hotel and hospitality content is stored by property. Guest facility retrieval uses property-bound SQL; menu items require an active, published menu and available item; promotions require a published state and current validity window (`app/hospitality.py:1668-1710`). The guest menu route also checks that the parent restaurant is active and strips internal fields (`app/main.py:1579-1600`). Tests exercise property isolation, publication, archived inventory, and cross-property request denial (`tests/test_intelligent_ui.py:353-920`, `tests/test_service_catalog.py:175-260`). An admin edit followed by a real browser chat response was **not** performed in this audit stream.

Map records and floor-map assets are property scoped (`app/main.py:1459-1535`, `app/main.py:1560-1577`). The map answer explicitly avoids claiming a route when no validated route graph is present (`app/main.py:6749-6840`). This is the correct safety behavior; complete wayfinding depends on hotel-specific map publication and route graph setup.

## UI and mobile findings

- The newer UI implements bounded SSE event parsing, typed components, conversation history, scroll anchoring, and guest-session error recovery (`app/guest_v2/app.js:65-210`, `app/guest_v2/app.js:1498-1580`, `app/guest_v2/app.js:1625-1698`). Backend tests verify its protocol, but this audit stream has not yet validated layout on mobile Chromium or iPhone WebKit.
- **Verified and fixed P2 scroll defect:** `renderMessages` scrolled `.conversation-region` while CSS made `#concierge-view .conversation-column` the actual scroll container (`app/static/app.js:1391-1426`, `app/static/styles.css:2963-2968`). The prior near-bottom check also ran after replacing the message list. At 390×700 Chromium, the before capture cut off the newest reply above the composer: [before](evidence/guest-scroll-before-390x700-chromium.png). The fix records the actual scroller's position before rendering and scrolls it after the DOM update. The [after capture](evidence/guest-scroll-after-390x700-chromium.png) shows the final line above the composer, and the focused assertion passed in Chromium and Pixel 7 emulation. This evidence closes the reproduced long-reply visibility case, not every historic layout concern.
- Existing responsive and accessibility browser tests in `tests/e2e/guest-premium.spec.js` and `tests/e2e/guest-scrollbar.spec.js` passed as part of the functional browser suite where selected. Physical iPhone Safari, Android Chrome, software keyboard interaction, captive mini-browser behavior, and screen reader use remain **unverified**.
- The legacy composer lives in the conversation card and CSS gives the conversation column a dedicated scroll region (`app/static/styles.css:2952-2999`). The fresh 390×700 screenshots show no message text overlapping the composer in this long-reply case; broader visual alignment and accessibility acceptance still need device and assistive-technology checks.

## Release impact and next verification

1. Exercise a synthetic admin content edit through the UI, then verify a new guest answer reflects the new published record and no draft content leaks.
2. Define a trustworthy opening-hours interpretation with property timezone or a live status feed before advertising “open now” as a calculated fact.
3. Run a physical-device and screen-reader pass. Those results cannot be inferred from emulation.
