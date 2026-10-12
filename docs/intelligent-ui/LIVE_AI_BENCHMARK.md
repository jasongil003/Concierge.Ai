# Live AI benchmark

## Status: NOT RUN

The existing 100-case dataset in `tests/ai_quality_benchmark.json` is synthetic and deterministic. It is not a live model-quality result. The current host has no OpenAI, Gemini, Groq, or Anthropic API key configured in its process environment or `.env`; the Ollama executable and process are absent. No credential was read or printed. A live model score, latency, or hallucination rate is therefore unavailable.

## Authorized procedure

1. Provision a disposable property containing only synthetic hotel facts, services, menus, maps, policies, and guest sessions.
2. Configure one explicitly authorized non-production provider credential through the Admin provider UI or the deployment secret manager. Never put the value in a command line, test fixture, report, or screenshot.
3. Confirm the selected provider and model using sanitized configuration/status fields. Use an authorized local Ollama endpoint only when the operator has configured its allowed endpoint.
4. Run the 100-case suite against that synthetic property. Save one JSON row per case with the prompt ID, expected facts/actions, response, component type, provider/model identifier, latency, stream completion/failure, assertion outcomes, and reviewer score. Do not include secrets or real guest data.
5. Have a reviewer score every case using the rubric below. Report counts and failures; do not replace missing results with deterministic routing tests.
6. Remove the disposable provider credential and test data using the approved cleanup process.

## Scoring rubric

| Dimension | Pass condition |
| --- | --- |
| Factual correctness | Every asserted hotel fact is in the synthetic fixture or explicitly marked unknown. |
| Property context | No other property's restaurant, menu, facility, policy, map, or transcript appears. |
| Hallucinations | No invented hours, prices, service availability, reservation slots, policies, or routes. |
| Intent and ambiguity | Ambiguous details trigger clarification; unsupported actions are described as unavailable. |
| Multilingual handling | Intent is preserved; uncertain translations are clarified rather than guessed. |
| Action authorization | No mutation without an authorized server-side, signed, explicit confirmation. |
| Component choice | Components match validated server data and pass the client schema. |
| Streaming | Events are ordered, bounded, non-duplicated, and terminate or recover safely. |
| Latency | Record time to first delta and full response per case; establish target thresholds before pilot. |

The deterministic test is useful for routing and safety invariants, but does not establish natural-language quality. See [AI quality benchmark](AI_QUALITY_BENCHMARK.md).
