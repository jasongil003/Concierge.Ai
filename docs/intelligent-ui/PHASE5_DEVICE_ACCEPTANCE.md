# Phase 5 device and accessibility acceptance

## Local evidence and boundary

The Playwright suite runs desktop Chromium and Pixel 7 mobile emulation against an isolated local test server. The restaurant Details race regression passed repeated desktop and mobile-emulation runs. This is not physical iPhone/Android, Safari, tablet, captive browser, QR/NFC, or screen-reader testing. Automated DOM checks are not a WCAG 2.2 AA conformance claim.

The current host has no connected physical device or hotel captive portal. Those checks remain **BLOCKED** pending target devices and access.

## Required manual acceptance

For each target device/browser, use a synthetic property and approved test guest:

1. Enter through the actual QR and NFC links; verify the expected guest hostname, TLS, property and guest-session binding.
2. Verify first load, refresh, back/forward navigation, session continuity, expiry and logout/revocation behavior.
3. Open the concierge and legacy guest UI; confirm server feature-flag disable falls back safely.
4. Use mobile keyboard and screen orientation changes. Verify composer visibility, scroll, send/cancel behavior and no blocked action behind the keyboard.
5. Open a restaurant Details panel during a slow response; confirm one card, expanded/collapsed state, correct accessible name, focus and no stale card after response completion.
6. Check streaming text, interruption, retry and fallback; ensure no duplicate service action. Action requests must still require explicit signed confirmation.
7. Test keyboard-only navigation, visible focus, VoiceOver/TalkBack announcements, headings, contrast, touch target size and reduced-motion preference. Record the specific WCAG 2.2 AA criterion, environment, result and defect for each issue.
8. Repeat within the actual captive browser and property Wi-Fi path. Verify guest hostname allowlisting and session isolation without exposing another property's data.

Record device model/OS/browser version, viewport, network/captive portal, build SHA, test property, steps, screenshots with synthetic data only, and pass/fail. Do not mark emulation as device acceptance.
