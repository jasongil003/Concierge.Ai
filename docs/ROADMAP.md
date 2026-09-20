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

### Intro experience / motion branding

Give each property an optional short branded experience before the Concierge chat appears. The animation must never block guest access.

- [ ] Intro mode: none / generated preset / custom upload
- [ ] Generate intro from uploaded PNG/JPG/SVG logo
- [ ] Built-in presets: minimal fade, fade + scale, luxury reveal, particle assemble, line draw, glass/blur, split reveal
- [ ] Logo-to-chat-header transition
- [ ] Duration, background/brand color, welcome message, and transition controls
- [ ] First-visit-only playback
- [ ] Optional Skip control
- [ ] Respect `prefers-reduced-motion`
- [ ] Mobile and desktop preview before publish
- [ ] Custom `.lottie` and Lottie `.json` upload
- [ ] Custom `.webm` upload
- [ ] Optional `.mp4` fallback
- [ ] Validate animation assets and file size
- [ ] Graceful fallback directly to chat if animation fails
- [ ] Initialize guest/chat session while intro is playing where possible
- [ ] Keep After Effects `.aep` as a source-project format only; require export to a supported web format
- [ ] Later: PNG/JPG vectorization and AI-generated custom motion from logo + prompt

Implementation tracking: #14

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

## Phase 6 - Property Intelligence & Guest Location Analytics

Build this as three connected capabilities. **Zones** are the spatial source of truth, **Sessions** provide stay/device identity, and **Location Analytics** aggregates behavior from both.

### Architecture

```text
ANTlabs / WLAN / PMS
          |
          +-- device/session identity
          +-- associated AP
          +-- guest/stay context
                    |
                    v
               Concierge.AI
                    |
       +------------+------------+
       |            |            |
       v            v            v
     Zones       Sessions      Location
                              Analytics
       |            |            |
       +------------+------------+
                    |
                    v
             Property Intelligence
```

### 6A - Zones & Facility Mapping

Tracking: #10

- [ ] Add Buildings / Floors / Facilities / Access Points / Map Editor
- [ ] Upload floor plan: PNG/JPG/SVG/PDF
- [ ] Lock floor plan as the background layer
- [ ] Trace meaningful areas with rectangle/polygon/circle tools
- [ ] Map public facilities and aggregate guestroom wings/floors
- [ ] Do not require individual guest-room mapping for location analytics
- [ ] Place WLAN APs on the floor plan
- [ ] AP -> zone/facility mapping
- [ ] Navigation paths, entrances, elevators, and stairs
- [ ] Operations View with technical/AP information
- [ ] Guest View with public facilities/navigation only
- [ ] Current-zone API
- [ ] Deterministic hotel route graph
- [ ] AI explanation of deterministic routes
- [ ] Later: assisted area detection/OCR and multi-AP precision positioning

### 6B - Sessions & Stay Memory

Tracking: #undefined

- [ ] Sessions tab: Active / History / Devices / Guest Stay / AI Memory / Location History
- [ ] Correlate ANTlabs and WLAN session data
- [ ] Convert raw MAC/network identity into a property-scoped pseudonymous device ID
- [ ] Create Concierge Stay ID
- [ ] Optional PMS Guest ID / room association
- [ ] Current AP and current zone in active session
- [ ] Resume the same active stay after reconnect
- [ ] Summarized AI stay memory instead of unlimited conversation history
- [ ] Stay-based guest preferences/context
- [ ] Configurable retention
- [ ] Delete/anonymize memory and location history at checkout/session expiry by default
- [ ] Do not create permanent cross-stay identity by default

### 6C - Location Analytics & Behavior Reporting

Tracking: #undefined

Views:

- [ ] Live
- [ ] Heatmap
- [ ] Areas
- [ ] Behavior
- [ ] Movement
- [ ] Dwell Time
- [ ] Peak Hours
- [ ] Reports

Metrics:

- [ ] live zone occupancy
- [ ] unique visitors/devices by zone
- [ ] average dwell time
- [ ] peak occupancy and peak periods
- [ ] visit frequency
- [ ] repeat zone visits
- [ ] previous/next zone
- [ ] aggregated movement paths
- [ ] entry/exit areas
- [ ] historical trends
- [ ] most/least visited public areas

### AI intent -> physical behavior

Where privacy policy and data quality allow, add aggregate reporting that connects Concierge interaction with observed facility visits:

```text
Guest asks where the spa is
      ->
Concierge provides directions
      ->
same active stay later appears in Spa zone
      ->
aggregate observed conversion
```

Potential metrics:

- [ ] facility inquiry -> directions
- [ ] directions -> observed zone visit
- [ ] AI recommendation -> observed facility visit
- [ ] facility inquiry -> booking/service request

Treat these as observed correlations/conversions, not proof of causation.

### Location accuracy policy

V1 uses:

```text
Device -> associated AP -> mapped zone -> facility
```

This is **zone-level location**.

Do not present V1 heatmaps as exact guest coordinates.

Later precision phase may add:
- multiple-AP RSSI
- controller location APIs
- calibration
- approximate X/Y
- high-resolution floor-plan heatmaps

### Privacy / security

- Prefer public/common-area analytics.
- Pseudonymize network device identifiers.
- Do not expose raw MAC addresses unnecessarily.
- Aggregate movement analytics by default instead of exposing individual trails.
- Apply configurable retention and audit controls.
- Respect private/randomized MAC behavior.
- Remove temporary stay/location context according to checkout/session-expiry policy.

### Exit criteria

A hotel can upload and trace its public/aggregate floor areas, map APs and facilities, resume an active guest stay safely, view current zone occupancy, and produce useful dwell/movement/behavior reports without representing AP-level location as precise indoor positioning.

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
