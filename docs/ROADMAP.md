# Concierge.Ai Product Roadmap

## Product direction

Concierge.Ai will be built **on-premise first** and designed so the same property can later move to **cloud or hybrid deployment without changing the guest-facing URL**.

### Core commercial principles

1. ANTlabs remains the network-access authority.
2. Concierge.Ai provides the guest experience, AI, knowledge, integrations, and service workflows.
3. Production hotel deployments use HTTPS; HTTP is lab-only.
4. The customer provides supported hardware and its own domain/subdomain.
5. A property keeps one canonical guest URL, for example `https://concierge.hotel.com`.
6. On-premise deployments use local/internal DNS to route that hostname to the local Concierge runtime.
7. The guest experience must be recoverable after the captive-portal mini-browser closes.
8. AI is provider-independent: local, Gemini, OpenAI, private compatible endpoints, hybrid, or automatic routing.
9. Hotels customize presentation and content; core authentication/security/business logic stays controlled by Concierge.Ai.
10. Commercial on-prem licensing targets a perpetual property license plus annual maintenance and paid custom integrations.

---

## Phase 0 - application foundation

**Status: foundation in progress / major scaffolding complete**

- [x] Repository architecture
- [x] Mobile-first guest concierge UI
- [x] Temporary guest session store
- [x] Hotel-specific configuration
- [x] Fast-path answers for repetitive questions
- [x] Local Ollama integration
- [x] Default local model upgraded to Qwen3 8B configuration
- [x] Multi-provider AI router
- [x] Fast / Auto / Advanced guest AI mode switcher
- [x] Gemini provider
- [x] OpenAI provider
- [x] OpenAI-compatible/private provider
- [x] Hybrid AI mode
- [x] Automatic AI routing mode
- [x] Google Places live recommendation adapter
- [x] ANTlabs adapter abstraction
- [x] Mock guest authentication
- [x] Browser-based ANTlabs handoff scaffold
- [x] SQLite prototype state
- [x] Docker deployment
- [x] CI test workflow
- [x] Architecture, deployment, security, and AI-provider documentation

### Exit criteria

- App runs locally.
- Guest can start a temporary concierge session.
- Hotel knowledge fast paths work.
- At least one configured AI provider can answer.
- AI provider is replaceable without changing the guest UI.

---

## Phase 1 - ANTlabs authentication proof

**Priority: highest**

The first real milestone is:

```text
Unauthenticated guest
        ->
Concierge.Ai
        ->
hotel credentials
        ->
ANTlabs / PMS validates the same guest device
        ->
Internet access opens
        ->
Concierge remains recoverable
```

### Work

- [ ] Validate SG5 external/full-custom portal flow on a lab gateway
- [ ] Capture exact login form/action/parameters
- [ ] Capture required gateway/downstream-client context
- [ ] Confirm supported success and failure redirects
- [ ] Validate pre-auth walled-garden access to Concierge.Ai
- [ ] Preserve gateway state using allowlisted/signed state
- [ ] Successfully authenticate a PMS guest through SG5
- [ ] Confirm ANTlabs, not Concierge.Ai, creates the Internet session
- [ ] Return or resume the guest Concierge after successful login
- [ ] Detect ANTlabs session logout/expiry where supported
- [ ] Test PMS checkout termination behavior
- [ ] Test iOS captive-network-assistant behavior
- [ ] Test Android captive-portal behavior
- [ ] Test roaming/reconnect without forcing unnecessary re-login

### Exit criteria

A physical phone can complete the end-to-end flow without manually changing SG5 session state.

---

## Phase 2 - production-style on-prem networking and HTTPS

Production hotel deployments must not depend on HTTP/IP URLs.

### Customer-provided prerequisites

- supported Mac mini/server/VM
- hotel network/VLAN access
- customer-owned hostname/subdomain, e.g. `concierge.hotel.com`
- DNS administrator/API access required for setup
- ANTlabs environment
- PMS/integration access where applicable

### Work

- [ ] Dedicated Concierge service VLAN/network design
- [ ] Reverse proxy on the on-prem runtime
- [ ] Customer hostname configuration
- [ ] Split-horizon/internal DNS
- [ ] HTTPS/TLS using ACME DNS-01
- [ ] Automated certificate renewal
- [ ] Ensure each property uses its own key/certificate
- [ ] Firewall policy: guest VLAN -> Concierge HTTPS only
- [ ] Prevent public inbound access to the on-prem runtime
- [ ] ANTlabs pre-auth HTTPS walled-garden configuration
- [ ] Canonical `/resume` flow after authentication
- [ ] Secure HttpOnly Concierge session cookie
- [ ] Session recovery after captive browser closes
- [ ] QR code pointing to the same canonical HTTPS URL
- [ ] Test Safari, Chrome, iOS captive browser, and Android captive browser
- [ ] Optional public informational page when the hostname is accessed off-site

### Exit criteria

The same HTTPS URL works for ANTlabs entry, QR re-entry, bookmarks, and normal browser access while the real on-prem application remains site-restricted.

---

## Phase 3 - AI, hotel knowledge, and recommendations

### Current AI architecture

```text
Guest
  |
  +--> Fast path / cache
  |
  +--> Fast mode
  |
  +--> Auto mode
  |      |
  |      +--> automatic complexity/live-data escalation
  |
  +--> Advanced mode
         |
         +--> stronger reasoning/provider
```

### Provider options

- [x] Local Ollama/Qwen
- [x] Gemini
- [x] OpenAI
- [x] OpenAI-compatible private/cloud endpoint
- [x] Hybrid
- [x] Automatic routing

### Remaining work

- [ ] Property-admin AI-provider settings UI
- [ ] Encrypted provider secret storage
- [ ] Per-property enabled-provider policy
- [ ] Per-property fast and advanced model selection
- [ ] Cloud-AI budget/usage controls
- [ ] Provider/model usage analytics
- [ ] Local fallback when public AI is unavailable
- [ ] Upload hotel FAQs, menus, policies, and service information
- [ ] Local document parsing/chunking
- [ ] Local embeddings/vector search
- [ ] Semantic response cache
- [ ] Source metadata and answer grounding
- [ ] Conversation summarization instead of unlimited chat history
- [ ] Multilingual response policy
- [ ] Live restaurant/place recommendation UI
- [ ] Hotel-curated recommendation list as offline fallback
- [ ] Maps/deep-link support for recommended places
- [ ] Never invent business names, ratings, opening hours, or addresses

### Exit criteria

Routine hotel questions are fast and inexpensive, complex requests automatically escalate, and nearby recommendations are grounded in current or hotel-curated data.

---

## Phase 4 - property platform and landing-page builder

The commercial product should not require Concierge.Ai engineering to redesign every hotel.

### Property administration

- [ ] Create/edit property
- [ ] Hotel name and property ID
- [ ] Customer hostname/subdomain
- [ ] Deployment mode: on-prem / cloud / hybrid
- [ ] Logo and brand assets
- [ ] Concierge name/avatar
- [ ] Colors, fonts, hero/background assets
- [ ] Welcome message
- [ ] Languages
- [ ] Quick actions
- [ ] Facilities
- [ ] Dining/spa/services
- [ ] Hotel policies
- [ ] Guest support contacts
- [ ] AI configuration
- [ ] Knowledge uploads
- [ ] ANTlabs integration settings

### Template builder

Provide hospitality-specific templates:

- [ ] Luxury hotel
- [ ] Business hotel
- [ ] Beach/resort
- [ ] Boutique hotel
- [ ] Serviced apartment
- [ ] Conference property

Builder features:

- [ ] Mobile-first visual editor
- [ ] Pre-auth preview
- [ ] Authenticated-guest preview
- [ ] Desktop/mobile preview
- [ ] Section ordering
- [ ] Quick-action editor
- [ ] Draft/publish workflow
- [ ] Version history
- [ ] Rollback
- [ ] Clone template between properties
- [ ] Hotel-group brand template

### Fully customized frontend

- [ ] Approved custom frontend package format
- [ ] HTML/CSS/assets/theme manifest
- [ ] Strict sandbox/content-security policy
- [ ] Asset/file validation
- [ ] Optional restricted JavaScript policy
- [ ] No arbitrary PHP/server-side code uploads
- [ ] Fixed Concierge API contract for custom frontends
- [ ] Preview/security scan before publish

### Exit criteria

A hotel can create and publish a branded guest experience without modifying core application code.

---

## Phase 5 - hotel operations and integrations

The core application remains coded; optional workflow automation can use n8n where appropriate.

### Core code

- [ ] PMS guest-context adapter
- [ ] Service-request API
- [ ] Staff dashboard
- [ ] Human escalation
- [ ] Request status tracking
- [ ] Auditable hotel actions
- [ ] Confirm actions before claiming success to the guest

### Integration framework

- [ ] PMS connector interface
- [ ] Housekeeping connector
- [ ] Maintenance/ticket connector
- [ ] POS/dining connector
- [ ] Spa/reservation connector
- [ ] Messaging connector
- [ ] Optional n8n webhook/event connector

### Event model

- [ ] `guest.connected`
- [ ] `guest.authenticated`
- [ ] `guest.disconnected`
- [ ] `guest.checked_out`
- [ ] `housekeeping.requested`
- [ ] `maintenance.requested`
- [ ] `late_checkout.requested`
- [ ] `human_handoff.requested`

### n8n boundary

Use n8n for hotel-specific workflow integration and notifications. Do not place guest authentication, license enforcement, core permissions, or session security inside n8n.

---

## Phase 6 - indoor location and hotel navigation

Start with AP/zone location, not precise indoor positioning.

### Work

- [ ] Define `WiFiLocationProvider` interface
- [ ] Correlate Concierge/ANTlabs session with Wi-Fi client
- [ ] Retrieve current associated AP from WLAN controller
- [ ] Property AP -> hotel zone mapping
- [ ] Current-zone API
- [ ] Hotel route graph
- [ ] Directions between zones/facilities
- [ ] AI explanation of deterministic route
- [ ] Aruba adapter
- [ ] Ruckus adapter
- [ ] Cisco/Meraki adapter as demand requires
- [ ] UniFi adapter as demand requires
- [ ] Optional RSSI/multi-AP enhancement later
- [ ] Guest privacy notice/consent where required
- [ ] Do not keep long-term movement history by default
- [ ] Delete temporary location association at session expiry/checkout

### Example

```text
Guest session
   ->
Current AP
   ->
Floor 3 East Wing
   ->
Destination: Pool
   ->
Route graph
   ->
Elevator -> Lobby -> Garden Corridor -> Pool
```

---

## Phase 7 - commercial licensing and maintenance

Initial on-prem commercial model:

```text
Perpetual property software license
        +
One-time implementation
        +
Annual maintenance/support
        +
Paid custom integrations
```

Customer provides hardware and domain/subdomain.

### License architecture

- [ ] Property-based license
- [ ] Signed offline-verifiable license
- [ ] Asymmetric signature/public verification key
- [ ] Installation/node identity
- [ ] Allowed node count
- [ ] Room/license tier
- [ ] Feature entitlements
- [ ] Version entitlement
- [ ] Maintenance expiration date
- [ ] Optional 2-node HA entitlement
- [ ] Trial license
- [ ] Active/grace/expired/revoked states
- [ ] Admin license status page
- [ ] License activation API
- [ ] License refresh/renewal flow
- [ ] Optional periodic control-plane validation

### Maintenance rules

When annual maintenance expires:

- existing purchased software continues to run
- ANTlabs guest Wi-Fi must not be broken
- future upgrades are unavailable
- support is unavailable
- managed update/certificate services follow contract terms
- custom work remains separately quoted

---

## Phase 8 - pilot hardening, security, and scale

- [ ] Signed gateway state
- [ ] Replay protection
- [ ] CSRF protection
- [ ] Rate limiting
- [ ] Secret encryption
- [ ] PII minimization
- [ ] Admin authentication/RBAC
- [ ] Audit log
- [ ] Privacy/retention controls
- [ ] Backup/restore
- [ ] Monitoring/alerting
- [ ] Health dashboard
- [ ] Dependency/security scanning
- [ ] Failure-mode tests
- [ ] AI-provider outage tests
- [ ] Internet-outage/local-fallback tests
- [ ] ANTlabs/PMS outage tests
- [ ] Load test 5/10/20/50 concurrent AI generations
- [ ] 1,000-connected-guest traffic simulation
- [ ] p50/p95 latency measurements
- [ ] CPU/GPU/memory measurements
- [ ] Queue/back-pressure controls
- [ ] HA local deployment option

### Pilot metrics

Track:

- authenticated Wi-Fi sessions
- Concierge adoption rate
- requests per guest
- cache/fast-path percentage
- local-AI percentage
- cloud-AI percentage
- Advanced-mode percentage
- median/p95 response latency
- failed authentication rate
- service requests
- human escalations
- nearby recommendation usage
- AI/API operating cost
- guest-session cleanup success
- uptime

---

## Phase 9 - cloud control plane and cloud migration

The on-prem product should evolve into a centrally manageable platform without forcing existing hotels to change URLs.

### Control plane

- [ ] Multi-property tenancy
- [ ] Organization/hotel-group accounts
- [ ] Property provisioning
- [ ] Central configuration management
- [ ] Deployment status/health
- [ ] Release channels
- [ ] Secure update delivery
- [ ] License management
- [ ] Central analytics
- [ ] Hotel-template library
- [ ] Partner/MSP roles

### Deployment choices

```text
Concierge.Ai Edge
- on-prem runtime
- local/private integrations
- optional local AI

Concierge.Ai Cloud
- cloud runtime
- no hotel AI hardware required

Concierge.Ai Hybrid
- local ANTlabs/PMS connector
- cloud AI/runtime services
```

### Migration rule

A property should retain:

- same customer-owned HTTPS hostname
- same QR codes
- same ANTlabs portal link
- same property ID
- same hotel configuration

Migration should primarily be a routing/DNS and deployment change.

---

## Phase 10 - advanced guest experience

Only after the core Wi-Fi/authentication flow is stable:

- [ ] Voice concierge
- [ ] PWA/add-to-home-screen experience
- [ ] Push/guest notifications where appropriate
- [ ] Restaurant/spa booking actions
- [ ] Airport transport workflows
- [ ] Late-checkout upsell
- [ ] Hotel service recommendations
- [ ] Optional guest preference memory limited to active stay
- [ ] Post-stay cleanup
- [ ] Hotel revenue attribution/analytics

---

## Near-term execution order

Do not try to build every phase in parallel.

### Next five milestones

1. **ANTlabs SG5 authentication proof**
2. **Production-style HTTPS + canonical URL + re-entry**
3. **Property admin + hotel template builder**
4. **Knowledge/RAG + AI provider settings + live recommendations**
5. **One real on-prem hotel pilot**

The pilot should happen before major investment in voice, precise indoor positioning, or full cloud migration.

---

## Current implementation status - zones, sessions, analytics, intro

**Status: commercial foundation implemented / real hardware validation pending**

- [x] Admin `Zones` section with building/floor hierarchy, floor-map upload validation, layer toggles, and canvas-based map object creation
- [x] Normalized data models for buildings, floors, maps, zones, facilities, APs, navigation nodes, and navigation edges
- [x] AP-to-zone association model using aggregate areas, not individual room mapping
- [x] Guest-safe zone/navigation APIs that omit AP identifiers and internal WLAN details
- [x] Deterministic route graph API for guest and operations views
- [x] Admin `Sessions` section for device reconnect, stay history, and compact AI memory
- [x] Property-scoped HMAC pseudonymous device identity
- [x] Concierge Stay ID as the memory anchor
- [x] Checkout anonymization and retention cleanup hooks
- [x] Admin `Location Analytics` section for live occupancy, observations, reports, dwell time, and movement transitions
- [x] Aggregate movement reporting instead of individual trail display
- [x] AI interaction and facility conversion event tables for future privacy-safe correlation
- [x] Admin `Branding -> Intro Experience` section with presets, duration, colors, first-visit, skip, and upload validation
- [x] Guest intro fallback that respects reduced motion and never blocks chat startup
- [x] Vendor-neutral `WiFiLocationProvider` abstraction and mock provider
- [x] Structured facility profiles with opening hours, capacity, booking support, and live status
- [x] Restaurants, menus, menu items, dietary/allergen tags, and availability
- [x] Hotel events with facility/zone, audience, capacity, CTA, and notification timing
- [x] Service request lifecycle with SLA state and explicit guest feedback
- [x] Notification rules, verified payload evaluation, suppression guardrails, and delivery history
- [x] Guest journey event tracking for adoption and observed-conversion reporting

Remaining validation:

- Real ANTlabs/WLAN AP association feed
- PMS checkout events and authoritative stay boundaries
- Real restaurant/POS, booking, PMS, and notification delivery integrations
- Production admin authentication/RBAC enforcement
- Production map editor precision, PDF rendering previews, and advanced polygon point editing
- Hardware-backed location accuracy testing
