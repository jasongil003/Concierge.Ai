# Security and deployment status

**Date:** 17 October 2026 (Asia/Manila)

**Status:** Live Admin work blocked pending secure access and guest-origin configuration.

## Access and transport

- The provided public Admin URL uses HTTP. Per task instructions, administrator credentials must not be submitted there.
- An HTTPS attempt to https://115.85.36.117:8080/admin returned ERR_SSL_PROTOCOL_ERROR in the separate in-app browser. The Admin page did not load. No TLS certificate or chain was available to inspect, so this does not establish why HTTPS failed.
- The HTTP Admin path displayed an unauthenticated sign-in form. It was viewed for baseline only; no credentials were typed and no sign-in was submitted.
- No SSH tunnel was established because no approved SSH endpoint or tunnel details were available.
- No administrator credentials were entered, retrieved, or requested from code, logs, or configuration files.
- The public guest homepage is reachable over HTTP. Its concierge startup failed with “Cross-origin guest mutation denied.” The initial page showed “Okada” and no unofficial demonstration disclaimer. Do not treat the live trial as ready for guest use until the property-specific origin and disclosure have been reviewed through the supported Admin UI.

## Data handling and changes

- No installation, environment reset, deployment, database write, or configuration save was performed.
- No existing property list, administrator account, guest record, session, provider configuration, role, or permission was inspected.
- No guest-specific or administrator data was accessed.
- No API key, password, cookie, database credential, or other secret was exposed.
- No licensed resort image, logo, or proprietary map artwork was copied into the deliverables.
- Research files are local working-tree documents. No source code was changed, no tests were run, and no commit or pull request was created.

## Security observations

The guest startup rejection is consistent with the application’s configured-origin guard in app/main.py. The guard requires browser mutations to use a configured property or canonical origin. This is an observation about the response and source guard, not a diagnosis of the exact live configuration. Keep the guard enabled and reconcile the property’s public origin through the supported interface.

The repository deployment guide states that a guest pilot should use a trusted HTTPS certificate and a TLS reverse proxy. The current HTTP page should not be used for administrator sign-in. See [Deployment Guide](docs/DEPLOYMENT.md).

## Deployment readiness

| Item | Status |
|---|---|
| Secure Admin URL available | Blocked; HTTPS attempt returned ERR_SSL_PROTOCOL_ERROR |
| Secure SSH tunnel available | Blocked; no approved host/user/tunnel details supplied |
| Admin authentication | Not attempted |
| Trial property exists and is isolated | Unknown; property list unavailable |
| Guest-origin configuration | Likely needs review; exact live setting unknown |
| Guest concierge initialization | Failed in browser with cross-origin mutation denial |
| Trusted HTTPS certificate / reverse proxy | Not verified |
| Guest privacy and tenant isolation | Not tested |
| Maps, notices, AI provider, and persistence | Not tested in live tenant |
| Deployment or recovery health | Not inspected |

## To continue safely

Provide a reachable trusted HTTPS Admin URL, or approved SSH host/user and tunnel endpoint details. Do not send administrator passwords in chat. Once a secure Admin page is available, enter the Root Administrator credentials directly into that page. Inspect the existing property and its origin before creating or editing anything. After changes, verify persistence, guest responses, map behavior, privacy boundaries, and the dated Medley Buffet override in the real portal.
