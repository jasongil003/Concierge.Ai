# ANTlabs Integration Plan

## Current status

The repository contains a configurable ANTlabs adapter with two modes:

- `mock`: simulates successful authentication for UI and local-AI development.
- `browser_handoff`: returns a form definition that the guest browser submits to the configured ANTlabs authentication endpoint.

The live adapter now follows the built-in processor path and form fields in the supplied ANTlabs Custom Portal Developer Guide r1.01. This documents the handoff contract; it does not prove the target property's portal, processor, PMS, or Internet-access policy is configured correctly.

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

The guest UI renders only enabled methods supported by the active adapter, and `/api/authenticate` rejects disabled methods and a disabled property-level authentication switch. Mock mode can exercise all ten form paths, but it simulates acceptance only. Live `browser_handoff` currently implements only the built-in processor methods listed below. RADIUS, ACS/global accounts and codes, user registration, and social login need their own validated ANTlabs flow; they are not advertised to guests by this adapter.

### Built-in processor handoff implemented here

For the live built-in processor, configure `ANTLABS_AUTH_URL` with the SG5 host and `/login/main.ant` path. The adapter sets the query parameter to `c=proc` for Complimentary, Local, PMS, and Access Code, or `c=cc` for Credit Card. It sends a POST with the guide's `p` values: `complimentary`, `local`, `pms`, `code`, or `cc`.

- Local credentials map to `uid` and `pwd`.
- PMS room and password map to `uid` and `pwd`; the default Concierge label collects last name, so the hotel's PMS policy must actually accept that value as its configured password.
- Access Code maps to `code`.
- Complimentary sends no guest credential.
- Credit-card payment details remain on ANTlabs' configured secure payment page; Concierge does not collect card data.

ANTlabs' guide describes the built-in processor and its success/failure pages as gateway-managed. Concierge submits the browser handoff but does not receive a trusted success callback or independently verify Internet access. The admin connection check is an endpoint reachability check only. A live guest-device test is still required before production.

The property-level **Require guest sign-in** setting controls whether Concierge shows the handoff choices and accepts its authentication API. Turning it off preserves the configured methods but does not change ANTlabs VLAN, portal, or Internet-access policy. Configure ANTlabs separately if the hotel intends to permit Internet access without gateway authentication.

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

## Signed gateway assertion

When the property's `antlabs_gateway_enabled` guardrail is enabled, `POST /api/session/start` requires a gateway assertion. The assertion is an HMAC-SHA256 over the exact request bytes using this canonical input:

```text
timestamp + "." + nonce + "." + request_body
```

Required headers are `X-ANTlabs-Timestamp`, `X-ANTlabs-Nonce`, and `X-ANTlabs-Signature`. The nonce must be 16 to 256 characters, the timestamp must be within five minutes, and the signature may be sent as hex or `sha256=<hex>`. The request body must contain the same `property_id` that Concierge resolved from the trusted property host. The request's direct source IP must match a configured ANTlabs gateway CIDR.

Nonce consumption is atomic and persistent. Concierge stores only a SHA-256 hash, scopes the row to the property, rejects reuse, and removes expired entries when consuming a nonce. If signature validation, property binding, source-range validation, or nonce storage fails, session creation is denied.

Keep the signing secret on the gateway or a trusted server-side integration. Never place it in browser code or guest URLs. Do not use `ALLOW_BODY_PROPERTY_SELECTION` as a substitute for a trusted hostname mapping in production. The assertion proves that the signed request came through the configured integration; it does not authenticate a guest with ANTlabs or prove the guest has Internet access.

Only allowlist the gateway context fields the application needs. Do not trust client-supplied room, guest, or authorization values unless they are covered by the signed assertion and validated against the target gateway contract. Avoid guest PII in URLs.

## Configuration

Example only:

```env
ANTLABS_MODE=browser_handoff
ANTLABS_AUTH_URL=https://<sg5-host>/login/main.ant?c=proc
ANTLABS_AUTH_METHOD=POST
ANTLABS_ROOM_FIELD=uid
ANTLABS_LAST_NAME_FIELD=pwd
ANTLABS_SESSION_FIELD=<validated-session-field-if-required>
ANTLABS_SESSION_CONTEXT_KEY=<validated-query/context-key-if-required>
ANTLABS_PASSTHROUGH_FIELDS=<validated-field-1>,<validated-field-2>
```

Replace `<sg5-host>` with the property's actual gateway hostname. The built-in processor requires the `/login/main.ant` path and POST. No ANTlabs session field is sent by default; only map session or passthrough values after validating them against the gateway-provided context. Startup accepts only `mock` and `browser_handoff`; unsupported values such as `live` fail configuration loading. Production startup also requires an auth URL for browser handoff. These checks validate configuration shape, not gateway compatibility.

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

This full round trip is still a lab validation requirement. A signed Concierge assertion and a rendered browser handoff form do not demonstrate that SG5 authenticated the guest or granted network access.

## Location and stay event hooks

The roadmap foundation exposes backend APIs that a real ANTlabs/WLAN adapter can call after the SG5 contract is validated:

- submit server-side WLAN device identity to restore or create an active Concierge Stay
- submit AP association observations as `access_point_identifier`
- map that AP to a configured Concierge zone
- update aggregate occupancy, dwell, and movement analytics

This integration must keep raw MAC handling server-side. Concierge.Ai stores and returns a property-scoped pseudonymous device ID and uses the active Concierge Stay as the AI memory anchor.

AP association is an aggregate location signal only. It supports reports such as `Lobby -> Restaurant -> Pool`; it does not provide exact guest coordinates.
