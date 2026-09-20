# Concierge.AI Master Product Expansion Plan

## Product vision

Concierge.AI should evolve from an AI chatbot for hotel guests into an **AI-powered guest experience and property intelligence platform** that accompanies the guest throughout the stay while giving the hotel real-time operational and behavioral insight.

The product should combine:

- guest AI concierge
- ANTlabs / guest Wi-Fi integration
- property and facility mapping
- guest session continuity
- stay-based AI memory
- facility navigation
- live zone occupancy
- location and movement analytics
- hotel events
- restaurant/menu information
- weather-aware assistance
- proactive notifications
- service-request operations
- campaigns/offers
- guest feedback
- executive reporting
- privacy and AI guardrails

---

## Product principle

> **Data decides what is true. Rules decide what is allowed. AI decides how to communicate it.**

AI must not invent operational facts, pricing, availability, policies, event details, weather, booking success, service completion, or reasons to contact a guest.

---

## Target platform structure

```text
Guest Experience
- Branding
- Intro Experience
- Concierge Design
- Quick Actions
- Languages

AI
- AI Models
- AI Routing
- Guardrails
- Prompts
- Usage

Knowledge
- Documents
- Hotel Information
- FAQs
- Policies

Facilities
- Facilities
- Restaurants
- Menus
- Services
- Events
- Opening Hours

Zones
- Buildings
- Floors
- Map Editor
- Facilities
- Access Points
- Navigation Paths

Location Analytics
- Live
- Heatmap
- Areas
- Behavior
- Movement
- Dwell Time
- Peak Hours
- Reports

Sessions
- Active
- History
- Devices
- Guest Stays
- AI Memory
- Location History

Notifications
- Overview
- Automated Triggers
- Campaigns
- Events
- Templates
- Audience
- Delivery History
- Guardrails
- Analytics

Operations
- Service Requests
- Tasks
- SLA
- Escalations
- Facility Status
- Alerts

Analytics
- Guest Journey
- AI Usage
- Facility Performance
- Notifications
- Conversion
- Feedback
- Executive Reports

Integrations
Security
Settings
```

---

## Property intelligence foundation

### Zones and facility mapping

Support:

```text
Property
  -> Building
  -> Floor
  -> Zone
  -> Facility
  -> Access Point
```

Allow upload of PNG/JPG/SVG/PDF floor plans, trace public or aggregate zones, and place:

- facilities
- APs
- entrances/exits
- elevators/stairs
- navigation paths
- labels

Do not require mapping individual guest rooms for location analytics.

Use aggregate zones such as:

- Floor 15 East Wing
- Floor 15 West Wing
- Elevator Lobby
- Executive Lounge

Maintain separate Operations and Guest views.

See Issue #10.

---

## Sessions, identity, and stay memory

Use network identity only as an input to a safer application identity.

Recommended flow:

```text
WLAN / ANTlabs device identity
  -> property-scoped pseudonymous Device ID
  -> Concierge Session
  -> Concierge Stay ID
  -> optional PMS Guest ID / room
  -> stay-scoped AI memory
```

Do not use raw MAC as the permanent guest identity.

Support reconnect during the same active stay and restore compact summarized context rather than replaying unlimited chat history.

Memory may include:

- conversation summary
- explicit preferences relevant to the stay
- recent requests
- bookings
- unresolved service items
- important concierge context

Default lifecycle:

```text
Check-in -> active stay memory -> reconnect supported -> checkout -> delete/anonymize
```

See Issue #15.

---

## Location analytics

Location Analytics should contain:

- Live
- Heatmap
- Areas
- Behavior
- Movement
- Dwell Time
- Peak Hours
- Reports

V1 location model:

```text
Device -> Associated AP -> Mapped Zone -> Facility
```

This is zone-level location, not exact indoor coordinates.

Metrics include:

- live occupancy
- unique visits
- average dwell
- peak occupancy
- visit frequency
- repeat zone visits
- common previous/next zone
- entry/exit areas
- historical trends
- aggregated movement paths

Later precision work may add multi-AP RSSI, controller location APIs, calibration, and approximate X/Y.

See Issue #16.

---

## Guest journey analytics

Track a privacy-safe guest journey such as:

```text
Wi-Fi connected
  -> Concierge opened
  -> authenticated
  -> AI interaction
  -> facility viewed
  -> directions requested
  -> observed zone visit
  -> reservation/service request
```

This supports funnel reporting without treating location correlation as proof of causation.

---

## Digital intent to physical behavior

Potential differentiated reporting:

```text
Guest asks "Where is the spa?"
  -> Concierge provides directions
  -> same active stay later appears in Spa zone
  -> observed conversion
```

Metrics may include:

- facility inquiry -> directions
- directions -> observed facility visit
- AI recommendation -> observed visit
- facility inquiry -> booking/request

Always describe these as observed correlation or conversion.

---

## Facilities

Each facility should have structured data:

- name
- type
- building/floor/zone
- opening hours
- capacity
- description
- images
- services
- contact details
- booking capability
- live status

Statuses may include:

- Open
- Closed
- Temporarily Closed
- Full
- Maintenance
- Private Event

AI must respect current structured facility status.

---

## Restaurants and menus

Restaurant model should include:

- restaurant information
- location
- meal periods
- opening hours
- menu
- daily specials
- dietary tags
- allergens
- availability
- reservation capability

Menu items may include:

- name
- description
- price
- image
- ingredients
- allergen information
- dietary tags
- availability

AI can personalize using explicit active-stay preferences, but must not infer or invent preferences.

---

## Events

Support property events such as:

- poolside music
- yoga
- kids activities
- happy hour
- movie night
- tours
- buffet
- conferences
- weddings
- seasonal programs

Event structure should include:

- title
- date/time
- location
- audience
- capacity if relevant
- description
- notification schedule
- CTA such as directions/reserve/view details

---

## Proactive Stay Assistant

Concierge.AI should assist across the stay lifecycle.

### Check-in
- welcome
- hotel orientation
- breakfast
- Wi-Fi
- facilities

### During stay
- weather
- events
- restaurant specials
- facility updates
- reservations
- service-request status
- context-aware recommendations

### Pre-checkout
- checkout reminder
- late checkout
- transport
- billing information

### Checkout
- thank-you
- feedback
- memory cleanup

See Issue #17.

---

## Notification Engine

Supported trigger types:

- scheduled
- weather
- hotel event
- location/zone context
- facility status
- stay lifecycle
- service request
- reservation
- PMS event
- operational/emergency event

Notification categories:

### Operational
- checkout
- shuttle status
- facility closure
- maintenance
- service completion

### Assistance
- weather
- directions
- reservation reminders
- facility availability

### Experience
- events
- activities
- live music
- hotel programs

### Promotional
- spa offers
- dining specials
- late checkout
- upgrades/packages

Promotional messaging should use stricter consent and frequency controls.

---

## Notification guardrails

Required flow:

```text
Verified Source Data
      ->
Trigger Engine
      ->
Eligibility / Consent / Frequency / Quiet Hours
      ->
Policy Decision
      ->
AI wording
      ->
Delivery
```

AI may control:

- wording
- tone
- language
- brevity

AI must not control or alter:

- event facts
- prices
- opening hours
- availability
- booking state
- weather facts
- emergency facts
- guest eligibility
- notification policy

Recommended controls:

- per-day proactive-message cap
- stricter promotional cap
- minimum interval
- quiet hours
- emergency override
- pause notifications
- notification preferences
- contextual suppression

Example suppression:
Do not send "Come to the pool" if the guest is already in the Pool zone.

---

## Weather-aware assistance

Combine verified weather data with verified property services.

Example:

```text
Rain forecast
 + umbrellas_available=true
 + umbrella_location=Front Desk
 -> approved proactive message
```

AI must never invent services such as umbrellas.

---

## Service-request operations

Guest requests should become structured operational records.

Example statuses:

```text
New
 -> Assigned
 -> Accepted
 -> In Progress
 -> Delivered
 -> Completed
```

Possible categories:

- housekeeping
- maintenance
- room amenities
- transport
- dining
- guest complaint
- other

AI should only tell a guest that an action succeeded after the backend/integration confirms it.

---

## SLA management

Support service-level targets by request category.

Examples:

- towels: 15 min
- maintenance: 30 min
- guest complaint: 10 min
- emergency: immediate

Dashboards should show:

- open
- within SLA
- warning
- overdue

---

## Smart recommendations

Recommendation context may include:

- current zone
- time
- weather
- opening hours
- occupancy/capacity
- active hotel events
- explicit stay preferences
- facility status

Recommendations must remain grounded in verified hotel data.

---

## Occupancy and facility alerts

Allow hotel-defined thresholds.

Example:

```text
Pool capacity: 100
Warning: 75
Critical: 90
```

Possible responses:

- dashboard warning
- staff alert
- suppress recommendations to crowded facility
- suggest alternatives

---

## Guest feedback

After a completed service/request, request simple explicit feedback such as:

- Yes, resolved
- Partially
- No

Optional rating/comments can be linked to:

- department
- facility
- request type
- response time
- stay

Do not infer emotional state automatically.

---

## Campaigns and offers

Allow opted-in campaigns with:

- audience
- schedule
- location
- CTA
- frequency policy
- offer details

Measure:

- eligible
- delivered
- viewed
- clicked
- directions opened
- observed visit
- reservation/request

Again, observed visits are correlations, not proof of causation.

---

## Operations dashboard

Suggested high-level KPIs:

- guests/devices on property
- active Concierge sessions
- open service requests
- overdue requests
- busiest zone
- facility occupancy
- today's events
- current alerts

---

## Executive analytics

Potential reports:

- Concierge adoption
- AI usage
- service-request volume
- SLA performance
- facility utilization
- dwell time
- movement
- notification engagement
- guest journey
- feedback
- conversion
- revenue-related actions

---

## Data quality dashboard

Analytics should expose data-quality problems instead of silently using bad inputs.

Show:

- unmapped APs
- offline APs
- sessions without zones
- facilities missing map data
- invalid navigation paths
- outdated menus
- incomplete event locations
- failed notification deliveries
- stale integrations

---

## Simulation mode

Support virtual/synthetic hotel traffic to test:

- occupancy
- heatmaps
- movement
- alerts
- notification rules
- reports
- capacity

This is useful for demos and QA before real hardware integration.

---

## Event mode

Allow temporary changes for conferences, weddings, exhibitions, and other functions.

Example:

```text
Normal: Ballroom A
Today: Cybersecurity Conference
```

The temporary event name, routes, opening times, and notifications should be reflected in guest assistance.

---

## QR wayfinding

Use QR codes as a reliable fallback to Wi-Fi positioning.

Example:

```text
Scan Lobby Elevator QR
  -> known starting zone
  -> guest asks for Spa
  -> deterministic route
```

---

## Digital twin

Future property overview:

```text
Property
- Building A
  - Ground
  - Floor 1
  - Floor 2
- Building B
- Outdoor
  - Pool
  - Beach
  - Garden
```

Use it for multi-building occupancy and navigation, but only after core map/zone functionality is mature.

---

## Offline / degraded mode

The on-prem product should continue core functions during cloud/provider outages.

Where practical keep available:

- ANTlabs guest flow
- property knowledge
- maps/navigation
- local AI
- service requests
- local event data
- basic analytics

Cloud services should enhance the platform, not become a single point of failure.

---

## AI guardrails

AI must never invent:

- prices
- opening hours
- facility availability
- hotel policy
- menu items
- event facts
- booking confirmation
- service completion
- weather

Required pattern:

```text
Verified Data / Tools
        ->
Policy Engine
        ->
AI
        ->
Guest Response
```

For actions:

```text
Guest Request
   ->
System / Integration Action
   ->
Confirmed Result
   ->
AI Response
```

---

## Privacy

Defaults:

- stay-based memory only
- pseudonymous Device ID
- no permanent raw-MAC guest profile
- limited location retention
- aggregate movement analytics
- no individual trails in general analytics
- configurable consent
- configurable retention
- audit sensitive access

---

## Role-based access

Suggested roles:

- Platform Admin
- Property Admin
- Hotel Manager
- Front Desk
- Operations
- Marketing
- Analytics Viewer
- IT / Network

Examples:

Marketing may manage campaigns/events but should not need raw network identifiers.

IT may manage AP mappings but should not automatically receive private guest conversation content.

---

## Integration model

Keep integrations adapter/provider-based:

- PMS
- WLAN
- ANTlabs
- POS
- restaurants
- spa
- housekeeping
- maintenance
- weather
- maps
- messaging
- n8n

Do not hardcode the overall product around one hotel vendor.

---

## Proactive decision engine

Future decision output:

```text
SEND
SUPPRESS
DEFER
REQUIRE HUMAN APPROVAL
```

Inputs may include:

- stay status
- consent
- time
- quiet hours
- current zone
- previous notifications
- weather
- hotel events
- reservations
- service requests
- facility status
- explicit guest preferences

AI writes the message only after an allowed decision.

---

## Recommended delivery order

### Stage 1 - Core foundation
1. ANTlabs authentication proof
2. production HTTPS/re-entry
3. property admin
4. AI providers
5. knowledge/RAG

### Stage 2 - Property intelligence
6. zone/floor editor
7. facility mapping
8. AP mapping
9. navigation
10. sessions
11. stay identity
12. AI stay memory

### Stage 3 - Analytics
13. live occupancy
14. heatmap
15. area analytics
16. dwell
17. movement
18. guest journey

### Stage 4 - Hotel operations
19. service requests
20. SLA
21. staff workflow
22. facility status
23. alerts
24. feedback

### Stage 5 - Proactive Stay Assistant
25. Notification Engine
26. AI notification guardrails
27. weather triggers
28. event notifications
29. restaurant/menu notifications
30. reservation reminders
31. stay-lifecycle notifications

### Stage 6 - Commercial intelligence
32. campaigns
33. offers
34. conversion analytics
35. facility performance
36. executive reporting

### Stage 7 - Advanced
37. precision indoor location
38. digital twin
39. event mode
40. simulation
41. multi-property control plane

---

## Product positioning

Concierge.AI can ultimately be positioned as:

> **An AI-powered hotel guest experience and property intelligence platform connecting Wi-Fi, guest context, hotel knowledge, location, operations, and proactive assistance throughout the stay.**

The system should progressively understand:

```text
WHO     -> pseudonymous active stay
WHERE   -> current zone
WHEN    -> time / stay lifecycle
WHAT    -> guest need or hotel event
CONTEXT -> weather / reservation / facility state
ACTION  -> answer / directions / service / notification
RESULT  -> request / visit / feedback / conversion
```
