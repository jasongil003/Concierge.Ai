# Phase 6 Live AI Results

## Status: BLOCKED / NOT RUN

No external model request was made for this phase. No explicitly authorized non-production provider credential, provider/model selection, cost ceiling, or approval for sending the synthetic benchmark dataset was configured. No credentials were read from a browser or personal account, and no hotel/guest content was sent externally.

The repository's supported provider modes and existing 100-case synthetic benchmark remain available. Their existence is not a completed benchmark. There are no case-level provider/model results, correctness or hallucination scores, prompt-injection outcomes, tool/action results, time-to-first-delta measurements, retry counts, or cost totals to report. Accuracy is **N/A**, not zero and not 100%.

## Required authorized run

Before execution, record written authorization, provider/model, approved dataset version, maximum request/cost budget, timeout/retry bounds, and a non-production credential source. Run the existing benchmark against synthetic cases only. Preserve each case ID, expected facts, outcome, action safety, component validity, latency, errors, and sanitized evidence. A response claiming a booking/service completion without an authorized backend action is a safety failure and must produce a regression test before release review.

Synthetic mock-provider and local routing tests must be reported as offline tests; they are not live-provider evidence. This gate remains open for ECC finding `AI-LIVE-001`.
