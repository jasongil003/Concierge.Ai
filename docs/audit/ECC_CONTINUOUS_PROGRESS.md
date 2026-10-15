# ECC continuous progress — 2026-10-15

## Verified baseline and release gate

- Fetched `origin/main`: `7185e18df2ae3b8f100804b7c3618a3909a831b6` (tree `277dd619401b21408bf487a6410895681f6a3cb6`). The work started from a clean checkout.
- Draft PR [#58](https://github.com/jasongil003/Concierge.Ai/pull/58) had the exact same tree as current `main`; it was closed as redundant and not merged.
- Main CI run [#238](https://github.com/jasongil003/Concierge.Ai/actions/runs/38741346522) completed with 9/10 jobs passing. `secret-scan` failed on three documented reachable-history detections. PR run #237 had the same result.
- The active `main` ruleset protects branch deletion and non-fast-forward updates but does not require CI status checks. The GitHub integration could not access branch-protection administration.
- Release status remains **NO-GO** until the secret-scan and required-check controls are resolved. No finding was suppressed, no shared history was rewritten, and no production operation was performed.

## Acceptance status

| Workstream | Status | Verified locally | Remaining boundary |
| --- | --- | --- | --- |
| Facility maps and directions | GREEN (synthetic) | Map revisions, routes, accessibility checks, and guest fallbacks are covered. | Approved hotel plans and on-site route walkthrough are missing. |
| AI providers | GREEN (deterministic) | Adapter, fallback, timeout, streaming, encrypted credentials, and privacy tests pass. | Live credentials and data-sharing authorization are missing. |
| Nearby recommendations | YELLOW | Complete-word intent matching and separate restaurant/attraction permissions pass the full local suite in draft [PR #60](https://github.com/jasongil003/Concierge.Ai/pull/60). | Hosted run #243 passed 339 browser tests (39 skipped) and every job except `secret-scan`; docs-only run #244 is checking the same code. Approved privacy policy and live Places checks remain outstanding. |
| Guest notifications | YELLOW | Facility closed/maintenance/reopen notice flow is implemented and covered locally. | PR #59 run #240 browser retry passed 339 tests (39 skipped); `secret-scan` still fails. Actual hotel delivery and weather alerts are unverified. |
| Guest privacy and security | RED | Consent controls and tracked snapshot checks exist. | Three reachable-history secret detections need issuer/repository-owner coordination; approved location/privacy policy is missing. |
| Deployment and recovery | YELLOW | Synthetic configuration, migration, backup, and CI deployment coverage exists. | Authorized clean target hosts, reboot/rollback, off-host backup, and separate key recovery are missing. |
| 30,000 concurrent users | DEFERRED | No capacity claim made. | Explicitly outside this completion pass. |

## Facility closure/reopen guest notices — PR #59

- Draft [PR #59](https://github.com/jasongil003/Concierge.Ai/pull/59) adds a shared facility-profile upsert path for the admin API and confirmed Admin AI actions. Changes into `closed`, `temporarily_closed`, or `maintenance` queue a property-scoped in-app operational notice for active stays; reopening queues a corrective notice.
- Delivery uses existing operational preferences, property timezone, quiet hours, send windows, deduplication, and inbox dispatch. A notification enqueue failure does not roll back the saved facility status.
- Local verification: focused backend tests **39 passed**; full suite **1,311 passed, 20 skipped**; guest inbox Chromium desktop and Pixel 7 mobile checks **2 passed**; compileall, `git diff --check`, and Bandit medium-severity/confidence scan passed.
- Latest hosted run [#240](https://github.com/jasongil003/Concierge.Ai/actions/runs/38747435895): all completed jobs passed except `secret-scan`, which failed. `browser-tests` was still in progress at the last check. Do not call this PR release-ready.

## Nearby intent and category permissions — current branch

- `GooglePlaces.should_search` and chat recommendation intent checks now match complete words/phrases, preventing fragments such as `eat` in “theater” or `plan` in “planetarium” from triggering a Places request.
- Fixed queries add explicit requested categories and map dining categories to `restaurant_search_enabled` and attraction/activity categories to `attractions_enabled`. A request for both requires both permissions; a single enabled category no longer authorizes searches for the disabled category. Generic pharmacy, shopping, and grocery categories keep the broad nearby gate.
- Regression tests first reproduced both defects. Focused nearby/privacy/context suite passes: **56 passed**. Full local suite: **1,319 passed, 20 skipped**, 2 warnings. `compileall`, `git diff --check`, and Bandit medium-severity/confidence scan pass.
- Current branch: `codex/fix-nearby-intent-permissions-20261015`, published as draft [PR #60](https://github.com/jasongil003/Concierge.Ai/pull/60). Hosted run [#243](https://github.com/jasongil003/Concierge.Ai/actions/runs/38751087470) passed 339 browser tests (39 skipped); every job passed except `secret-scan`. Docs-only run #244 is active on the latest branch head.

## External blockers and next steps

1. Credential issuer and repository owner: confirm revocation/rotation, then coordinate history and clone/fork/cache cleanup and rerun secret-scan. Keep the finding values out of reports.
2. Repository administrator: require the defined CI and secret-scan checks on `main` and verify merge protection rejects failures.
3. Property/privacy owner: approve location and external-processing policy, retention schedule, and guest-facing text before live collection.
4. Provider account owner: supply approved Places/AI credentials and confirm account, API, licensing, and quota access before a live connection test.
5. Hotel operations owner: validate plans, routes, closure facts, and notification workflows in an authorized staging property.
6. Recovery owner: provide disposable target hosts, PostgreSQL/Redis, encrypted off-host backup, and separately escrowed recovery key for a restore drill.

Do not merge a PR with failed required checks. Reassess release status only after hosted checks pass and the administrator has enabled required-check enforcement.

## GitHub follow-up

- PR #59 contains facility closed/maintenance/reopen notices. Run #240's first browser attempt had 337 passed, 39 skipped, and two failed admin-control tests; the targeted retry passed 339 tests (39 skipped). `secret-scan` failed.
- PR #60 contains Nearby phrase-boundary and independent category permission fixes. Run #243 passed 339 browser tests (39 skipped), backend, PostgreSQL/Redis, Docker, dependency, static-security, and deployment jobs. `secret-scan` failed. Run #244 is checking a documentation-only follow-up.
- Both PRs remain drafts; neither has been merged. The Git push could not authenticate from this workspace, so the verified local trees were published through the authenticated GitHub connector. No CI gate was bypassed.
