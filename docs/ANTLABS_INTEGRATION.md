# ANTlabs Integration Plan

## Current status

The repository contains a configurable ANTlabs adapter with two modes:

- `mock`: simulates successful authentication for UI and local-AI development.
- `browser_handoff`: returns a form definition that the guest browser submits to the configured ANTlabs authentication endpoint.

The exact SG5 authentication URL, required form fields, success callback, failure callback, and gateway session parameters are intentionally not hard-coded yet.

They must be validated against a real ANTlabs SG5 deployment.

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
