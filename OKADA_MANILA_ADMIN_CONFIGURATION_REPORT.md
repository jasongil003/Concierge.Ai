# Concierge.AI Admin Portal configuration report

**Date:** 17 October 2026 (Asia/Manila)

**Target:** http://115.85.36.117:8080/admin

**Outcome:** Live Admin Portal configuration was blocked before authentication. No live settings were changed.

## Access and baseline evidence

The task instructions say the public portal uses HTTP and explicitly prohibit entering administrator credentials over public HTTP. I first opened the Admin Portal over HTTPS in the separate Codex in-app browser at https://115.85.36.117:8080/admin. The browser returned ERR_SSL_PROTOCOL_ERROR and did not render an Admin Portal page. I then viewed the unauthenticated HTTP page only to establish the login-page baseline; it showed username/password fields and “Authorized hotel personnel only.” No username or password was entered and no form was submitted.

I did not retry the login over HTTP, modify the live application, reset or install anything, inspect the database, or obtain secrets from environment files or logs. No authenticated baseline screenshot or save evidence exists because the secure Admin Portal never loaded.

The read-only guest homepage at http://115.85.36.117:8080/ rendered with the heading “How can I help with your stay today?” and the label “Okada”. Its concierge panel displayed “Unable to start the concierge: Cross-origin guest mutation denied.” The message composer’s Send button was disabled. No guest message was submitted.

## Module-by-module result

| Admin section | Inspection | Values saved | Persistence / guest check |
|---|---|---|---|
| Property management | Blocked; no secure Admin page | None | Not tested |
| Hotel information and branding | Blocked | None | Not tested |
| Restaurants and menus | Blocked | None | Not tested |
| Facilities and indoor map editor | Blocked | None | Not tested |
| Nearby recommendations | Blocked; external research only | None | Not tested in Concierge.AI |
| Notifications and temporary overrides | Blocked | None | Not tested |
| AI providers and property knowledge | Blocked | None | Not tested |
| User roles and permissions | Blocked | None | Not tested |
| Dashboard, analytics, privacy, deployment health, recovery | Blocked | None | Not tested |

The source-backed configuration draft is in [OKADA_MANILA_CONTENT_MANIFEST.json](OKADA_MANILA_CONTENT_MANIFEST.json). Its state is explicitly marked “not created or saved.” It is not evidence that the live tenant contains this property or content.

## Prepared values, pending secure UI access

- Display name: Okada Manila — Concierge.AI Trial
- Location: New Seaside Drive, Entertainment City, Parañaque City, 1701 Metro Manila, Philippines
- Main contact: +63 2 8888 0777
- Website: https://okadamanila.com
- Timezone: Asia/Manila
- Guest-facing disclaimer: Unofficial independent research demonstration; not operated, endorsed, or maintained by Okada Manila.
- Existing property reconciliation: not possible until the property list can be inspected. Do not create a duplicate before checking.
- Existing property data, accounts, sessions, and settings: not inspected and not modified.

## Temporary Medley Buffet configuration proposal

If the tenant supports a dated location override, retain the usual location as Upper Ground Floor, The Promenade, Pearl Wing. Apply the official temporary location Sinag, 3rd Floor, Coral Wing for 5–19 October 2026. Set an explicit review/expiry at the end of 19 October in Asia/Manila. On expiry, recheck the official notice before restoring or announcing the usual location. The official page still showed the relocation when checked on 17 October 2026.

No notification, facility record, map point, route, knowledge item, or override was entered into the live application.

## Required next step

Provide a reachable trusted HTTPS Admin Portal URL, or an approved SSH host/user and tunnel endpoint so the Admin Portal can be opened through a secure local tunnel. Do not send administrator passwords in chat. Once a secure page is available, the Root Administrator should enter credentials directly into that page. Then inspect the current property list and settings before saving any trial configuration.
