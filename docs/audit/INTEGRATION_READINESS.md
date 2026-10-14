# Integration readiness

**Audit target:** `d5d006e89c38c0d901256d545679fee753175ef8`  
**Date:** 2026-10-14 (Asia/Manila)

| Integration | Local evidence | Live status / required work |
|---|---|---|
| OpenAI, Gemini, Groq, Claude, OpenRouter, Ollama/local compatible providers | Adapters/configuration in `app/ai_providers.py`; fake-backed tests cover routing, property scope, secret masking, streaming and failure behavior (`tests/test_ai_providers.py`, `tests/test_ai_provider_distributed_bulkhead.py`). | **IMPLEMENTED_NOT_VERIFIED.** No credentials or live provider calls. Verify model IDs, quotas, latency, failover, cost accounting and guest-data sharing policy per provider. No OAuth flow or consumer-subscription API access was demonstrated. |
| ANTlabs SG5 built-in processor handoff | Adapter contract tests in `tests/test_antlabs_adapter.py`; documented supported handoff and explicit mock/live distinction in `docs/ANTLABS_INTEGRATION.md`. | **BLOCKED.** No SG5 lab, target firmware, captive-network, hotel DNS/TLS, or disposable device. Handoff response is not proof of network admission. |
| ANTlabs mock mode | Mock behavior is explicitly labeled and exercised by tests/browser flows. | **VERIFIED AS SIMULATION ONLY.** Never represent it as a live connection. Production config rejects mock mode. |
| PMS room authentication and checkout/expiry | Guest-side fields and adapter contract exist. | **BLOCKED.** No target PMS, approved field mapping, checkout event, or physical device. Confirm whether room/last-name fields match property policy. |
| Local account / complimentary / access-code / credit-card processor | Current docs describe browser handoff for selected built-in processor methods; payment details remain on the gateway page. | **BLOCKED** pending gateway/configuration validation. No payment data should enter Concierge chat or provider context. |
| RADIUS, ACS/global account/code, user registration and social login | Mock paths/settings are not proof of live service; the ANTlabs plan says the current live adapter does not advertise these methods as supported. | **MISSING as live Concierge adapters** or **BLOCKED** on target-gateway contract/credentials; do not surface as ready. Implement and validate only against approved gateway specifications. |
| Guest session continuity, QR/NFC and captive mini-browser return | Session resume, expiry and replay controls pass local tests. | Session continuity on real captive browsers is **BLOCKED**. Dedicated QR/NFC device flow is **MISSING**; encoding the canonical URL externally is not a product feature. |
| PMS/POS/booking, external notifications, WLAN/AP feed | Data models and adapter foundations exist in parts of the repository. | **BLOCKED** without authorized vendor endpoints, test identities, business rules and notification recipient/frequency policy. No live delivery or WLAN tracking is claimed. |
| Reverse proxy, guest host and management network isolation | Local code/tests validate trusted forwarding, host/origin and CIDR rules; proxy/compose definitions exist. | **IMPLEMENTED_NOT_VERIFIED** on an actual hotel's DNS, TLS, proxy chain and VLAN. No gateway/network was contacted or changed. |

## Provider privacy boundary

Provider selection and configuration are property-scoped in local tests. Before live use, the property must approve which guest/session fields may be sent to each provider. This audit did not send guest content externally. API keys remain server-side in the tested configuration paths; OAuth support is not inferred from an available consumer subscription.
