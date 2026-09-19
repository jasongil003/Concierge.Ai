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
