# Master release readiness

## Current remediation update — 2026-10-16

**Decision: RED — RELEASE BLOCKED.** Work started from current GitHub `main` at `96d832afe70781575e9e00a862d9c746dfcddd2d` on `codex/final-remediation-20261016`. Source fixes are committed as `f8bcf3d`; property-scope coverage as `2a0cc6f`; signed waypoint QR as `3c4e3bd`; the hosted response-schema correction as `101ed7d`; and the Conversations pagination slice plus detail-state follow-up as `97369c6` and `adec402`. Draft [PR #63](https://github.com/jasongil003/Concierge.Ai/pull/63) remains open and unmerged. Hosted run [#260](https://github.com/jasongil003/Concierge.Ai/actions/runs/38866073706) completed 8/10 jobs: backend **1,349 passed, 19 skipped**; browser **342 passed, 41 skipped, 15 failed**; PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed. Twelve browser failures came from retention-race test mocks that still expected the pre-pagination URL; the route mock correction passes all six scenarios locally. Three more full-suite-only onboarding/network-access failures passed focused local reruns and still need confirmation in the full suite. PR-diff/current-worktree secret scans were clear; forced-text history scanning found three known historical findings. The 30,000-user target is deferred by the user and excluded from acceptance.

The [fresh acceptance ledger](acceptance-ledger-2026-10-16.json) contains all 384 core requirements and 13 supplemental rows. Core status is **213 LOCALLY VERIFIED (55.47%), 70 IMPLEMENTED, 56 PARTIAL, 41 BLOCKED, and 4 FAILED**. No LIVE VERIFIED result is claimed. Local status does not establish production readiness.

### Current remediation and validation

- Fixed the admin conversation-retention race across stale refreshes, property switches, edits made during save, failed saves, and server-canonical values. Six deterministic browser scenarios passed in Chromium and mobile Chromium (**12/12 runs**).
- Added property-local peak observed-hour reporting with daily pseudonym deduplication, bounded report intervals, and copy that explicitly describes sampled observations rather than occupancy. Property-isolation/timezone tests passed.
- Added an admin QR for the saved HTTPS guest origin, a scoped SVG endpoint, canonical URL copying, and NFC URL-record guidance. The endpoint requires `network.view`, checks property scope, and returns no-store SVG. Focused backend tests passed (**4/4**) and the focused Chromium UI test passed (**1/1**). Physical QR/NFC acceptance remains pending.
- Added signed, property-bound wayfinding QR links for published guest-visible map nodes. The guest start endpoint verifies the signature and current published map, and the guest flow carries the QR node into route-origin selection without adding signature parameters to gateway context. Focused backend tests passed (**6/6**); admin QR generation passed in Chromium (**1/1**); guest route flow passed in Chromium and mobile Chrome (**2/2**). K-18 is locally verified; physical scanning and hotel map/waypoint validation remain pending.
- Stay-scoped location consent, checkout/withdrawal deletion, and authoritative guest notification opt-out are implemented and regression-tested on `main` through PR #61. The remaining location-retention duration, deletion scope, consent copy, and allowed notification audience require property/privacy-owner approval; those policy-dependent acceptance rows are marked **BLOCKED** until approval.
- Added bounded server pagination to the property Conversations inbox: stable ordering, role-scoped counts, status filters, previous/next controls, and a maximum page size of 100. Backend/property-scope/privacy/notification regressions passed (**57/57**); focused Chromium conversation workflows passed (**3/3**). Search is current-page scoped; other high-volume admin lists remain to be paginated.
- Focused backend set: **19 passed**; guest-entry endpoint scope regression: **4 passed**. Latest full local backend run: **1329 passed, 21 skipped, 5 failed**. All five failures were installer checks unable to bind because a pre-existing local listener held port 8080; that process was left running. This is not reported as a green full-suite result.
- Full nonvisual browser run: **351 passed, 39 skipped, 0 failed** across desktop Chromium and mobile Chrome. Visual browser checks: **4 passed**. `git diff --check`, JavaScript syntax, and current Bandit scan passed. Final-manifest pip-audit found no known vulnerabilities; npm audit reported zero high-severity vulnerabilities. Gitleaks 8.24.3 no-git redacted scan after the wayfinding changes reported **0 current-worktree findings**; hosted full-history secret-scan validation remains required.

### Release gates still open

- Run #260's PR-diff and current-worktree scans were clear; its forced-text full-history Gitleaks scan found three known historical findings in `audit/evidence/security-2026-10-12/recovery-harness-before.txt`. The credential issuer must revoke the credential and confirm revocation. The repository owner must then authorize coordinated shared-history cleanup and rerun the scan. Cleanup was validated only in a disposable mirror; no shared history was rewritten.
- `main` branch protection is disabled. The GitHub integration returned HTTP 403 for rule administration. A repository administrator must require Backend, Browser, PostgreSQL/Redis, Docker, dependency, static-security, secret-scan, Linux-deployment, and macOS-deployment checks.
- Base-branch GitHub Actions run `38843201718` had **9/10 jobs pass**; `secret-scan` failed on historical findings. Draft [PR #63](https://github.com/jasongil003/Concierge.Ai/pull/63) remains open. Candidate run [#260](https://github.com/jasongil003/Concierge.Ai/actions/runs/38866073706) passed **1,349 backend tests**, while the browser suite had **342 passed, 41 skipped, and 15 failed**. Twelve failures were corrected locally by updating the retention-race URL mock for pagination; three other failures passed focused local reruns and require full-suite confirmation. PostgreSQL/Redis, Docker, dependencies, static security, and Linux/macOS deployment passed. The PR-diff/current-worktree Gitleaks scans were clear; forced-text history scanning failed on three known historical findings. Do not merge until refreshed browser CI, historical-secret remediation, required checks, and external acceptance gates are resolved.
- Remaining local feature requirements include pagination for other high-volume admin lists, whole-property template cloning, campaign lifecycle/audience selection, Lottie scope, and monetary AI cost. Privacy consent and deletion software is present; its policy-dependent acceptance remains **BLOCKED** pending the property data controller. Live AI/Places/PMS/WLAN/delivery acceptance and physical hotel-device validation still require their owners and credentials.

## Next independently actionable work

Continue server-side pagination for the remaining high-volume property-scoped admin lists. Keep campaign lifecycle/audience behavior behind explicit product acceptance, and retain the RED release recommendation until credential, governance, property-policy, live-integration, and device gates are closed.

The 2026-10-12–13 report below is preserved as a historical audit snapshot; its metrics and decision do not represent this remediation candidate.

---

## Historical release-readiness snapshot (2026-10-12–13)

Date: **2026-10-12–13 (Asia/Manila)**. Baseline: `41c0ea1a7937035db6078cbb944f1e94f2fbad63`. Branch: `codex/master-product-audit-2026-10-12`. Final tested implementation commit: `ecfe3f42963896cd86a291450fa574a4c26b197f`; backend fixes committed as `d2d09ba9028448d7e2a88320643b1aaafb9004af`. Report commit is discoverable with `git log -1 -- audit/MASTER_RELEASE_READINESS.md`; the report does not claim a future self-referential hash.

Environment: Darwin arm64, CPython 3.11.16, Node 26.7.0, desktop Chromium and Pixel 7 emulation. Test state is temporary synthetic SQLite plus isolated Linux containers with PostgreSQL 16/Redis; existing persistent state is guarded unchanged. Git fetch and GitHub evidence retrieval succeeded. No production deployment, merge, push, real customer mutation, provider credential bypass or hotel hardware test was performed.

## Decision

**INTERNAL DEMO ONLY.** The complete product vision is not achieved. Working local guest/admin workflows and corrected security boundaries support synthetic internal demonstrations. Open privacy/notification software requirements, absent target-environment acceptance and capacity evidence prevent a limited hotel pilot or production claim.

The matrix contains every original A–R bullet (384), plus five denominator-excluded clarifications. Its explicit VERIFIED COMPLETE count divided by 384 is the local acceptance percentage; full local implementation is 278/384 (72.40%) including implemented-but-unverified rows. Partial features and external foundations are not counted as complete. Current verified acceptance is **207/384 (53.91%)**. Exact final figures are in [the matrix](MASTER_FEATURE_ACCEPTANCE_MATRIX.md) and `master-feature-acceptance.json`.

## Verified evidence

- Backend final: **1132 PASS, 0 FAIL, 18 SKIP**. Broader security subset: 660 PASS, 0 FAIL, 2 SKIP, overlapping the full suite. Historical guest expiry-refresh/revocation and restricted-role regressions pass.
- Browser final: **283 PASS, 0 FAIL, 35 SKIP**, complete functional and visual suite across desktop Chromium and Pixel 7 emulation. Every previous reproduction/suite failure is retained separately; pending checks are not passes.
- Current npm audit: zero advisories. Fresh requirements-dev resolution: 78 packages, zero known advisories. Installed project environment after scoped tooling refresh: 97 packages, zero known advisories; pip check passed. Bandit threshold, compile/syntax, Compose configuration and whitespace checks passed.
- Bounded real loopback shell/health: 1/5/10 HTTP threads, 100 requests each, zero failures; owned app health returned after restart. This proves neither guest/AI capacity nor target hardware sizing.
- Final staging proxy: repeated startup/health passed; six bounded checks accepted canonical loopback login/health, denied anonymous admin, required HTTPS when supplied forwarding was present, and rejected an unconfigured host. App/data/cache remain internal; only proxy joins loopback ingress. All audit-owned resources and generated credentials were removed after verification.
- Fresh real service checks: PostgreSQL **14 PASS**, Redis **4 PASS**, PostgreSQL publication guard **1 PASS**; Linux memory enforcement probe passed. Container runtime smoke passed four phases; app/PostgreSQL/Redis interruption recovery passed seven phases including 16 integration tests. These overlap local tests and are reported separately.
- Historical PR #52 CI: nine successful jobs including PG/Redis migration/backup integration, Docker persistence/Trivy and secret scan; browser job had 273 PASS, 2 FAIL, 35 SKIP. It tested a PR merge/head, not this audit branch. Remote failure evidence drove the classic-scrollbar/readiness corrections.

## Confirmed corrections

Legacy dashboard permission/department projection; daytime quiet-hour predicate; truthful staff-access/transcript-retention disclosures; shared home/chat scroll track; empty quick-actions suppression; PDF export placement/pagination; PostgreSQL dashboard null-bind typing; PostgreSQL 16-compatible backup tools; fixed app/proxy address allocation; isolated recovery credentials/database fixtures; atomic legacy knowledge publication authorization; deterministic browser fixture readiness and isolated property setup; current evidence output preserving historical screenshots. Stale local development tooling was refreshed without changing unrelated environments. One High publication-authorization bypass was reproduced and fixed: a legacy knowledge editor lacking publish permission could enable or overwrite guest-visible facts. No Critical exploit was confirmed in this scoped audit. Remaining High release gates below are unresolved acceptance requirements, not fabricated exploit findings.

## Historical remaining release gates and dependency classes (2026-10-12–13 snapshot; superseded for current status above)

| Class | Required work / evidence | Current result |
| --- | --- | --- |
| Local software | Property-scoped location consent/retention/checkout/opt-out cleanup; authoritative notification audience/preferences, property timezone, frequency/dedupe, scheduler/durable delivery | Incomplete; highest-priority privacy/automation work |
| Local feature backlog | Monetary AI cost/budget accounting, semantic/vector retrieval, pagination, saved property-template cloning, QR/NFC/known-zone flow, reporting/map gaps and supported translations | Missing/partial/unverified as individually recorded |
| Real hardware | SG5 pre-auth/admission, captive browser recovery, physical QR/NFC, roaming/reconnect, mobile keyboards/safe areas and WLAN AP zone validation | BLOCKED by absent authorized hotel lab/device evidence |
| External integrations | PMS check-in/checkout, WLAN/controller feed, POS/booking, weather, delivery channel, authorized live AI quality/routing/grounding benchmark | BLOCKED; mock facts are not live integrations |
| Infrastructure | Actual hotel TLS/Nginx stream/host/CIDR/proxy behavior, clean install/upgrade/reboot/rollback, portable Phase6 native-host service-test execution and encrypted off-host restore/key recovery | Fresh local container PG/Redis migration/restore/recovery and persistence passed; target deployment acceptance remains blocked |
| Capacity | Representative progressive load/queue/provider/database bottleneck, outage/recovery and soak measurements with hardware details | 30,000 users remain a target, no achieved capacity |
| Product enhancements | OAuth, working Copilot/Azure Foundry, Lottie, licensing/control plane, voice/PWA/push and precision positioning | Not silently declared deferred; product scope/backlog required |

## Historical next-task recommendation (implemented since this snapshot)

The property-scoped location consent and cleanup lifecycle was implemented through PR #61 and is covered by the current acceptance ledger. Property/privacy-owner approval of retention duration and deletion scope remains open; see the current update above.

Run final-candidate hosted CI, final-image vulnerability/secret checks and target Linux/hotel Phase 6 acceptance before any pilot review. Do not relabel the local 18 service/platform skips as passed, infer gateway authentication from a browser handoff, infer live delivery from eligibility rows, or infer indoor coordinates from AP association.

## Commands and audit navigation

Executed commands and actual results: [test ledger](MASTER_TEST_RESULTS.md), [security review](MASTER_SECURITY_REVIEW.md), [UI review](MASTER_UI_UX_REVIEW.md), [performance review](MASTER_PERFORMANCE_REVIEW.md), [remediation/commits](MASTER_REMEDIATION_LOG.md), [prioritized gaps](MASTER_PRODUCT_GAP_ANALYSIS.md), and [requirement matrix](MASTER_FEATURE_ACCEPTANCE_MATRIX.md). Raw records are under `audit/evidence/`; prior audit documents were preserved.
