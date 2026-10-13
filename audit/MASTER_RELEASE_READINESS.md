# Master release readiness

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

## Remaining release gates and dependency classes

| Class | Required work / evidence | Current result |
| --- | --- | --- |
| Local software | Property-scoped location consent/retention/checkout/opt-out cleanup; authoritative notification audience/preferences, property timezone, frequency/dedupe, scheduler/durable delivery | Incomplete; highest-priority privacy/automation work |
| Local feature backlog | Monetary AI cost/budget accounting, semantic/vector retrieval, pagination, saved property-template cloning, QR/NFC/known-zone flow, reporting/map gaps and supported translations | Missing/partial/unverified as individually recorded |
| Real hardware | SG5 pre-auth/admission, captive browser recovery, physical QR/NFC, roaming/reconnect, mobile keyboards/safe areas and WLAN AP zone validation | BLOCKED by absent authorized hotel lab/device evidence |
| External integrations | PMS check-in/checkout, WLAN/controller feed, POS/booking, weather, delivery channel, authorized live AI quality/routing/grounding benchmark | BLOCKED; mock facts are not live integrations |
| Infrastructure | Actual hotel TLS/Nginx stream/host/CIDR/proxy behavior, clean install/upgrade/reboot/rollback, portable Phase6 native-host service-test execution and encrypted off-host restore/key recovery | Fresh local container PG/Redis migration/restore/recovery and persistence passed; target deployment acceptance remains blocked |
| Capacity | Representative progressive load/queue/provider/database bottleneck, outage/recovery and soak measurements with hardware details | 30,000 users remain a target, no achieved capacity |
| Product enhancements | OAuth, working Copilot/Azure Foundry, Lottie, licensing/control plane, voice/PWA/push and precision positioning | Not silently declared deferred; product scope/backlog required |

## Next recommended Codex task

Implement **property-scoped location privacy lifecycle**: define retention/consent policy, enforce ingestion/read/export authorization and opt-out, delete observations/visits/transitions at retention/checkout boundaries, and add positive/negative/reconnect/cross-property regressions. Preserve useful aggregate reporting only under an explicit privacy policy. Then implement notification eligibility/frequency/deduplication before any outbound activation.

Run final-candidate hosted CI, final-image vulnerability/secret checks and target Linux/hotel Phase 6 acceptance before any pilot review. Do not relabel the local 18 service/platform skips as passed, infer gateway authentication from a browser handoff, infer live delivery from eligibility rows, or infer indoor coordinates from AP association.

## Commands and audit navigation

Executed commands and actual results: [test ledger](MASTER_TEST_RESULTS.md), [security review](MASTER_SECURITY_REVIEW.md), [UI review](MASTER_UI_UX_REVIEW.md), [performance review](MASTER_PERFORMANCE_REVIEW.md), [remediation/commits](MASTER_REMEDIATION_LOG.md), [prioritized gaps](MASTER_PRODUCT_GAP_ANALYSIS.md), and [requirement matrix](MASTER_FEATURE_ACCEPTANCE_MATRIX.md). Raw records are under `audit/evidence/`; prior audit documents were preserved.
