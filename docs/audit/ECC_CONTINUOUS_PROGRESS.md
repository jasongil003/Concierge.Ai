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
| Deployment, recovery, and load | **YELLOW / BLOCKED for target environment** | Hosted deployment and 