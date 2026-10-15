# ECC continuous progress — 2026-10-15

## Verified baseline

- Latest fetched `origin/main`: `7185e18df2ae3b8f100804b7c3618a3909a831b6` (tree `277dd619401b21408bf487a6410895681f6a3cb6`). The workspace was clean before this continuation.
- PR #58 head `f4287c20febb4023179a1040540c244db4b223ec` has the same exact tree as `main`. Closed as redundant with a PR comment; no code was dropped and no merge was attempted.
- GitHub Actions main run [#238](https://github.com/jasongil003/Concierge.Ai/actions/runs/38741346522): 9/10 jobs passed; `secret-scan` failed on the three documented reachable-history detections. PR run [#237](https://github.com/jasongil003/Concierge.Ai/actions/runs/38738776409) had the same result.
- The active `main` ruleset protects deletion and non-fast-forward updates but has no required status-check rule. The GitHub integration returned 403 for branch-protection administration; its available repository settings tool is read-only.

## Acceptance status

| Workstream | Status | Current evidence and boundary |
|---|---|---|
| Facility maps and directions | GREEN | Synthetic map revisions, publication, routes, accessibility checks, and guest fallbacks are covered. Approved hotel plans and on-site route walkthrough remain BLOCKED. |
| AI providers | GREEN | Deterministic adapter, fallback, timeout, streaming, encrypted credential, and privacy tests exist. Live tests are BLOCKED on approved credentials and data-sharing authorization. |
| Nearby recommendations | RED | Source review found substring-based intent detection and category gating that treats either restaurant or attraction permission as permission for both. Fix is the next task. |
| Notifications | YELLOW | Existing inbox, request status, event reminders, retries, consent, and PostgreSQL-safe dispatch are tested. Facility closure/reopen fix is local and passing; weather alerts are BLOCKED because no approved source exists. |
| Guest privacy and security | RED | Hosted forced-text secret scan reports three reachable-history detections. Issuer revocation and repository-owner history cleanup require coordinated external action. Approved location/privacy policy is also BLOCKED. |
| Deployment and recovery | YELLOW | Synthetic configuration, migration, backup, and CI deployment coverage exists. Physical target install, reboot/rollback, off-host backup, and key recovery remain BLOCKED on authorized environments. |
| 30,000 concurrent users | DEFERRED | Explicitly outside this execution's completion requirements. |

## Facility status notice fix

- Added a shared facility-profile upsert path for the admin API and confirmed Admin AI actions. Transitions into `closed`, `temporarily_closed`, or `maintenance` queue a property-scoped in-app operational notice for each active stay; reopening queues a corrective notice.
- Notice content uses the staff-entered facility name and status note. Existing per-stay operational preferences, property timezone, quiet hours, send window, dedupe, and inbox dispatch are reused. Notification failures are logged without rolling back the verified facility status update.
- Reproduction: new regression initially failed because a maintenance update produced no guest inbox item. After the fix, tests cover operational opt-out, cross-property isolation, duplicate suppression, reopening text, and confirmed Admin AI updates.
- Tests: `.venv/bin/pytest -q tests/test_notification_delivery.py tests/test_admin_configuration_actions.py` — **39 passed**, 2 warnings. `.venv/bin/pytest -q -rs` — **1,311 passed, 20 skipped**, 2 warnings. `npx playwright test tests/e2e/guest-tools.spec.js -g "guest inbox renders safely" --project=chromium --project=mobile-chrome` — **2 passed**. Compileall and `git diff --check` passed. A first full-suite attempt caught test-property leakage; teardown was added and the rerun passed.
- Current branch: `codex/facility-closure-notifications-20261015`; implementation is published as draft PR [#59](https://github.com/jasongil003/Concierge.Ai/pull/59). Hosted CI run [#239](https://github.com/jasongil003/Concierge.Ai/actions/runs/38747253293) is in progress; do not treat this change as release-ready until its checks finish.

## Remaining P0/P1 blockers and next work

1. Fix and test nearby intent matching and enforce restaurant and attraction permissions independently; never send guest text to Places beyond fixed, allowed category queries.
2. Do not suppress the history scanner or rewrite shared history yet. The credential issuer must confirm revocation/rotation and the repository owner must coordinate all refs, forks, caches, and clone remediation.
3. A repository administrator must require the defined CI and secret-scan checks on `main`; current ruleset read access cannot write configuration.
4. Obtain approved property privacy/retention text, approved weather source, live provider credentials, hotel plans/network staging, and disposable target-host/key-recovery environments.

## GitHub follow-up

- Closed draft PR [#58](https://github.com/jasongil003/Concierge.Ai/pull/58) because its tip tree exactly equals current `main`. It was not merged; the current main secret-scan gate is failing.
- The branch was published through the authenticated GitHub connector after the local Git push could not authenticate. Draft PR #59 is open; CI run #239 is in progress. No branch-protection change, secret suppression, history rewrite, production operation, or real guest-data access has occurred in this continuation.
