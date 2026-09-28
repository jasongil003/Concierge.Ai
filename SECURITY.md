# Security Policy and Prototype Boundaries

Concierge.Ai has security controls for development and controlled testing, but
this repository checkout does not establish production readiness. See
[`audit/CURRENT_READINESS.md`](audit/CURRENT_READINESS.md) for the current
evidence and open deployment gates.

## Current control status

**Implemented and locally tested:** guest API routes require a server-issued,
high-entropy guest token and a separate browser-context cookie; only hashes are
stored; the cookies expire and can be revoked; resume rotates credentials.
Session IDs alone no longer authenticate guest API calls. Property isolation,
admin authentication, RBAC, CSRF, and the Admin AI confirmation/allowlist
workflow remain enforced by server-side checks. SQL runtime values use bound
parameters; the narrowly suppressed Bandit B608 cases were reviewed as fixed
SQL fragments, generated placeholders, or constant schema identifiers.

**Deployment-dependent:** use HTTPS, set unique bootstrap and encryption
secrets, restrict canonical hosts and administrator CIDRs, configure trusted
proxy ranges, isolate the service on hotel networks, and set retention policy.
ANTlabs remains responsible for network admission and Internet access.

**Open or not verified here:** PDF expansion/resource limits need isolated
runtime validation. No real SG5, PMS, TLS proxy, production network, PostgreSQL
or Redis service, Docker daemon, or current online dependency advisory service
was available for this checkout's verification. A CI workflow definition is
not evidence that its remote jobs have passed.

## AI safety boundaries

The LLM must not:

- grant Internet access directly
- modify gateway firewall state directly
- claim a hotel action completed unless a tool confirms it
- invent room, price, operating-hour, or reservation data
- receive full PMS records when only minimal guest context is required

## Guest data

The design target is temporary guest context tied to the active hotel/Wi-Fi session.

Guest and assistant message text stays in the open browser session for short-term context and is sent to the property's configured AI service to generate answers. The application does not write new raw chat text to its database or expose transcripts through staff APIs or analytics. If the concierge cannot verify an answer, it directs the guest to call the hotel. Confirmed service requests and preferences the guest explicitly saves are separate records with their own workflows.

Transcript rows written by earlier versions may remain in an existing database; this change removes their staff-facing application access but does not erase those historical rows.

## Zone, session, and location privacy

- WLAN identifiers supplied by ANTlabs or infrastructure are normalized and converted to a property-scoped HMAC pseudonymous ID. Raw MAC addresses are not stored as the Concierge identity and are not returned to browsers.
- Stay memory is anchored to `ConciergeStay`, not to a permanent device profile. Default checkout behavior anonymizes room/PMS fields and clears compact AI memory.
- Location analytics use aggregate `Device -> Associated AP -> Zone -> Facility` observations. The product must not claim exact indoor positioning from a single AP.
- Guest-facing APIs omit access point identifiers, internal zone notes, and operations-only WLAN data.
- Uploads are constrained to expected web-safe floor-plan and animation types, size-limited, stored under server-controlled paths, and addressed through generated IDs to avoid path traversal.
- Retention cleanup exists for stay records; production deployments must configure retention windows and connect authoritative PMS/ANTlabs checkout or expiry events.

## AI and notification guardrails

- Verified hotel data is authoritative for facility status, menus, prices, events, opening hours, reservation availability, and service-request state.
- AI-generated notification text may change wording only. It must not create eligibility, invent offers, override quiet hours, bypass opt-outs, or claim a facility/service state that the backend has not confirmed.
- Promotional notifications require explicit category consent in policy evaluation.
- Notifications are suppressed when the guest is already at the destination zone or when a facility is closed, full, under maintenance, or reserved for a private event.
- Guest feedback must be explicitly submitted; do not infer satisfaction or sentiment from conversation text alone.
