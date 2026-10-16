# ECC continuous progress — 2026-10-16

Target remains a fully verified ECC release candidate by 2026-10-19. This report separates local and hosted evidence from property, production, and security acceptance.

## Baseline and pull request state

- Current `main`: `2f320df41dfc338ac60e5d662901a1cc5192875d`, which merges PR #61 (guest lifecycle, retention, and consent cleanup).
- PR #61 is merged. Hosted run [#246](https://github.com/jasongil003/Concierge.Ai/actions/runs/38835174052) passed backend (1,321 passed, 19 skipped), browser (339 passed, 39 skipped), PostgreSQL/Redis, Docker, dependency, static-security, and Linux/macOS deployment jobs. Its redacted current-worktree secret scan failed; its later forced-text step did not run. Docs-only run [#247](https://github.com/jasongil003/Concierge.Ai/actions/runs/38836604680) had the same secret-scan failure; all other jobs passed.
- PR #60 remains open. Its pre-update head was `8447e928c2af062e92ef4b5e55dae7e3058c9179`, based on `7185e18`; `main` advanced three commits after that base. The conflict resolution merges current `main` at `2f320df41dfc338ac60e5d662901a1cc5192875d` into that branch, preserving published history without a rebase or force update.
- PR #59 remains a draft; hosted run #240 failed the secret-scan job.
- The accessible ruleset previously inspected, `23912203`, did not require CI checks. Branch-protection administration was not accessible through the connected GitHub integration.

## Nearby recommendations and Places permissions — PR #60

- Complete-word and phrase matching prevents fragments such as “eat” in “theater” or “plan” in “planetarium” from triggering nearby searches.
- Restaurant and attraction permissions are checked independently against the requested categories. Mixed dining and attraction requests require both permissions; unrelated nearby categories keep the broad nearby gate.
- Focused nearby/privacy/context suite passed **56 tests** before this base update. The prior full backend run passed **1,319 tests, 20 skipped**.
- Hosted run [#245](https://github.com/jasongil003/Concierge.Ai/actions/runs/38753064200) passed backend, browser, PostgreSQL/Redis, Docker, dependency, static-security, and deployment jobs. Secret scan failed.
- Git automatically combined the overlapping application and privacy-test changes; only this added progress report had an add/add conflict. The report reconciles PR #60's Places work with the lifecycle changes now on `main`. Updated-head verification is recorded below.

## Workstream status

| Workstream | Status | Evidence and remaining boundary |
| --- | --- | --- |
| Guest stay lifecycle, privacy retention, and location cleanup | **YELLOW** | Merged to `main` through PR #61. Active stays no longer expire from a check-in deadline; post-checkout retention begins at checkout. Property/privacy policy approval and live ingestion/admin/export acceptance remain open. |
| Personalization retention and checkout deletion | **YELLOW** | Merged to `main` through PR #61; automated cleanup is covered. Property/privacy owner must approve retention and deletion semantics. |
| Notification consent and timezone handling | **YELLOW** | Merged to `main` through PR #61. Withdrawal cascades to linked sessions and suppresses old optional notices; DST quiet hours and invalid timezones are covered. PR #59 facility-state notices remain a separate draft. |
| Nearby recommendations and Places authorization | **YELLOW** | PR #60 implements phrase-boundary intent matching and category-specific permissions. Updated-head CI and secret-scan acceptance remain outstanding. |
| Historical credential and secret scan | **RED** | Runs #240, #245, #246, and #247 have failed a secret-scan job. The #246/#247 history scan passed while the redacted current-worktree step failed; the existing historical credential finding is not proven to be the cause. Credential validity/revocation is unconfirmed. No secret values are included here. |
| Deployment, recovery, and load | **YELLOW / BLOCKED for target environment** | Hosted deployment and Docker jobs passed. No hotel host or off-host backup/key-recovery target was available; 30,000-user load remains explicitly out of scope. |
| External pilot and production release | **NO-GO** | Secret-scan, required-check governance, approved privacy policy, and live hotel/provider/recovery acceptance remain open. |

## Verification and limits

- Local checks before the merge: focused lifecycle/consent/notification/personalization tests **48 passed**; full backend **1,319 passed, 21 skipped** on the lifecycle branch; browser **339 passed, 39 skipped**.
- PR #60's prior focused nearby/privacy/context suite: **56 passed**. After merging current `main`, the combined `test_places.py`, `test_guest_privacy_consent.py`, `test_notification_delivery.py`, and `test_personalization.py` suite passed **88 tests**, with 2 existing warnings.
- Python compile and Bandit at medium severity/confidence passed on the respective pre-merge branches. `git diff --cached --check` passed on the merged tree. Local Gitleaks is unavailable; do not infer secret-scan success from local checks.
- No real guest, hotel, production database, provider credential, or gateway data was used for these checks.

## Required owners and next steps

1. Credential issuer and repository owner: confirm invalidation, coordinate authorized history/clone/fork/cache remediation, and obtain a complete passing secret scan. This work did not rotate credentials, rewrite history, or suppress findings.
2. Repository administrator: configure required CI and security checks through an authorized control plane and verify merge protection rejects failures.
3. Property/privacy owner: approve location and external-processing policy, retention, notification audiences, and guest-facing text before live collection.
4. Hotel operations and recovery owners: validate routes, facility facts, delivery workflows, target-host installation, and encrypted off-host recovery in authorized staging.

Do not approve an external pilot or production release until the security, governance, property-policy, and operational gates have evidence.

## Continuation — 2026-10-16 (PR #59 refreshed against current main)

- Current `main` advanced to `6c8694916fdf0fe5aaf7f059813ba14004ea5f7f` when PR #60 merged. PR #59 is being refreshed against that base; this merge preserves the facility notification implementation and the newer Places/privacy changes already on main.
- The progress report conflict is resolved by retaining the latest main report and recording this continuation. The feature matrix notification row now describes the PR #59 facility notices while retaining its production-verification limits.
- The previous resolved PR #59 head `df971c7696277be28b478865e057744be752663b` had hosted CI run [#250](https://github.com/jasongil003/Concierge.Ai/actions/runs/38839977954): backend, PostgreSQL/Redis, Docker, dependency, static-security, and Linux/macOS deployment jobs passed; its current-worktree secret scan failed. Browser testing was still running at the last check. The refreshed head requires its own hosted checks.
- PR #59 remains a draft. No secret finding was suppressed, and no branch was merged into `main`.
- Refreshed-head focused validation: `.venv/bin/python -m pytest -q -rs tests/test_notification_delivery.py tests/test_admin_configuration_actions.py tests/test_guest_privacy_consent.py tests/test_personalization.py tests/test_places.py` — **104 passed**, 2 warnings. Compile and `git diff --check HEAD` are recorded after the final tree check.

## Continuation — 2026-10-16 signed guest wayfinding QR

| Workstream | Status | Evidence and remaining boundary |
| --- | --- | --- |
| Published waypoint QR entry and guest route origin | **YELLOW** | K-18 locally verified: signed property/node-bound HTTPS links, current published-map checks, property isolation, and route-origin handoff. Backend **6 passed**; admin QR **1 Chromium pass**; guest QR **2 desktop/mobile passes**. Physical QR printing/scanning and hotel map accuracy remain pending. |
| Current source security scan | **YELLOW** | Gitleaks 8.24.3 no-git redacted worktree scan after the QR change: **0 findings**. Historical full-history secret scan and branch-protection checks remain release gates. |

The guest browser flow filters the signed start parameters from gateway context and preserves the QR waypoint as the route origin across destination selection and a new chat. The feature tests use synthetic properties/maps; they do not establish physical-device, hotel-network, or production acceptance.
