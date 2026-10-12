# Live provider Phase 5 results

## Status: BLOCKED / NOT RUN

No live AI call was made. No explicitly authorized non-production provider credential was provided for this Phase 5 benchmark. Credential values were not read, queried, copied, or exposed. No ChatGPT subscription or deterministic local test is treated as API authorization.

The existing `tests/ai_quality_benchmark.json` contains 100 synthetic cases: hotel facts, dining, service requests, ambiguity, unsupported actions, cross-property attempts, and adversarial prompts. It does not contain dedicated multilingual or streaming-interruption scenarios; add those as separately labeled supplemental cases to the authorized live run. The deterministic test suite covers local routing and safety invariants. It does not produce model correctness, hallucination, multilingual, or streaming latency scores.

| Measure | Phase 5 result |
| --- | --- |
| Provider / model | None selected; no live provider configured for this run |
| Live cases | 0 / 100 |
| Correctness score | N/A |
| Hallucination rate | N/A |
| Tool/component selection | No live output to score |
| Authorization outcomes | No live actions attempted |
| First-token and full-response latency | N/A |
| Token use / retries / provider errors | N/A |

## Safe operator procedure

1. Obtain explicit approval for a disposable, non-production provider credential and synthetic data transfer.
2. Create an isolated synthetic property and guest sessions; verify property IDs and test-only action catalog.
3. Configure credentials only through the approved secret manager or admin provider configuration flow. Never put values in shell arguments, fixtures, reports, browser storage, logs or screenshots.
4. Run all 100 base cases plus separately identified multilingual and streaming-interruption cases. Save sanitized per-case provider/model, expected facts/actions, actual result, correctness, hallucination, tool/component choice, auth outcome, first-token/full latency, token count and retry/error fields.
5. Have a reviewer score each case, including injection, cross-property, multilingual and interruption cases. No unsigned or unconfirmed service action may mutate state.
6. Remove the test credential and disposable data through the approved cleanup process.

Use the scoring rubric and dataset reference in [AI quality benchmark](AI_QUALITY_BENCHMARK.md). No quality number should be filled in until an authorized live run completes.
