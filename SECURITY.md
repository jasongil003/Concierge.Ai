# Security Policy and Prototype Boundaries

Concierge.Ai is currently a prototype.

## Do not use the current branch as-is for production guest authentication.

Before a hotel pilot:

- validate the supported ANTlabs authentication contract
- use HTTPS
- isolate the Concierge host on a service VLAN
- allowlist gateway-supplied parameters
- sign or otherwise protect redirect state
- implement replay protection
- rate-limit authentication and chat endpoints
- add audit logging
- implement administrator authentication and RBAC
- encrypt stored secrets
- minimize PMS/guest data
- define data retention and deletion policies
- conduct dependency and application security scanning

## AI safety boundaries

The LLM must not:

- grant Internet access directly
- modify gateway firewall state directly
- claim a hotel action completed unless a tool confirms it
- invent room, price, operating-hour, or reservation data
- receive full PMS records when only minimal guest context is required

## Guest data

The design target is temporary guest context tied to the active hotel/Wi-Fi session.

Operational records such as a housekeeping ticket may outlive the AI chat session if hotel operations require it, but guest chat context should follow the configured retention policy.

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
