# Real-device acceptance checklist

**Status: NOT TESTED.** No physical iPhone or Android handset was available during the local QA run. Every row below remains `NOT TESTED` until a human completes it on the named device and records evidence. Browser emulation and Playwright do not satisfy this checklist.

## Test record

- Property / staging environment: ______________________________
- Tester and date/time: _______________________________________
- iPhone model / iOS version / carrier: _________________________
- Android model / Android version / browser: ____________________
- Wi-Fi SSID / VLAN (do not record its password): ________________
- Guest hostname / certificate expiry: __________________________
- Build / commit: _____________________________________________
- Evidence location (redact guest credentials and personal data): ____

## iPhone

For each row: connect the named iPhone to the test hotel's guest Wi-Fi, follow the steps literally, record the observed result, and change status only to `PASS` or `FAIL` with evidence.

| Check | Exact steps and expected result | Status |
|---|---|---|
| Hotel Wi-Fi association | Forget the test SSID, join it with the approved test profile, and confirm the device receives the expected guest-network address without reaching management resources. | NOT TESTED |
| Captive portal detection | With Safari closed, join the SSID and confirm iOS displays its captive-network prompt for the configured Concierge portal. | NOT TESTED |
| Pseudo-browser launch | Tap the captive-network prompt; confirm the portal renders without a blank page, certificate warning, or forced external-browser dependency. | NOT TESTED |
| QR entry | Close the portal, scan the property's printed test QR code with Camera, open the detected guest URL, and confirm the same property is selected. | NOT TESTED |
| NFC entry, when installed | Tap the approved test NFC tag and confirm it opens the same property URL as the QR code. If no NFC tag is deployed, record `NOT APPLICABLE` and why; do not call it a pass. | NOT TESTED |
| Authentication | Complete the configured staging authentication flow with a disposable guest account; verify the gateway accepts it and the app does not display unsupported methods. | NOT TESTED |
| Guest interface | Check hotel identity, language, text scaling, navigation, menus, maps, privacy notice, and request controls in the actual iOS portal/browser. | NOT TESTED |
| Session continuation | Start a guest session, leave the page, return using the issued guest entry, and confirm the same valid session resumes without crossing accounts. | NOT TESTED |
| Reopen captive portal | Close the pseudo-browser, reopen the captive portal from Wi-Fi settings, and confirm the configured session resumes or displays the documented sign-in state. | NOT TESTED |
| Browser transition | Use the portal's open-in-browser transition if present; verify hostname, TLS, property, session, and guest functionality remain correct. | NOT TESTED |
| Logout | Sign out, revisit/back-navigate to the guest interface, and confirm the prior authenticated session cannot perform protected guest actions. | NOT TESTED |
| Expired session | Use a staging session with the configured short test expiry, wait for expiry, and confirm protected actions fail closed with a clear re-entry path. | NOT TESTED |
| HTTPS and TLS | Inspect the actual guest URL and certificate in Safari; verify valid name, chain, dates, and HTTPS redirect. Record the certificate fingerprint and expiry, not private keys. | NOT TESTED |
| Property selection/isolation | Use two staging properties and their assigned domains; confirm each host resolves only to its own property and changing a request parameter cannot select the other. | NOT TESTED |
| Restaurant menu | Open a published test restaurant and confirm its current menu and item details match the admin configuration. | NOT TESTED |
| Guest request | Submit one clearly labeled disposable test request, verify its confirmation and property/restaurant assignment, then close it through the authorized staff workflow. | NOT TESTED |
| AI assistant | Ask a non-sensitive property question and an unsupported question; verify the answer uses only approved property information and degrades safely when the provider is unavailable. | NOT TESTED |
| Orientation change | Rotate portrait to landscape and back on the live interface; confirm controls remain visible, usable, and free of horizontal clipping. | NOT TESTED |
| Background/foreground | Background the portal/browser for at least one minute, return, and verify session, entered state, keyboard, and focus behavior. Repeat after a longer staging interval. | NOT TESTED |

## Android

Repeat each case on a physical Android handset using the deployed guest Wi-Fi and the stated browser. Record the browser and Android build; emulator results do not qualify.

| Check | Exact steps and expected result | Status |
|---|---|---|
| Hotel Wi-Fi association | Forget the test SSID, join using the approved test profile, and confirm the expected guest-network address and isolation from management resources. | NOT TESTED |
| Captive portal detection | Join with Chrome closed; confirm Android's captive-portal notification appears and names/opens the configured portal. | NOT TESTED |
| Pseudo-browser launch | Tap the notification and confirm the portal loads without certificate warning, blank page, or broken navigation. | NOT TESTED |
| QR entry | Scan the property's test QR with the camera/QR scanner and confirm it opens the matching property guest URL. | NOT TESTED |
| NFC entry, when installed | Tap the approved test NFC tag; confirm it opens the same property URL. If no NFC tag is deployed, record `NOT APPLICABLE` and why. | NOT TESTED |
| Authentication | Complete the supported staging gateway flow with a disposable account; confirm only configured authentication methods are shown. | NOT TESTED |
| Guest interface | Check property identity, navigation, text scaling, contrast, restaurant/menu, service request, assistant, privacy, and keyboard behavior. | NOT TESTED |
| Session continuation | Start a session, leave the portal, return via the same guest entry, and verify the valid session resumes for the same property. | NOT TESTED |
| Reopen captive portal | Close the pseudo-browser and reopen the portal from Wi-Fi settings; verify documented session-resume behavior. | NOT TESTED |
| Browser transition | Open the guest URL in Chrome if prompted; confirm TLS, hostname, property, and session continuity. | NOT TESTED |
| Logout | Sign out, use browser back/reopen, and confirm protected guest operations require a new valid session. | NOT TESTED |
| Expired session | Wait for the staging expiry and confirm protected operations fail closed with a clear recovery path. | NOT TESTED |
| HTTPS and TLS | Inspect the real hostname and TLS certificate in Chrome; verify name, chain, dates, redirect, and no mixed-content warning. | NOT TESTED |
| Property selection/isolation | Test two staging properties and attempt an unauthorized property ID; confirm the other property's content is never returned. | NOT TESTED |
| Restaurant menu | Open a published test restaurant and compare its menu and items with admin configuration. | NOT TESTED |
| Guest request | Submit one labeled disposable request, verify confirmation and correct property/restaurant routing, then resolve it through staff. | NOT TESTED |
| AI assistant | Test a verified property question, unsupported question, and provider outage behavior without entering personal data. | NOT TESTED |
| Orientation change | Rotate portrait/landscape and verify the composer, navigation, and action controls remain usable without clipping. | NOT TESTED |
| Background/foreground | Background the browser for one minute and then longer; return and verify session expiry, entered text, focus, and keyboard behavior. | NOT TESTED |

## Sign-off

- Defects filed with reproduction and device evidence: __________________________
- Retest build / commit: ____________________________________________________
- Human tester sign-off: ______________________________ Date: _______________
- Overall result: **NOT TESTED** until the rows above are completed and signed.
