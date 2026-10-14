# Guest UI acceptance

Date: 2026-10-14 (Asia/Manila)  
Reviewed commit: `6bc9fbba880389c08d8fc011383fc2274e632665`  
Browser run: Playwright, Chromium and Pixel 7 emulation; synthetic property data.

## Results

The full suite completed with **334 passed, 38 project-specific skips, and 0 failures**. The Chromium responsive matrix passed at all nine sizes: 1920×1080, 1440×900, 1280×720, 1024×768, 768×1024, 430×932, 390×844, 375×812, and 320×720. The Pixel 7 emulation suite passed its applicable mobile flows; desktop-only and matrix tests are intentionally skipped in that project.

Covered guest behavior includes navigation, retained drafts on errors, session restore and property switching, composer width and attachment, chronological messages, loading/error recovery, menu cards, service confirmation/status/cancellation, map search and routes, text alternatives, image fallback, no horizontal overflow, and no message/composer overlap. The request confirmation flow specifically maps “Can I have two extra pillows?” to “Extra Pillow,” then verifies explicit confirmation and a created response. The restaurant regression explicitly checks that menu details stay above the persistent composer at phone, tablet, and desktop widths.

## Fresh screenshots

All images below were captured during this run from synthetic fixture data and copied out of Playwright's temporary result directory. The large green image is fixture artwork, not a hotel photograph.

| View | Screenshot | What it shows |
|---|---|---|
| Mobile, 390×844 | [restaurant card and menu](evidence/guest-ui-acceptance-2026-10-14/restaurant-mobile-390x844.png) | Restaurant card, published menu, and composer remain separated on a phone-sized viewport. |
| Tablet, 768×1024 | [restaurant card and menu](evidence/guest-ui-acceptance-2026-10-14/restaurant-tablet-768x1024.png) | Card and persistent composer at tablet width. |
| Desktop, 1440×900 | [restaurant card and menu](evidence/guest-ui-acceptance-2026-10-14/restaurant-desktop-1440x900.png) | Assistant content remains aligned within the centered conversation column; composer stays below the response. |
| Desktop, 1280×900 | [verified pool answer](evidence/guest-ui-acceptance-2026-10-14/verified-pool-answer-desktop.png) | Published synthetic hours/location response and follow-up suggestions. |

The current control inventory is also saved at [control-inventory.json](evidence/guest-ui-acceptance-2026-10-14/control-inventory.json). It covered 42 admin destinations, 5 guest views, and 2,125 visible control instances; it found 0 enabled non-focusable controls and 0 controls missing accessible names. It is an inventory with keyboard-entry validation; it does not claim every button was behaviorally clicked.

## Visual findings and remaining limits

- No reproducible layout defect appeared in the fresh browser run. Automated checks found no horizontal overflow, composer overlap, missing navigation, test console errors, or failed guest requests.
- The checked guest response remains left-aligned, guest messages right-aligned, and the composer remains available below the message/card content at mobile and desktop widths.
- Screenshots use synthetic hotel and restaurant records. They do not verify a hotel's imagery, menu pricing, opening hours, availability, or content rights.
- The browser run used desktop Chromium and Pixel 7 emulation only. Physical iOS/Android devices, Safari, screen readers, voice control, and captive mini-browsers were not tested.
- No live AI provider was called. The tested response content is deterministic fixture-backed property data, not evidence of live model quality.
