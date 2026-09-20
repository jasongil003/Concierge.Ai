# Concierge.Ai Master Product Plan

Concierge.Ai is evolving from an on-prem Wi-Fi concierge prototype into a commercial hotel guest experience, property intelligence, and proactive stay assistant platform.

## Product Pillars

1. Guest Wi-Fi and Concierge entry remain recoverable through ANTlabs or equivalent gateway flows.
2. Verified hotel data is the source of truth for facilities, menus, events, operations, and notifications.
3. AI may summarize, translate, personalize wording, and explain deterministic routes, but it must not invent prices, opening hours, availability, service completion, eligibility, or facility status.
4. Location V1 is AP-associated zone occupancy, not exact indoor positioning.
5. Guest identity is stay-scoped and pseudonymous by default.
6. On-prem operation must degrade gracefully when cloud AI, weather, or external APIs are unavailable.

## Current Implementation Status

Implemented foundations:

- Zones, floors, floor maps, AP mapping, guest-safe routes, and deterministic navigation graph
- Property-scoped pseudonymous device identity and Concierge Stay memory
- Location observations, zone visits, dwell, live occupancy, and aggregate movement reporting
- Intro experience configuration and validated animation uploads
- Vendor-neutral `WiFiLocationProvider` contract with a mock provider
- Structured facility profiles with opening hours, capacity, booking support, and live status
- Restaurants, menus, menu items, dietary/allergen metadata, and availability
- Hotel events with location, audience, capacity, CTA, and notification timing fields
- Service request lifecycle with SLA tracking and explicit guest feedback
- Notification rules, verified payloads, suppression guardrails, and delivery history
- Guest journey event tracking for adoption and conversion analytics

Hardware and integration validation still required:

- Real ANTlabs SG5 authentication contract
- WLAN/AP association feed and controller metadata
- PMS stay/check-in/checkout events
- Production weather provider
- Production notification delivery channel
- Production RBAC and admin authentication

## Implementation Order

1. Complete Zones and deterministic navigation.
2. Complete stay identity and memory lifecycle.
3. Complete AP-to-zone observations and analytics.
4. Add structured hospitality content: facilities, restaurants, menus, and events.
5. Add operations: service requests, SLA, feedback.
6. Add proactive assistant guardrails and notification engine.
7. Add reporting, journey analytics, data quality, simulation, and QR wayfinding.
