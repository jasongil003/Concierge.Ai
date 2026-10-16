# ECC continuous progress — 2026-10-16

<<<<<<< HEAD
Target remains a fully verified ECC release candidate by 2026-10-19. This report records the state observed on 2026-10-16; it does not treat local or synthetic evidence as production acceptance.

## Baseline and working change

- Repository: `jasongil003/Concierge.Ai`; `main` baseline `7185e18df2ae3b8f100804b7c3618a3909a831b6`.
- Working branch: `codex/guest-lifecycle-notifications-20261016`, based on that `main` commit.
- Local verified commit: `7031cf0eca6a076d5ab80d650be0d0e05874598d`.
- Published PR commit: `03f07aa9cfbe2029943cdec013524a3e85b48889`, created through the authenticated GitHub connector after local `git push` could not read a username credential. The 18-file tree was checked against the local Git blob hashes before publication.
- Draft [PR #61](https://github.com/jasongil003/Concierge.Ai/pull/61) is open against `main`. CI [run #246](https://github.com/jasongil003/Concierge.Ai/actions/runs/38835174052) completed with all jobs passing except `secret-scan`: backend **1,321 passed, 19 skipped**; browser **339 passed, 39 skipped**; PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed. `secret-scan` failed at the redacted current-worktree step; the later forced-text step did not run.
- Prior open drafts: [PR #59](https://github.com/jasongil003/Concierge.Ai/pull/59), facility status notifications; [PR #60](https://github.com/jasongil003/Concierge.Ai/pull/60), nearby Places permissions and intent handling. Neither is merged.
- PR #59 head `d670790f781d5d3b25fbc3f96c757d0a8f2e60ad`; CI run [#240](https://github.com/jasongil003/Concierge.Ai/actions/runs/38747435895) failed at secret scan.
- PR #60 head `8447e928c2af062e92ef4b5e55dae7e3058c9179`; CI run [#245](https://github.com/jasongil003/Concierge.Ai/actions/runs/38753064200) passed backend, browser, PostgreSQL/Redis, Docker runtime, Linux/macOS deployment, Python/Node dependency audit, and static security jobs. Secret scan failed. The run predates this working branch.
- `main` has no required CI checks configured in the accessible ruleset. Ruleset `23912203` only rejects deletion and non-fast-forward updates. The branch-protection API returned 403, so required checks could not be set through the available integration.

## Workstream status

| Workstream | Status | Commit / PR | Cause, fix, and evidence | Files changed | Remaining owner and next action |
|---|---|---|---|---|---|
| Historical credential and secret scan | **RED** | Base `7185e18`; PRs #59/#60/#61 runs #240/#245/#246 have failed secret-scan jobs | Existing audit records a real execution credential in reachable history; its value is not included here. PR #61 run #246 also failed its redacted current-worktree scan; this does not establish that the failure is the historical credential alone. Local Gitleaks is unavailable. No validity or revocation proof is available. | No secret-scan configuration or finding was changed. | Credential issuer must confirm invalidation/rotation. Repository owner must coordinate any authorized history cleanup and verify a complete history scan. No history rewrite, force push, or credential rotation was performed. |
| Guest stay lifecycle, privacy retention, and location cleanup | **YELLOW** | Local commit `7031cf0eca6a076d5ab80d650be0d0e05874598d`; published commit `03f07aa9cfbe2029943cdec013524a3e85b48889`; draft PR #61 | Local regressions pass: active stays no longer expire from a check-in deadline. Post-checkout retention is configurable on the server, begins at checkout, and repeat checkout does not extend it. Cleanup is property-scoped, idempotent, and uses atomic deletion; sessions/device associations and active-stay location and consent retention follow stay status. Long-stay, migration, reconnect, checkout, shared-device, concurrent-cleanup, orphan, consent, and property-isolation regressions pass. Hosted PostgreSQL/Redis integration passes on run #246. | `.env.example`, `app/config.py`, `app/guest_identity.py`, `app/location_analytics.py`, `app/main.py`, `app/privacy_consent.py`, `tests/test_guest_privacy_consent.py`, `tests/test_postgres_integration.py` | Property/privacy owner must approve the collection and retention policy. Review full deletion behavior against approved property policy before pilot. |
| Personalization retention and checkout deletion | **YELLOW** | Local commit `7031cf0eca6a076d5ab80d650be0d0e05874598d`; published commit `03f07aa9cfbe2029943cdec013524a3e85b48889`; draft PR #61 | Local regressions pass: active-stay preferences and personalization survive short inactivity expiry; cleanup purges configured profile/preferences after checkout. Regression covers five-day active stay and post-checkout purge. | `app/personalization.py`, `tests/test_personalization.py` | Property/privacy owner must approve retention and deletion semantics; browser control acceptance remains. |
| Notification consent, delivery scheduling, and timezone handling | **YELLOW** | Local commit `7031cf0eca6a076d5ab80d650be0d0e05874598d`; published commit `03f07aa9cfbe2029943cdec013524a3e85b48889`; draft PR #61. Facility state notices are separately in draft PR #59 (head `d670790f781d5d3b25fbc3f96c757d0a8f2e60ad`). | Local regressions pass: optional consent withdrawal cascades across linked sessions in one consent-store transaction. Optional inbox content is deleted and event tombstones prevent old notifications from reappearing after re-consent; the worker reconciles after interruption. Added spring-forward/fall-repeat quiet-hour and invalid-`ZoneInfo` regressions. Hosted backend, browser, and PostgreSQL/Redis jobs pass on run #246. | `app/hospitality.py`, `app/main.py`, `app/privacy_consent.py`, `tests/test_notification_delivery.py` | PR #59 and PR #61 remain drafts; PR #61 secret scan has failed. Real guest delivery and property acceptance remain unverified. Weather triggers remain blocked pending an approved source. |
| Nearby recommendations and Places authorization | **YELLOW** | Draft [PR #60](https://github.com/jasongil003/Concierge.Ai/pull/60), head `8447e928c2af062e92ef4b5e55dae7e3058c9179` | The PR constrains intent matching and requires permissions for the actual restaurant/attraction categories requested. Run #245 passed its non-secret checks, including browser tests. | PR #60 changes are on its own branch; not in PR #61. | Secret scan failure blocks merge. Live Places credentials, external-processing consent acceptance, provider outage behavior, and live provider correctness remain unverified. |
| Facility closure, maintenance, and reopening notifications | **YELLOW** | Draft [PR #59](https://github.com/jasongil003/Concierge.Ai/pull/59), head `d670790f781d5d3b25fbc3f96c757d0a8f2e60ad` | PR describes staff-approved facility-state triggers, active-stay/property-scoped delivery, preferences, quiet hours, deduplication, and failure isolation. PR verification reports 1,311 passed/20 skipped plus two browser checks. CI run #240 failed at secret scan. | PR #59 changes are on its own branch; not in the current working branch. | Review its current diff after privacy changes land; secret scan blocks merge. Verify real staff/guest delivery only in an authorized staging property. |
| Facility maps and directions | **YELLOW / BLOCKED for property proof** | No change in this branch; see `ECC_FEATURE_MATRIX.md` | Synthetic map editing, publication, graph, and route behavior are implemented and locally tested in prior audits. No approved hotel floor plans or physical walkthrough were available. | No change in this branch. | Property owner must provide approved plans and complete on-site route/accessibility acceptance; keep real-building accuracy unverified. |
| AI providers and external integrations | **YELLOW / BLOCKED for live proof** | No change in this branch; see `ECC_FEATURE_MATRIX.md` | Mock provider routing, encrypted credentials, fallback, and grounded answers have local evidence. No live provider account or production credential was used in this turn. | No change in this branch. | Provider owner must supply authorized staging credentials and acceptance scope; verify privacy, quotas, fallback, and tenant isolation. |
| Database, recovery, deployment, and load | **YELLOW / BLOCKED for target environment** | PR #61 run #246 passed PostgreSQL/Redis, Docker smoke, and Linux/macOS deployment. | New PostgreSQL regression ran successfully in hosted integration. No hotel host or off-host backup/key-recovery target was available. The 30,000-user load target remains explicitly out of scope. | This branch adds a PostgreSQL cleanup regression in `tests/test_postgres_integration.py`; no deployment files changed. | Operations owner must provide isolated staging for off-host backup/key recovery and target install/reboot acceptance. Do not use production data. |
| Branch protection and required CI | **RED / BLOCKED** | Base `7185e18`; ruleset `23912203` | Available ruleset only prevents deletion and non-fast-forward updates; it does not require CI. Branch-protection API access returned 403. | No change in this branch. | Repository owner must configure required successful CI checks through an authorized GitHub control plane. Do not merge until protection and all applicable checks are verified. |
| External pilot and production release | **NO-GO** | Current `main` baseline `7185e18`; PR #61 head `03f07aa9cfbe2029943cdec013524a3e85b48889` | PR #61 run #246 passed all checks except the redacted current-worktree secret scan. Main still lacks required checks; privacy policy and live hotel/gateway/provider/recovery acceptance remain open. | No release changes. | Release owner retains NO-GO until security, required protections, policy, staging acceptance, and production recovery gates have evidence. Production capacity evidence is also required except the explicitly deferred 30,000-user test. |

## Local verification on this branch

- Focused lifecycle, notification, and personalization suite: **48 passed**, 2 warnings.
- Full backend: `.venv/bin/python -m pytest -q -rs` — **1,319 passed, 21 skipped, 2 warnings** in 60.43 seconds. Skips include PostgreSQL/Redis/backup integration and platform-specific tooling; see the captured pytest summary and CI for service-backed evidence.
- Desktop/mobile browser suite: `npm run test:e2e -- --grep-invert @visual` — **339 passed, 39 skipped, 0 failed** in 6.3 minutes across Chromium and mobile Chrome emulation. The skips are the suite's project-specific and visual exclusions. It used the isolated Playwright server and disposable test database; generated tracked screenshot/inventory artifacts were restored after the run.
- `.venv/bin/python -m compileall -q app` — passed.
- `.venv/bin/bandit -q -r app -x app/static --severity-level medium --confidence-level medium` — exit 0, no findings; Bandit printed existing `nosec` and comment warnings.
- `git diff --check` — passed.
- Local `pip-audit -r requirements-dev.txt` could not upgrade pip in the sandbox, so it did not produce a local dependency audit. Hosted dependency audits passed on run #245, which predates this branch; no dependency files changed.
- Gitleaks is not installed locally. Do not infer secret-scan success from local checks.

## Release decision

**NO-GO for external pilot and production.** The code-level lifecycle and notification defects addressed in this branch have local regression evidence, but they do not resolve the reachable-history credential, required-check protection, property-approved privacy policy, or live hotel and recovery acceptance. Do not merge a PR while a required security check fails or an external/security gate remains open.
=======
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
>>>>>>> 96d832afe70781575e9e00a862d9c746dfcddd2d
