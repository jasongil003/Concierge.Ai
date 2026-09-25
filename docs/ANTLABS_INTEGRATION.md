# ANTlabs Integration Plan

## Current status

The repository contains a configurable ANTlabs adapter with two modes:

- `mock`: simulates successful authentication for UI and local-AI development.
- `browser_handoff`: returns a form definition that the guest browser submits to the configured ANTlabs authentication endpoint.

The exact SG5 authentication URL, required form fields, success callback, failure callback, and gateway session parameters are intentionally not hard-coded yet.

They must be validated against a real ANTlabs SG5 deployment.

## Authentication methods in scope

The guest authentication capability must cover every method currently exposed in Concierge.Ai hotel settings. Enabling a method in settings must lead to a real guest flow or clearly show that the property's required gateway/provider configuration is missing. A setting or AI explanation alone does not count as an implemented login method.

| Concierge.Ai method | Guest inputs / gateway flow to validate | Dependencies and notes |
| --- | --- | --- |
| Complimentary | Complimentary processor (`p=complimentary`) and any configured plan | Usually no guest credential; property plan/configuration may be required. |
| Local | Built-in processor (`p=local`, `uid`, `pwd`) | Local gateway account and plan. |
| RADIUS | Gateway login with RADIUS mode/type and username/password | RADIUS server, shared secret, and gateway policy must already be configured. |
| PMS / room login | Built-in processor (`p=pms`, `uid` for room, `pwd` for the PMS credential) | Confirm whether the property accepts last name as the PMS password; do not assume it. |
| Credit card | Credit-card processor (`c=cc`) and configured payment flow | Payment provider and plan required. Card details must be collected only by the supported payment flow, never by Concierge chat or its AI. |
| Access code | Built-in processor (`p=code`, `code`) | Gateway-issued code and applicable plan. |
| Global account | ACS/global account login using username and password | ACS account availability and gateway-to-ACS configuration. |
| Global code | ACS/global code login using code | ACS code availability and gateway-to-ACS configuration. |
| User form | Configured registration form, followed by any required verification | Form fields, consent, OTP/email/SMS verification, and account provisioning depend on site configuration. |
| Social network | ANTlabs social login initialization and return flow | Provider app credentials, callback URLs, and gateway social-login configuration. This is a redirect/callback flow, not a normal credential form. |

The supplied ANTlabs docs describe multiple supported gateway mechanisms, but do not prove that every method is licensed, enabled, or configured on the target gateway. During discovery, record each hotel's enabled methods and mark each one as `ready`, `configuration required`, or `unsupported by this gateway/version`. The guest UI should offer only methods marked ready for that property.

The V5 Gateway API's `auth_login` supports local, RADIUS, and ACS account/code paths. The custom portal guide also documents built-in complimentary, local, PMS, access-code, and credit-card processor paths, plus gateway social-login APIs. User-form verification and payment/social provider setup require their own site configuration. The ASP API V2 management API is not a substitute for guest login.

The guest UI now renders forms from the property's enabled methods, and the `/api/authenticate` endpoint rejects any method that is disabled for that property. Mock mode can exercise all ten form paths, but it simulates acceptance only. Live gateway handoff mappings still require validation against the site's configured processor and provider setup; a handoff response by itself must not be treated as proof of successful authentication.

## Why browser handoff

The guest device is the client ANTlabs needs to authorize. The prototype therefore avoids making the gateway login request from the Concierge server's source IP.

Conceptually:

```text
Guest
  |
  v
Concierge.Ai
  |
  | collect room / last name
  v
Guest browser submits authentication form
  |
  v
ANTlabs SG5
  |
  v
PMS / configured authentication source
  |
  v
Guest network session becomes authenticated
```

## Pre-auth network requirement

The Concierge endpoint must be reachable before guest authentication.

For the first lab:

```text
http://<concierge-server-ip>:8080
```

For a real pilot:

```text
https://concierge.example.com
```

with the hostname allowed through the ANTlabs pre-auth/walled-garden policy.

## Gateway context preservation

When ANTlabs redirects or links the guest into Concierge.Ai, preserve only the parameters required to complete the login handoff.

The browser prototype currently stores query parameters as `gateway_context`.

Production requirements:

1. allowlist accepted gateway parameter names
2. reject unexpected fields
3. never trust client-supplied room or authorization state
4. use signed or opaque state where possible
5. prevent replay
6. set a short lifetime
7. avoid exposing guest PII in URLs

## Configuration

Example only:

```env
ANTLABS_MODE=browser_handoff
ANTLABS_AUTH_URL=http://<gateway-auth-endpoint>
ANTLABS_AUTH_METHOD=POST
ANTLABS_ROOM_FIELD=<validated-room-field>
ANTLABS_LAST_NAME_FIELD=<validated-last-name-field>
ANTLABS_SESSION_FIELD=<validated-session-field-if-required>
ANTLABS_SESSION_CONTEXT_KEY=<validated-query/context-key-if-required>
ANTLABS_PASSTHROUGH_FIELDS=<validated-field-1>,<validated-field-2>
```

Do not deploy `browser_handoff` using placeholder field names. No ANTlabs session field is sent by default; it must be mapped from validated gateway-provided context.

## Real SG5 validation checklist

Capture a normal working ANTlabs guest login and document:

- initial captive portal URL
- query parameters supplied to the portal
- form action URL
- HTTP method
- required hidden fields
- room field name
- last-name field name
- CSRF/nonces if present
- success redirect
- failure redirect
- how the downstream client session is identified
- what happens when the browser closes
- login/session expiry behavior
- PMS checkout behavior

Preferred method: use a lab SG5 and browser developer tools while performing a standard supported login.

## Success criteria

The milestone is complete when this flow works without manually changing the gateway session:

```text
1. Phone joins guest Wi-Fi
2. Phone is unauthenticated
3. Concierge.Ai is reachable through pre-auth policy
4. Guest provides valid hotel credentials
5. Browser hands authentication to SG5
6. SG5/PMS validates the guest
7. SG5 opens Internet access for that device
8. Guest returns to Concierge.Ai
9. Concierge session remains active
10. SG5/PMS logout causes concierge session expiry
```

## Location and stay event hooks

The roadmap foundation exposes backend APIs that a real ANTlabs/WLAN adapter can call after the SG5 contract is validated:

- submit server-side WLAN device identity to restore or create an active Concierge Stay
- submit AP association observations as `access_point_identifier`
- map that AP to a configured Concierge zone
- update aggregate occupancy, dwell, and movement analytics

This integration must keep raw MAC handling server-side. Concierge.Ai stores and returns a property-scoped pseudonymous device ID and uses the active Concierge Stay as the AI memory anchor.

AP association is an aggregate location signal only. It supports reports such as `Lobby -> Restaurant -> Pool`; it does not provide exact guest coordinates.
