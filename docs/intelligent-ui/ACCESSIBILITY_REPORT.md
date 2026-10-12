# Intelligent UI accessibility and responsive review

## Evidence

The final Playwright run covers desktop Chromium and emulated Pixel 7 Chrome. Existing responsive checks exercise 320, 375, 390, 430, 768, 1024, 1440, and 1920 pixel widths. The Intelligent UI captures welcome and conversation screenshots for desktop and mobile; the map browser regression verifies native marker buttons, `aria-label`, `aria-pressed`, a live selected-location label, image alt text, and a text list of marker names. Map images are lazy-loaded and stay same-origin.

The repository's manual control inventory reports 2,113 visible control instances, 2,078 focusable controls, zero enabled controls missing keyboard focus, zero missing accessible names, and no invalid composite widgets for its Chromium run. Existing tests also cover focus state, keyboard entry points, reduced motion, and mobile navigation. The screenshots were manually inspected in this assessment: content remains legible, the composer stays anchored, and no horizontal overflow is visible in the captured states.

## Limits

These checks are not a full WCAG conformance audit and do not include an axe-core scan or screen-reader testing. Pixel 7 is browser emulation, not a physical phone. Desktop Safari, iPhone Safari, Android physical hardware, hotel captive browsers, voice control, and high-contrast operating-system settings were not available. The mobile welcome screen intentionally uses generous vertical whitespace; the composer remains visible at the bottom.

Screenshots: `screenshots/welcome-chromium.png`, `screenshots/conversation-chromium.png`, `screenshots/map-chromium.png`, `screenshots/welcome-mobile-chrome.png`, and `screenshots/conversation-mobile-chrome.png`.
