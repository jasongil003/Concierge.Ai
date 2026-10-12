# Live AI provider results

## Current outcome

**NOT RUN pending authorization.** The process environment had no provider credential variables. Metadata-only inspection found one stored Gemini credential row and one Groq credential row in the local application database; their values were not read. Gemini is marked disabled (status `connected`), and Groq is marked enabled (status `not_configured`). These records do not establish that either credential is an approved test credential or that its property is synthetic. No synthetic prompt was sent externally while that approval is unknown. A ChatGPT consumer subscription is not evidence of API access or credit.

Source integrations include direct OpenAI-compatible adapters for OpenAI and Groq, Gemini, Anthropic Claude, an OpenRouter-compatible endpoint, and an operator-trusted local OpenAI-compatible endpoint (including Ollama). GitHub Copilot is explicitly unavailable in the provider catalog. Provider inventory labels are not proof that a credential, network route, or model is configured.

## Authorized operator procedure

1. Approve one test provider and confirm billing/limits, data handling, model, endpoint, and a synthetic-only test property. Use an existing authorized test credential from the secret manager; never read browser sessions or export a production credential.
2. Build a disposable hotel fixture with synthetic hotel hours, pool, restaurants/menu, facilities, policies, locations, guest-service catalog, and synthetic guest sessions. Confirm property IDs do not reference real guests.
3. Configure the provider on that test property, limit concurrency and output, and verify that server-side tool authorization and explicit guest confirmation remain enabled.
4. Run the repository's existing 100-case benchmark plus the provider and streaming regression suites. Preserve per-case IDs, expected behavior, result, latency/first delta, and sanitized failure category; omit prompts/responses if they contain any non-synthetic data.
5. Cover factual grounding, cross-property isolation, hallucinations, routing, ambiguity, unsupported requests, languages, prompt injection, component choice, streaming order/cancellation, provider failure, latency, and unauthorized state change. A deterministic mock/provider adapter result must not be labeled live model quality.
6. Revoke the temporary test credential and retain a sanitized report.

No case-level live scores, model latencies, streaming token timings, or provider-failure measurements are claimed for this Phase 4 run. Deterministic adapter tests are reported separately in `docs/audits/ECC_PHASE4_TEST_RESULTS.md`.
