# Concierge.Ai Roadmap

## Phase 0 - foundation

- [x] Repository architecture
- [x] Mobile guest UI
- [x] Temporary guest sessions
- [x] Local hotel configuration
- [x] Fast-path answers
- [x] Local Ollama integration
- [x] ANTlabs adapter abstraction
- [x] Mock authentication
- [x] Browser-based gateway handoff scaffold
- [x] Docker deployment

## Phase 1 - ANTlabs lab integration

- [ ] Validate SG5 external/full-custom portal flow
- [ ] Capture exact gateway login fields
- [ ] Validate pre-auth walled-garden access to Concierge host
- [ ] Preserve gateway client/session context safely
- [ ] Successful PMS guest authentication through SG5
- [ ] Return guest to Concierge after authentication
- [ ] Detect/consume session logout or expiry
- [ ] 15-30 minute disconnect grace policy
- [ ] Test iOS captive portal behavior
- [ ] Test Android captive portal behavior

## Phase 2 - hotel concierge MVP

- [ ] Admin property configuration
- [ ] Upload hotel FAQ / menu / policy documents
- [ ] Local embeddings and vector search
- [ ] Semantic response cache
- [ ] Service-request workflow
- [ ] Staff dashboard
- [ ] Human escalation
- [ ] PMS guest-context adapter
- [ ] Multilingual response policy
- [ ] Conversation summarization
- [ ] Automatic session cleanup

## Phase 3 - pilot hardening

- [ ] HTTPS
- [ ] dedicated service VLAN
- [ ] signed gateway state
- [ ] replay protection
- [ ] rate limiting
- [ ] audit log
- [ ] PII minimization
- [ ] admin RBAC
- [ ] encrypted secrets
- [ ] backup/restore
- [ ] monitoring and alerting
- [ ] load tests
- [ ] failure-mode testing
- [ ] privacy/retention controls

## Phase 4 - commercial platform

- [ ] multi-property tenancy
- [ ] property templates
- [ ] white-label domains and branding
- [ ] PMS connector framework
- [ ] housekeeping/POS/spa connectors
- [ ] analytics and usage metering
- [ ] subscription/billing
- [ ] MSP/reseller roles
- [ ] optional cloud model provider
- [ ] optional voice concierge
- [ ] optional places/maps provider
- [ ] HA local deployment

## Pilot success metrics

Track at minimum:

- authenticated Wi-Fi sessions
- Concierge adoption rate
- requests per guest
- percentage served from fast path/cache
- percentage requiring LLM
- median response latency
- p95 response latency
- service requests created
- staff escalations
- failed authentication rate
- AI operating cost
- guest session cleanup success
