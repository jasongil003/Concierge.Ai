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

Draft [PR #63](https://github.com/jasongil003/Concierge.Ai/pull/63) is mergeable and remains draft. Hosted run [#258](https://github.com/jasongil003/Concierge.Ai/actions/runs/38861282815) passed 9/10 jobs: backend **1,348 passed, 19 skipped**, browser **356 passed, 40 skipped**, and PostgreSQL/Redis, Docker, dependencies, static security, and both deployment validations passed. Only full-history Gitleaks failed on the three known historical findings; the changed-commit and current-worktree scans were clear. Release recommendation remains RED.

## 2026-10-16 candidate refresh — PR #63 run #259

- PR #63 remains open, draft and unmerged at head `4563d0064da1e306a67f173a8b729d99811aec7b`; `main` remains unchanged.
- Hosted run [#259](https://github.com/jasongil003/Concierge.Ai/actions/runs/38862722596) completed with **9/10 jobs passed**. Backend: **1,348 passed, 19 skipped**; browser: **356 passed, 40 skipped**. PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed.
- The PR-diff scan and current-worktree no-git Gitleaks scans were clear. The forced-text full-history scan found three known historical findings; no credential values are reproduced.
- The current ledger corrects privacy rows for existing stay-bound location consent, checkout/withdrawal cleanup and authoritative optional-notification opt-out. Property/privacy-owner approval of retention duration, deletion scope, consent copy and allowed audiences remains **BLOCKED**; live hotel/controller and provider validation remain outstanding.
- Release recommendation remains **RED**. No merge, deployment, history rewrite, or credential rotation occurred.

## 2026-10-16 local pagination slice — commit `97369c6`

- The property Conversations inbox now loads stable, bounded server pages (default 50, maximum 100), reports property/restaurant-role-scoped totals and status counts, filters status on the server, and supports previous/next controls. Search is labeled as page-scoped because stored message bodies are encrypted. Follow-up `adec402` preserves selected detail and updates it after status/reply/assignment mutations even when the filter removes the row from the current page.
- Focused backend/property-scope/privacy/notification regression set: **57 passed**. Focused Chromium pagination and existing takeover/reply/resolve/assignment workflows: **3 passed**. `node --check app/static/admin.js` and `git diff --check` passed.
- This is a partial C-30 acceptance: pagination for other high-volume admin lists remains open. The pagination slice was published at candidate head `46d6c1d2e3dbd6208c7aac3f80b80d2e4eb17013` and run #260 tested it. That run passed 1,349 backend tests, 19 skipped; its browser suite had 342 passed, 41 skipped, 15 failed. Twelve failures were six stale retention-race URL mocks that did not match the new pagination query string; the remaining three onboarding/network-access failures passed in isolated local reruns but need full-suite confirmation. A focused mock correction now passes all six retention-race tests in Chromium. PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed. PR-diff/current-worktree Gitleaks were clear; forced-text history scanning found the same three known historical findings. Full hosted rerun is pending publication.
- The local correction changed only the retention test route pattern from the old unpaginated path to the paginated request path. No product behavior was weakened or mocked outside that test route.

## 2026-10-16 PR #63 hosted run #261

- The query-aware retention mock correction is published at head `7b31f7201ceaaa235bba74d054ba706f60291554`.
- Hosted run [#261](https://github.com/jasongil003/Concierge.Ai/actions/runs/38868604334) completed with **9/10 jobs passing**: backend **1,349 passed, 19 skipped**; browser **357 passed, 41 skipped, 0 failed**; PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed.
- PR-diff and current-worktree Gitleaks scans were clear. The forced-text full-history scan again found three known historical findings; no credential values are copied here.
- Release remains **RED**. Main branch protection is still unavailable to this integration (HTTP 403); privacy-owner approval, issuer-side credential revocation, authorized history cleanup, hotel/device acceptance, and live integrations remain external gates. No merge or deployment occurred.

## 2026-10-16 Guest Requests pagination follow-up

- The Guest Requests queue now uses `GET /api/admin/properties/{property_id}/service-requests` with stable server pages (50 by default, maximum 100), server-side status and text filters, property-local completed-today logic, and summary counts over the full authorized property or department scope. The general hospitality overview no longer transfers all service-request records.
- `tests/test_service_catalog.py`, `tests/test_department_rbac_scope.py`, and `tests/test_restaurant_workflows.py`: **19 passed**. This covers paging across 55 records, no overlap across pages, stable tie ordering, cross-page search, status totals, property/department scoping, and denial without `requests.view`.
- Guest Requests Chromium browser checks: **3 passed**, including page navigation and full-queue counts. Bandit at medium severity/confidence, JS/Python syntax, and `git diff --check` passed.
- The developer virtualenv lacks the declared `qrcode` package. The local API/browser harness used a temporary import-only stub that raises if invoked; no test in this workstream exercises QR generation. The stub and all temporary dependencies/output were removed. Hosted CI for this candidate is pending.
- C-30 remains **PARTIAL** because other high-volume admin lists have not been paginated. Release remains **RED** pending hosted checks and the documented owner/integration/device gates.

## 2026-10-16 encrypted backup remediation

| Workstream | Status | Evidence and remaining boundary |
| --- | --- | --- |
| Full database/upload archive encryption | **YELLOW** | AES-256-GCM authenticated streaming encryption now covers SQLite and PostgreSQL backup ZIP payloads. Installers generate/preserve an independent 32-byte key; production Compose requires it; legacy plaintext is opt-in only. Focused verification: **155 passed, 2 skipped**. Hosted run #269 passed backend, PostgreSQL/Redis, Docker, static security, dependency, and deployment jobs; the full-history secret scan remains a release blocker. |
| Off-host backup recovery | **BLOCKED** | No authorized external destination, separate key-vault retrieval, or clean disposable target was available. Existing archives from older releases are not converted and remain legacy plaintext until aged out or explicitly migrated. Do not copy them off-host in plaintext. |

The key is excluded from backup contents and hidden from the settings object's representation. Recovery owners must escrow both the backup key and the existing credential-encryption key in separate protected records and perform the documented synthetic-data rehearsal before operational acceptance. The broader acceptance denominator and verified count do not change: Q-23 remains **PARTIAL** and no live verification is claimed. The PR remains draft and release acceptance remains **RED** because of the historical-secret scan and other external release gates.

## 2026-10-16 PR #63 hosted acceptance update — run #269

- Candidate head `9cbfc34fdc50c7c0c8e9102ddce159ab89ddadb7` completed hosted CI with **9/10 jobs passing**. Backend: **1,358 passed, 19 skipped**; browser: **359 passed, 41 skipped, 0 failed**. PostgreSQL/Redis, Docker runtime, Python/Node dependency, static security, and Linux/macOS deployment jobs passed.
- PR-diff and current-tree Gitleaks scans passed. Forced-text full-history scanning found **three historical findings**; values are omitted. Issuer revocation confirmation and owner-authorized history cleanup remain unverified.
- The scan's exact exception covers only a synthetic fixture removed from the current tree; no general rule or path was suppressed.
- Off-host backup replication, separate key retrieval, legacy archive conversion/expiry, and clean-target recovery remain blocked. Q-23 remains **PARTIAL**; verified acceptance totals are unchanged and release remains **RED**.
- No merge or deployment occurred. The 30,000-concurrent-user target remains deferred.

## 2026-10-16 PR #63 hosted acceptance update — run #271

- Code head `930e86def98ea8e0eb8f2ae2ed8c8bdb1ea1c734` completed hosted CI with **9/10 jobs passing**. Backend: **1,360 passed, 19 skipped**; browser: **361 passed, 41 skipped, 0 failed**.
- The new admin audit-log pagination scenario passed on Chromium and mobile Chrome. The server returns filtered, property-scoped pages with stable ordering, bounded page sizes and offsets, total counts, and stale-offset clamping.
- PostgreSQL/Redis, Docker runtime, dependency security, static security, and Linux/macOS deployment passed. Current-tree and PR-diff Gitleaks scans were clear; forced-text full-history scanning still reports three retained historical findings.
- C-30 remains **PARTIAL** while other high-volume admin lists and collection-wide conversation search remain open. Release remains **RED**; Q-23 remains **PARTIAL**; no merge or deployment occurred. The 30,000-user target remains deferred.


## 2026-10-16 continuation — campaigns, template cloning, and final local acceptance

- Added a property-scoped campaign draft/preview/publish workflow. The audience preview returns aggregate counts only; only active stays with an enabled promotional preference and promotional-message consent on every linked active session qualify. Publish rechecks consent transactionally and queues in-app guest inbox messages. Email/push delivery is not claimed. The three backend regression cases and Chromium/mobile campaign browser flow passed.
- Reconciled G-21 with the existing validated published-design copy endpoint and builder flow. Backend tests verify source/target isolation, CAS revisions, protected settings/credentials, and draft-only semantics; the desktop Chromium copy flow passed.
- Added page-specific guidance and related-page links for Notification Campaigns after the initial complete local browser run found a missing guidance link on desktop and mobile. The corrected complete run passed **368 tests, 42 skipped, 0 failed** in 6.8 minutes.
- Full backend run passed **1,380 tests, 21 skipped, 0 failed**. Bandit passed at the CI threshold, with only existing parser/nosec warnings. Redacted Gitleaks 8.24.3 current-tree scan found **0 findings**. Local tests used isolated state and the temporary qrcode import path; no production data/provider was used.
- Acceptance ledger totals: **216/384 core locally verified (56.25%)**, 70 implemented, 56 partial, 41 blocked, zero failed, and one core product deferral. H-05 Lottie is deferred per the user's October 16 direction; it remains in the denominator and has no verification credit. R-X01 alone is excluded.
- The published PR #63 head at the start of this continuation was `616de318bf85b8504852e3b8f6d18cc80ef091e7`. Its hosted [run #276](https://github.com/jasongil003/Concierge.Ai/actions/runs/38908867509) passed 9/10 jobs; backend/browser, PostgreSQL/Redis, Docker, dependencies, static security, and both platform deployment validations passed. Full-history Gitleaks alone failed on three retained historical findings. Connector publication of the reviewed updated candidate and its hosted run are pending.
- Release remains RED. The issuer and repository owner must complete revocation and authorized history cleanup; a repository administrator must require CI checks. Privacy policy, live hotel/provider/device validation, and off-host recovery remain open. No merge, deployment, or shared history rewrite occurred.
