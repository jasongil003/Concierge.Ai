# AI orchestration and guest action routing

## Provider routing

Intelligent UI continues through the established property-scoped `AIModelService`, provider selection, local-only setting, retry/fallback policy, quotas, and bulkheads. Native stream adapters are used only when their capability is implemented. Provider capability metadata no longer claims tool calling or vision where the adapter does not send those schemas/payloads.

Guest chat history is reloaded from the authenticated session and passed to the existing chat service. Client-supplied history is not trusted as context. Direct property answers (such as configured breakfast hours, Wi-Fi guidance, and facility profiles) remain server-side fast paths.

## Service actions

Clear English service-request phrases are routed to the existing deterministic configured-catalog proposal flow. Current regression examples include towels, shampoo, housekeeping, pillows, and air-conditioning repair. Dining questions, menus, table reservations, vegan/vegetarian options, and allergens are classified as dining/information and do not create service requests. Ambiguous, unsupported, cross-property, and adversarial prompts are included in the deterministic benchmark.

The router is not a generative tool selector. The backend matches only active, guest-visible services in the current property and returns either an explicit signed review proposal, a clarification when multiple catalog services match, or a truthful unsupported response. Confirmation is explicit; the server validates the signed, expiring token against the active guest session, property, configured service, and duplicate-request protections. Streaming events never execute these actions.

## Limits and benchmark boundary

`tests/ai_quality_benchmark.json` contains 100 synthetic prompts: 20 hotel information, 20 dining, 20 service requests, 10 ambiguous, 10 unsupported, 10 cross-property, and 10 adversarial. The test harness exercises deterministic routing controls. All `live_provider_status` values remain `not_run`; no natural-language model score, hallucination rate, multilingual quality score, or live provider success rate is claimed. Spanish examples exist in the older evaluation set but remain not tested with a configured model.

No model-generated booking, reservation availability, transaction, room assignment, or service completion is treated as authoritative.
