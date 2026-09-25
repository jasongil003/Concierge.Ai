# Concierge.Ai Architecture

## Goal

Concierge.Ai turns the hotel guest Wi-Fi journey into a temporary, property-aware digital concierge.

The ANTlabs gateway remains responsible for network admission and Internet access. Concierge.Ai provides the guest experience, local AI, hotel knowledge, service orchestration, and session lifecycle.

## Prototype architecture

```text
Guest phone
    |
    | Hotel guest Wi-Fi
    v
ANTlabs SG5
    |
    | pre-auth walled-garden access
    v
Concierge.Ai web app
    |
    +--> Temporary guest session
    +--> Hotel knowledge / fast-path answers
    +--> Local LLM through Ollama
    +--> ANTlabs authentication adapter
    |
    v
ANTlabs guest authentication
    |
    v
Internet access
```

## Design principles

1. ANTlabs remains the network access authority.
2. The LLM never modifies firewall or gateway state directly.
3. Guest devices communicate only with Concierge.Ai before authentication.
4. The AI model is replaceable.
5. Hotel facts come from verified property data, not model memory.
6. Common answers bypass the LLM.
7. Guest context is temporary and expires automatically.
8. Sensitive hotel systems are accessed through adapters with minimum required privileges.

## Request routing

```text
Guest message
      |
      v
Fast path / cache?
  | yes        | no
  v            v
Answer       Retrieve hotel facts
               |
               +--> Live place lookup when relevant
               |
               v
          AI Orchestrator
          /      |       \
      Local    Gemini    OpenAI/Compatible
          \      |       /
           Fast / Auto / Advanced
                  |
                  v
               Response
```

The guest sees a simple Fast / Auto / Advanced mode switch. Provider names remain an administrator concern.

See [AI providers and routing](AI_PROVIDERS.md).

Future routing will add:

- service requests
- PMS-aware tools
- human escalation
- semantic cache
- small intent router

## Session lifecycle

```text
CREATED
   |
   v
PRE_AUTH
   |
   v
AUTHENTICATED
   |
   +--> ACTIVE
   |
   v
OFFLINE / IDLE
   |
   v
GRACE PERIOD
   |
   v
EXPIRED
   |
   v
CLEANUP
```

The current prototype uses an inactivity TTL. Production should also consume an authoritative ANTlabs/PMS logout or checkout event when available.

## Zone, Navigation, and Location Model

The roadmap foundation adds normalized SQLite tables for:

- buildings, floors, floor maps, zones, facilities, access points
- navigation nodes and navigation edges
- device identities, Concierge stays, guest sessions
- location observations, zone visits, movement transitions
- AI interaction and facility conversion events
- intro experience configuration

Every record is scoped by `property_id`; API handlers verify the property before mutating or reading resources. Guest-facing zone/navigation APIs return only guest-visible zones, facilities, corridors, entrances, elevators, stairs, and routes. They never return access point identifiers or operations-only WLAN details.

The V1 physical model is:

```text
WLAN device -> associated AP -> mapped zone -> facility
```

This supports aggregate occupancy and movement reporting. It must not be presented as exact indoor X/Y positioning. The deterministic navigation route graph is authoritative: AI can explain a route conversationally, but it should use route labels returned by the API rather than inventing path segments.

Future precision-location work can add BLE/UWB/RTT/multi-AP trilateration providers behind a separate adapter without changing the AP-to-zone aggregate analytics contract.

The WLAN integration boundary is `WiFiLocationProvider`. Vendor adapters should emit current client/AP observations with optional RSSI, controller, source, and timestamp metadata. The analytics layer consumes those observations only after the AP is mapped to a Concierge zone.

## Stay Memory

### Guest-controlled personalization

Guest preference memory lives in the separate `guest_personalization` and `guest_preferences` SQLite tables. It is scoped to both `property_id` and the opaque Concierge session id; guest endpoints first revalidate that session against the hotel's configured network and property boundary. The default is private. A hotel may suggest a default level, but the guest must opt in before saved preferences are collected or supplied to an AI provider.

Preference rows retain category, key, value, source, confidence, persistence, creation/update timestamps, and last use. Episodic language such as "tonight" creates a temporary preference with a six-hour expiry. Stay and profile entries expire under the hotel's configured retention policy and are removed at checkout when `delete_profile_at_checkout` is enabled. Profile-level preferences require the guest to choose Personal Concierge and remain scoped to that session; a durable returning-guest profile requires a future authenticated PMS or guest-account identity and is not inferred from a device identifier.

The guest can inspect, edit, remove, or clear preferences in Personalization / Memory or through conversational memory commands. Turning personalization off leaves entries available for the guest to review or clear but excludes them from future AI context. Hotel admins configure policy through RBAC-protected property settings; the settings API does not expose individual guest preferences. PMS data remains distinct from explicit and inferred preference rows.

Raw WLAN MAC addresses are not Concierge identities. When WLAN or ANTlabs provides a MAC server-side, Concierge.Ai normalizes it and derives:

```text
device_<HMAC(property_secret, normalized_mac)>
```

The AI memory anchor is `ConciergeStay`, not the device alone. Reconnect creates or restores an active stay for the property/device and stores only compact memory fields: conversation summary, explicit stay preferences, recent requests, unresolved service requests, and important context. Checkout anonymizes room/PMS fields and clears memory by default.

Randomized/private Wi-Fi MAC behavior is expected; integrations should treat device identity as best-effort session continuity, not permanent cross-stay tracking.

## Verified Hospitality Data and Proactive Assistant

Structured hospitality data now lives in normalized tables for facility profiles, restaurants, menus, menu items, hotel events, service requests, guest feedback, notification rules, notifications, notification deliveries, and guest journey events.

The guardrail model is:

```text
Verified data -> Trigger -> Eligibility -> Policy -> AI wording -> Delivery
```

AI can control wording, language, tone, and length. It cannot control or invent the trigger, guest eligibility, price, availability, event time, facility status, service completion, opening hours, or weather facts. Those must come from stored hotel data or trusted integrations.

Service requests move through confirmed backend states:

```text
New -> Assigned -> Accepted -> In Progress -> Delivered -> Completed
```

The guest-facing layer should only claim completion after the backend status is `completed`. Feedback is explicit (`yes`, `partially`, `no`) rather than inferred from sentiment.

## Network zones

Recommended hotel layout:

```text
                    ANTlabs SG5
                       |
          +------------+-------------+
          |            |             |
          v            v             v
      Guest VLAN   AI Service VLAN  Management VLAN
                       |
                       v
                 Concierge.Ai host
```

Recommended policy:

- Guest VLAN -> Concierge HTTPS: allow
- Guest VLAN -> management VLAN: deny
- Guest VLAN -> hotel back-office systems: deny
- Concierge host -> explicitly required hotel services only
- Concierge host -> Internet: optional, depending on deployment mode

## Local AI

Prototype default:

- Ollama runtime
- Qwen3 8B configured by default
- low temperature
- short output limit
- no extended reasoning
- small retrieved context

The runtime is intentionally abstracted behind `app/llm.py` so production can later use MLX, llama.cpp, vLLM, a private model server, or a cloud provider without changing the guest application.

## Scale

Do not size by total connected guests alone. Size by:

- simultaneous active AI generations
- prompt/context length
- output length
- model size and quantization
- percentage of requests served from cache/tools

A 1,000-guest hotel should aim to keep most repetitive requests off the LLM and benchmark realistic concurrent generation loads before production rollout.
