# Guest UI premium review — 2026-10-13

## Scope and baseline

- Latest `origin/main` was fetched at `9e9c018a48d9cd720ce4e242380ef6b6710f33c1`; the dedicated branch is `codex/guest-concierge-premium-2026-10-13`.
- Reviewed guest-facing criteria A-01–A-37 in [the master feature acceptance matrix](MASTER_FEATURE_ACCEPTANCE_MATRIX.md), including property branding, responsive navigation, concierge, Explore, My Stay, requests, accessibility, mobile keyboard behavior, and layout defects. Also reviewed the [October 12–13 master UI/UX audit](MASTER_UI_UX_REVIEW.md), which recorded 283 passes, 35 skips, and no failures in its then-current run. It called out the absence of physical-device and screen-reader acceptance. This review retains those limits and adds the empty-property, direct-route, and premium presentation cases below.
- The app ran against Playwright’s temporary SQLite database. Property names, guest content, artwork, and requests in retained screenshots are synthetic. The custom test design was restored after the route test. No production database, backend implementation, deployment, push, merge, or commit was touched.

## Guest inventory

### Routes and views

| Route or view | Behavior | Source |
| --- | --- | --- |
| `/` | Serves the property’s legacy shell or its enabled Intelligent Guest UI shell | `app/main.py:1240` |
| `/intelligent-ui/{asset_name}` | Serves allow-listed Intelligent Guest UI assets | `app/main.py:1255` |
| `/{page_slug}` | Serves the shell for an enabled, published single-segment guest page | `app/main.py:7758` |
| Home | Welcome, configured hero, quick actions, published highlights, request summary, concierge entry | `app/static/index.html:38`; rendering in `app/static/app.js:847` |
| Explore | Published dining, facilities, events, promotions, recommendations, menus, details, directions and map entry | `app/static/index.html:85`; `app/static/app.js:1170` |
| Requests | Service catalog, request actions, confirmation, current status, and cancellation | `app/static/index.html:98`; `app/static/app.js:1040` |
| My Stay | Stay verification/status, active requests, dining and upcoming events | `app/static/index.html:112`; `app/static/app.js:1279` |
| Concierge | Conversation, suggestions, composer, response states, links, structured actions, and staff handoff | `app/static/index.html:120`; `app/static/app.js:1389` |
| Published custom guest page | Property-configured sections and actions, including direct URL entry | `app/static/index.html:81`; `app/static/app.js:179`; server route in `app/main.py:7758` |

### Shared controls and interactions

- Property header, configured branding, maintenance notice, hotel menu, configured navigation or five-item bottom navigation, and the optional first-visit intro (`index.html:30–36, 176–247`; `app.js:148–225, 2586–2632, 2690–2743`).
- Concierge message list, suggested prompts, new conversation, text/voice/attachment affordances when enabled, composer shortcuts, send/loading/error states, retry/draft retention, proposal review and confirmation cards (`index.html:120–175`; `app.js:996–1038, 1389–1830`).
- Property map modal with marker selection and text labels; guest-controlled preferences modal with level, add/edit/clear/disable actions; restaurant staff request dialog with restaurant selection and request status (`index.html:249–318`; `app.js:2217–2308, 2438–2584`).
- Explore details and menu expansion, restaurant directions, map access, request forms and confirmation/cancel, preferences, privacy/help/language/accessibility menu actions, and configured page actions (`app.js:542–757, 1040–1275, 2317–2440`).
- Guest data interactions are backed by the existing home, request, personalization, facilities, restaurant/menu, service catalog, recommendation, zone/map/route, proposal/confirmation, service-request/cancel, staff-message/escalation, and chat/history endpoints (`app/main.py:1422–1815, 6656–6685`). Backend code was not changed.

## Confirmed issues and corrections

| Confirmed issue | Root cause | Correction |
| --- | --- | --- |
| No clear concierge action on the legacy home or on configured hero sections that omitted one | Home relied on navigation or property-authored hero buttons | Added a direct “Ask your concierge” action while retaining property-authored actions (`index.html:55`; `app.js:156, 584–598`). |
| Empty property home read as an accidental blank | Empty sections were hidden without a property-discovery explanation | Added a concise empty state only when no published highlights exist (`app.js:117–142, 852–856, 987–990`). |
| My Stay could imply a verified hotel service relationship when none was linked | Unknown stay status fell back to “Guest services available” | Replaced it with “No verified stay linked”; checked-in and checked-out states remain explicit (`app.js:1287–1295`). |
| Concierge suggestions disappeared when a property had no valid configured prompts | The renderer returned an empty list, and malformed/incomplete prompts were not filtered | Filtered invalid prompts and supplied neutral questions about information the property has published (`app.js:1349–1360`). |
| Small-screen chat header/composer and privacy disclosure were cramped; privacy copy was too small and low-contrast | Narrow layout retained a horizontal header and unused composer grid track; privacy text inherited muted 10px styling | Stacked the header below 360px, compacted the composer, improved disclosure size/color, and set guest action targets to at least 44px (`styles.css:3170–3223`). |
| Map and personalization dialogs did not contain keyboard focus or reliably restore it on close | The custom modal shells only toggled visibility | Added focus containment, inert background handling, escape close, and return-focus restoration (`app.js:2221–2260, 2288–2320, 2538–2584`). |
| One-card desktop Explore sections left half the grid empty | A two-column list did not adapt when only one verified item existed | Let a single card span the available row (`styles.css:2359`). |
| Published custom guest URLs opened Home instead of the requested page | Startup called `setActiveView("home")` before loading property page config, and that call replaced the current path with `/` | Startup now sets the initial visible view without changing history; user navigation still updates routes (`app.js:176, 179–208`). The regression test publishes a synthetic page, enters its real URL, and verifies it at all eight widths. |

## Before and after

The baseline captures were made from the fetched base branch before edits. The after set was regenerated from the final UI. Each core comparison below is a full-page Chromium capture; captures use the same viewport dimensions and synthetic property setup.

| View | Before | After |
| --- | --- | --- |
| Home, 320px | [before](evidence/guest-premium-2026-10-13/before/home/320.png) | [after](evidence/guest-premium-2026-10-13/after/home/320.png) |
| Concierge, 320px | [before](evidence/guest-premium-2026-10-13/before/concierge/320.png) | [after](evidence/guest-premium-2026-10-13/after/concierge/320.png) |
| Explore, 1440px | [before](evidence/guest-premium-2026-10-13/before/explore/1440.png) | [after](evidence/guest-premium-2026-10-13/after/explore/1440.png) |
| Empty property, 390px | — | [Home](evidence/guest-premium-2026-10-13/after/empty-property/home/390.png), [Explore](evidence/guest-premium-2026-10-13/after/empty-property/explore/390.png), [Requests](evidence/guest-premium-2026-10-13/after/empty-property/requests/390.png), [My Stay](evidence/guest-premium-2026-10-13/after/empty-property/stay/390.png), [Concierge](evidence/guest-premium-2026-10-13/after/empty-property/concierge/390.png) |
| Published custom page, all widths | Not present in the baseline fixture | [After captures](evidence/guest-premium-2026-10-13/after/custom-page/) |

The evidence directory retains 40 baseline screenshots, 40 after screenshots for the five core views, eight direct custom-page screenshots, and five empty-property screenshots (93 PNGs, about 7.6 MB total). The configured hero image in the after matrix is a synthetic SVG, not hotel photography.

## Changed files

- Guest shell and cache-busted JavaScript: `app/static/index.html`.
- Guest rendering, startup route preservation, truthful empty/stay states, valid starter prompts, property concierge label, and dialog focus management: `app/static/app.js`.
- Guest-specific layout, readable disclosure, minimum action sizing, narrow-chat adjustments, and reduced-motion behavior: `app/static/styles.css`.
- Guest empty-state, direct CTA, reload continuity, two-property session boundary, theme, focus, layout, contrast and touch-target journeys: `tests/e2e/guest-premium.spec.js`.
- Responsive screenshot matrix with an isolated published guest page and synthetic property content: `tests/e2e/guest-audit-matrix.spec.js`.
- Intentional updated guest-home visual golden: `tests/e2e/visual.spec.js-snapshots/guest-home-chromium-darwin.png`.
- Retained baseline and after screenshots: `audit/evidence/guest-premium-2026-10-13/`.
- This report: `audit/GUEST_UI_PREMIUM_REVIEW_2026-10-13.md`.

## Playwright and accessibility results

- Chromium guest-focused suite: **73 passed**. It includes the existing guest journeys, visual snapshots, property-context checks, the custom-route regression, guest request cancellation, cross-property session rejection, and the viewport matrix.
- Mobile Chrome / Pixel 7 emulation guest suite: **68 passed, 2 skipped**. The viewport matrix intentionally runs only once in Chromium; the restaurant-staff request test is not enabled in this mobile project.
- Responsive matrix: five core guest views plus one published custom guest page at **320, 375, 390, 430, 768, 1024, 1440 and 1920px**. Assertions cover page/body horizontal overflow; configured populated home data is awaited before capture. The empty property is also captured at 390px.
- Functional checks cover navigation, guest session reload continuity, two mapped property hostnames (the prior session is rejected and replaced on the second property), current property themes, direct custom-page entry, prompt action, restaurant details/directions, maps, guest request creation/tracking/cancellation, errors/outages, and visual baselines.
- Accessibility checks found visible keyboard focus; modal Tab/Shift+Tab containment, Escape close and focus restoration; privacy disclosure contrast of at least 4.5:1 in the tested synthetic theme; and controls at least 24 CSS pixels in the tested concierge/nav/composer surfaces. CSS gives key guest actions 44px minimum height and mobile navigation 56px.
- These are focused browser checks, not a complete WCAG audit. No physical Safari/iOS device, screen reader, voice-control, or hardware keyboard run was performed.

Commands used:

```sh
GUEST_UI_AUDIT_DIR=audit/evidence/guest-premium-2026-10-13/after npx playwright test \
  tests/e2e/guest.spec.js tests/e2e/guest-privacy.spec.js \
  tests/e2e/guest-scrollbar.spec.js tests/e2e/property-context.spec.js \
  tests/e2e/visual.spec.js tests/e2e/guest-premium.spec.js \
  tests/e2e/guest-audit-matrix.spec.js --project=chromium

npx playwright test tests/e2e/guest.spec.js tests/e2e/guest-privacy.spec.js \
  tests/e2e/guest-scrollbar.spec.js tests/e2e/property-context.spec.js \
  tests/e2e/guest-premium.spec.js --project=mobile-chrome
```

## Remaining limitations and release recommendation

- The browser fixtures use synthetic inventory and artwork; confirm the real property’s published content, brand fonts/colors, logo, and supplied hero photography before approving a guest-facing pilot.
- Chromium desktop and Pixel 7 emulation do not establish Safari/iOS, physical-device safe-area, captive-network reopen, assistive-technology, or localized-content acceptance.
- The cross-property check verifies a rejected and restarted guest session across two synthetic host mappings. Production DNS, reverse-proxy and property-domain configuration still need an environment-specific pilot check.
- Empty/loading/error content and major guest actions were exercised, but every property-authored layout combination, unusual theme contrast, and arbitrary custom builder composition was not visually sampled exhaustively.

**Recommendation:** approve this branch for product/brand review and staging validation. Do not recommend production release until a representative property’s real branding/content and the supported physical browser/accessibility environment pass acceptance. The branch is intentionally uncommitted and unpushed; no deployment or merge was performed.
