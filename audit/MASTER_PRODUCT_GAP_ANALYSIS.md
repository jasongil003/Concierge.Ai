# Master product gap analysis

Date: **2026-10-12–13 (Asia/Manila)** (audit began October 12, finalized October 13). Baseline `41c0ea1a7937035db6078cbb944f1e94f2fbad63`. Audited HEAD `d2d09ba9028448d7e2a88320643b1aaafb9004af`. Final tested implementation commit: `ecfe3f42963896cd86a291450fa574a4c26b197f`; reports are committed separately. Environment and actual commands/results match the [acceptance matrix](MASTER_FEATURE_ACCEPTANCE_MATRIX.md). Inventory work modifies only the two reports and machine-readable matrix.

## Current status continuation — PR #63, 2026-10-16

The rows below preserve the October 12–13 snapshot and are not a current inventory. Guest privacy consent, stay-bound location collection, checkout/withdrawal deletion, and notification opt-out were implemented through PR #61 and are regression-tested. The current acceptance ledger supersedes the historical gap statements: policy-dependent privacy rows are **BLOCKED** pending property data controller/privacy-owner approval of retention duration, deletion scope, guest-facing text and allowed audiences. The Conversations inbox and service-request queue have bounded server pagination, and the admin audit log now has filtered, bounded pages with stable ordering and property scoping; these are tested slices of C-30. Pagination for other high-volume admin lists, whole-property template cloning, campaign lifecycle/audience selection, monetary AI cost, and an explicit Lottie product decision remain open. Conversation search remains current-page scoped because message bodies are encrypted. Signed waypoint QR is implemented in PR #63; physical scanning and hotel map accuracy remain blocked by device/hotel acceptance.

Draft PR #63 is open. Latest hosted run [#262](https://github.com/jasongil003/Concierge.Ai/actions/runs/38870199927) validated the prior candidate: backend passed **1,349 tests, 19 skipped**; browser passed **357 tests, 41 skipped, 0 failed**; PostgreSQL/Redis, Docker, dependency audits, static security, and Linux/macOS deployment passed. PR-diff/current-worktree scans were clear; forced-text full-history Gitleaks found three known historical findings. The Guest Requests pagination follow-up has focused local evidence; hosted candidate validation is pending. See [current release readiness](MASTER_RELEASE_READINESS.md) for release decision and owner gates.

The planned product is incomplete: **213/384 (55.47%)** original requirements are locally verified. Current ledger counts: LOCALLY VERIFIED=213, IMPLEMENTED BUT UNVERIFIED=70, PARTIAL=56, BLOCKED=41, FAILED=4. Local passing tests do not establish a working hotel network, live AI/PMS/notification integrations, platform installs, or 30,000-user capacity.

## Highest-priority product gaps and confirmed corrections

| Priority | Gap | Evidence | Acceptance before closure |
|---|---|---|---|
| High (confirmed authorization defect, fixed) | Legacy manual knowledge bypassed publish permission | Editor-only custom role PUT with enabled=true returned HTTP 200 and 1 guest-eligible fact before fix; actor-aware guarded upsert, five host regressions and a separate native PostgreSQL publication-guard case now pass | Preserve permission/draft/race/action and native PostgreSQL guard regressions; complete representative multi-worker acceptance |
| Medium (confirmed defect) | PDF report body was off-page; fixed this audit | Relative Td accumulated coordinates; fixed absolute Tm/page-height pagination, actual reader and 2 regressions pass | Preserve coordinate/pagination tests and verify final candidate report exports |
| High | Location retention/consent lifecycle incomplete | `app/location_analytics.py` has no deletion path; stay retention is separate | Property-configured bounded location cleanup, checkout/consent behavior and negative privacy tests |
| Medium (High activation gate) | Notifications lack authoritative preferences/audience, frequency limits, minimum interval and dedupe | `app/hospitality.py:1544` evaluation; `:1736` policy only checks a few supplied facts | Server-owned active stay/preferences, atomic cap/dedupe, property timezone, source acquisition, durable delivery and opt-out tests before activation |
| High | No real SG5/PMS/WLAN proof | Adapters/contracts/mock provider plus acceptance docs | Authorized physical gateway/controller/PMS lab evidence for admission, walled garden, roam/reentry and checkout |
| High | Remaining clean-host/final-image/off-host acceptance gates | Host JUnit retains PG/Redis/Linux/systemd skips; separate actual container PostgreSQL 14 + approval 1 and Redis 4 pass. Clean-host/reboot/off-host and final image gates remain | Complete remaining clean-host reboot/update/rollback, final image scanning and encrypted off-host recovery; actual container migration/restore already passed |
| High | Capacity not measured | Serial TestClient and <=10 shell/health client-thread sample; bounded mocked semaphore tests | Progressive isolated representative loads with hardware, actual providers, p50/p95/error/CPU/RSS, queue and soak results |
| Medium | Provider cost estimation and monetary budget absent | `app/ai_providers.py` request/token limits; report labels cost unavailable | Versioned verified pricing, audited token/billing reconciliation and race-safe property spend limits |
| Medium | QR/NFC/known-zone wayfinding missing | Canonical host and route APIs exist; no product scan flow | Safe canonical/known-zone links, credential continuity and real device tests |
| Medium | Knowledge remains lexical; scanned PDF OCR absent | `docs/KNOWLEDGE_MANAGEMENT.md` and worker/store | Retrieval quality tests for intended semantics; OCR policy and target resource tests if scope retained |
| Medium | Admin pagination/complete sorting missing | Lists load arrays and filter locally | Bounded property/role pagination with stable ordering and browser controls for high-volume collections |
| Medium | Complete map/heatmap/peak/facility conversion reporting absent | PDF reference canvas, basic geometry; aggregate returns visit/dwell/movement only | Tested PDF background/point editing, time-bucket metrics and observed-correlation reporting |
| Medium | Lottie and arbitrary safe HTML/CSS not supported | Intro only MP4/WebM; design schema rejects arbitrary injection | Explicit product scope choice, then bounded sandbox implementation if retained |
| Medium | Live multilingual AI/guest UI acceptance incomplete | Language prompts/configuration are not translated product acceptance | Supported language catalog and live factual/error/action benchmarks |

## Production conclusion

**INTERNAL DEMO ONLY**. Open location privacy/notification policy and final-candidate CI, hotel proxy and hardware gates prevent a controlled hotel deployment. Do not advertise pilot or production readiness. Local tested boundaries are valuable foundations; missing privacy/notification controls and clean-host, hotel proxy, hardware and current image scan gates prevent complete product claims. Historical PR52 synthetic-merge CI passed nine jobs including PostgreSQL/Redis, Docker/Trivy and secret scanning, but failed browser tests (273 pass,35 skip,2 fail). This audit preserves and addresses failures; historical CI is not final-candidate certification. A runtime defect or unresolved High finding in the companion reviews may reduce this decision.

## Documentation reconciliation

Historical audit evidence is preserved. The baseline documentation contained contradictory/stale status statements; the parent has reconciled AI_PROVIDERS, ARCHITECTURE, roadmap and master plan with current acceptance evidence. The table below records statements before this audit, rather than continuing to assert they remain in the corrected documents.

| Document | Statement before this audit | Current evidence-based interpretation |
|---|---|---|
| docs/AI_PROVIDERS.md | Current limits says no admin login/RBAC, no guest streaming and fixed-only routing | Auth/CSRF/RBAC, provider circuit/retry/fallback, SSE guest endpoint and automatic/privacy/cloud routing now exist; OAuth and live providers remain incomplete/unverified |
| docs/ARCHITECTURE.md | Says raw messages never written to DB | Intelligent UI persistence stores encrypted conversation content; legacy history differs. Document feature-flag scope and retention explicitly |
| docs/MASTER_PRODUCT_PLAN.md | Current status says production RBAC/auth still required, notification delivery history implemented without distinguishing status | Local RBAC regressions pass; deployed auth acceptance still open. Notifications persist eligibility/suppression, not confirmed production deliveries |
| docs/ROADMAP.md | Many unchecked items coexist with implemented foundation list | Mark each item source-implemented/local-verified/blocked/missing separately; checkboxes alone are not acceptance evidence |

## Planned features beyond the A–R checklist

A–R is the requested 384-row acceptance denominator. The roadmap contains additional commercial/future scope; these are not silently counted as complete or included in the denominator. No deferral is assumed without a product decision.

| Additional planned scope | Assessment / next action |
|---|---|
| Signed offline-verifiable property license, asymmetric signature, node/room/feature/version entitlements, grace/expiry/revocation, activation/renewal | Roadmap unchecked; no dedicated license module found in app file inventory. Missing commercial feature group; define licensing without breaking ANTlabs guest network |
| Hotel-group/MSP organization/control plane, signed secure update delivery, release channels, central license/analytics management, cloud/hybrid migration | On-prem and multi-property foundations exist; dedicated full control plane/organization/partner roles and migration acceptance are not established |
| HA two-node operation, Redis/Postgres multi-worker certification | Tooling/integration tests exist; candidate service and failover/capacity evidence pending; clean host/reboot and representative capacity remain blocked |
| Voice concierge, PWA/add-to-home-screen, guest push channel, airport transport, late checkout upsell, paid reservation workflows | Product enhancement scope, not accepted by source presence; requires explicit priorities and external contracts |
| Weather provider, real restaurant/POS/booking integration, campaigns, simulation/event-mode/digital-twin maturity | Stored facts/mock observations do not complete production source acquisition or orchestration; separate adapters and accepted metrics needed |

## Remaining work by dependency class

- **Local software:** location retention/consent; notification policy/scheduler/delivery architecture; cost/budget accounting; pagination; QR/NFC; map/heatmap/peak/funnel completion; targeted accessibility/translations. Fix actual companion security/UI findings before expanding features.
- **Real hardware:** SG5 admission/walled-garden/captive and roam/reopen/checkout; AP association and zone accuracy; iPhone/Android keyboards/safe areas; clean macOS/Ubuntu installs and reboot/recovery.
- **External integrations:** approved AI provider credentials, PMS/POS/reservations, WLAN feed, weather and guest/staff notification channel. Copilot/Azure Foundry and OAuth are not supported working integrations merely from placeholders/schema.
- **Performance/capacity:** actual PG/Redis and controlled container restart/dependency recovery passed. Remaining: representative guest/AI load,worker/database/provider bottleneck measurement,hardware failover and soak. No 30,000-user claim.
- **Product enhancements:** licensing/control plane, voice/PWA/push, mature custom HTML/CSS/Lottie, precision positioning only after baseline hotel workflows.

## Execution evidence and limits

Backend baseline JUnit: 1100 PASS, 18 SKIPPED, 0 FAIL. Final local full-suite counts are calculated from backend-final.xml in matrix metadata; expanded host suite 1132 PASS,18 SKIPPED,0 FAIL, including dashboard, quiet-hours, PDF-layout and legacy publication regressions. Separate actual container PostgreSQL 14+publication1,Redis 4,Linux kernel probe 1,Docker 4 phases and controlled recovery 7 phases / 16 integration cases are recorded with scope; overlapping results are not added to unique host/browser totals. Security owner reports 660 PASS, 2 SKIPPED, 0 FAIL in broadened focused boundary run; no duplication is added to the full-suite test total. Final functional+visual browser run: 283 PASS,35 SKIPPED,0 FAIL in playwright-final-candidate.log; previous failures and focused reruns are retained in MASTER_TEST_RESULTS.md. Neither overlapping focused runs nor control inventories are added to the unique suite count. Inventory source review cannot make a skipped external test pass.

Next recommended local task: **Preserve the remediated High legacy knowledge publication boundary; then implement property-scoped location retention and guest consent lifecycle, with regression tests proving observation/visit/transition cleanup and checkout behavior; then harden notification authoritative eligibility, frequency and dedupe before enabling outbound automation.**

## Documentation corpus inspected

All listed files were read for requirements/status/blocker reconciliation, with critical architecture/master plan/roadmap/provider/knowledge/deployment acceptance sections reviewed in detail. Historical numbers and verdicts are not fresh evidence.

- `MANUAL_UI_CHECKLIST.md` (176 lines).
- `README.md` (309 lines).
- `SECURITY.md` (63 lines).
- `audit/00_EXECUTIVE_SUMMARY.md` (30 lines).
- `audit/01_SYSTEM_MAP.md` (65 lines).
- `audit/02_CONFORMANCE_BASELINE.md` (36 lines).
- `audit/03_THREAT_MODEL.md` (34 lines).
- `audit/04_SECURITY_ADMIN_AUTH.md` (29 lines).
- `audit/05_SECURITY_CROSS_TENANT.md` (25 lines).
- `audit/06_SECURITY_NETWORK_SSRF.md` (26 lines).
- `audit/07_SECURITY_XSS.md` (37 lines).
- `audit/08_SECURITY_AI_PROMPT_INJECTION.md` (20 lines).
- `audit/09_AI_PROVIDER_AND_FALLBACK.md` (18 lines).
- `audit/10_QA_FUNCTIONAL.md` (24 lines).
- `audit/11_OPERATIONS_RELIABILITY.md` (16 lines).
- `audit/12_DEPLOYMENT.md` (18 lines).
- `audit/13_SECURITY_HARDENING_BASELINE.md` (35 lines).
- `audit/14_MONITORING_OBSERVABILITY.md` (21 lines).
- `audit/15_MULTI_TENANCY_ISOLATION.md` (19 lines).
- `audit/16_DATA_LIFE_CYCLE.md` (20 lines).
- `audit/17_COMPLIANCE_RECOMMENDATIONS.md` (21 lines).
- `audit/18_FINDINGS_REGISTER.md` (43 lines).
- `audit/19_FIXES_APPLIED.md` (24 lines).
- `audit/20_REGRESSION_TESTS.md` (22 lines).
- `audit/21_QA_WALKTHROUGH.md` (24 lines).
- `audit/22_FINAL_REAUDIT.md` (34 lines).
- `audit/23_REMEDIATION_PASS.md` (29 lines).
- `audit/24_TENANT_ISOLATION_VERIFICATION.md` (17 lines).
- `audit/25_OUTBOUND_NETWORK_SECURITY.md` (11 lines).
- `audit/26_AI_PROVIDER_VERIFICATION.md` (11 lines).
- `audit/27_BACKUP_RESTORE_TEST.md` (17 lines).
- `audit/28_DOCKER_RUNTIME_VERIFICATION.md` (11 lines).
- `audit/29_LOAD_TEST_RESULTS.md` (9 lines).
- `audit/30_FINAL_PRODUCTION_READINESS.md` (30 lines).
- `audit/31_API_INVENTORY_COMPLETE.md` (214 lines).
- `audit/31_CURRENT_AUDIT.md` (342 lines).
- `audit/32_UI_CONTROL_INVENTORY.md` (41 lines).
- `audit/ANTLABS_ACCEPTANCE.md` (45 lines).
- `audit/CURRENT_READINESS.md` (70 lines).
- `audit/MANUAL_QA_2026-09-29.md` (172 lines).
- `audit/PRECONFIGURED_CONTENT_QA.md` (134 lines).
- `audit/PRODUCTION_READINESS_REPORT.md` (167 lines).
- `audit/PRODUCTION_SECURITY_CHECKLIST.md` (71 lines).
- `audit/REAL_DEVICE_ACCEPTANCE.md` (73 lines).
- `audit/REMEDIATION_AUDIT_001_002_2026-10-02.md` (115 lines).
- `audit/REMEDIATION_PROD_001_002_2026-10-02.md` (89 lines).
- `audit/SECURITY_TEST_RESULTS.md` (73 lines).
- `audit/VULNERABILITY_AUDIT.md` (97 lines).
- `audit/VULNERABILITY_FINDINGS.md` (213 lines).
- `audit/evidence/browser-2026-10-12/accepted-results/guest-guest-empty-property-c1241-ions-and-unsupported-routes-chromium/error-context.md` (318 lines).
- `audit/evidence/browser-2026-10-12/accepted-results/guest-guest-empty-property-c1241-ions-and-unsupported-routes-mobile-chrome/error-context.md` (318 lines).
- `audit/evidence/browser-2026-10-12/final-results/guest-guest-empty-property-c1241-ions-and-unsupported-routes-chromium/error-context.md` (294 lines).
- `audit/evidence/browser-2026-10-12/layout-after/guest-privacy-guest-privac-da21b-ed-conversations-truthfully-chromium/error-context.md` (53 lines).
- `audit/evidence/browser-2026-10-12/layout-after/guest-scrollbar-guest-home-3deb7-ent-with-classic-scrollbars-chromium/error-context.md` (61 lines).
- `audit/evidence/browser-2026-10-12/layout-after/guest-scrollbar-guest-home-3deb7-ent-with-classic-scrollbars-mobile-chrome/error-context.md` (133 lines).
- `audit/evidence/browser-2026-10-12/layout-final/guest-scrollbar-guest-home-3deb7-ent-with-classic-scrollbars-chromium/error-context.md` (136 lines).
- `audit/evidence/browser-2026-10-12/layout-final/guest-scrollbar-guest-home-3deb7-ent-with-classic-scrollbars-mobile-chrome/error-context.md` (136 lines).
- `audit/evidence/browser-2026-10-12/privacy-before/guest-privacy-guest-privac-da21b-ed-conversations-truthfully/error-context.md` (58 lines).
- `audit/evidence/browser-2026-10-12/scrollbar-before/guest-scrollbar-guest-home-3deb7-ent-with-classic-scrollbars/error-context.md` (141 lines).
- `audit/evidence/browser-2026-10-12/scrollbar-before-csp-safe/guest-scrollbar-guest-home-3deb7-ent-with-classic-scrollbars/error-context.md` (133 lines).
- `audit/evidence/browser-2026-10-12/test-results/guest-guest-privacy-menu-action-responds-chromium/error-context.md` (241 lines).
- `audit/evidence/browser-2026-10-12/test-results/guest-guest-privacy-menu-action-responds-mobile-chrome/error-context.md` (241 lines).
- `audit/evidence/security-2026-10-12.md` (80 lines).
- `docs/AI_PROVIDERS.md` (124 lines).
- `docs/ANTLABS_INTEGRATION.md` (177 lines).
- `docs/APPLIANCE_INSTALLATION.md` (324 lines).
- `docs/ARCHITECTURE.md` (231 lines).
- `docs/CONTROLLED_IMPROVEMENT_LOOP.md` (70 lines).
- `docs/CONTROLLED_POC_ACCEPTANCE.md` (151 lines).
- `docs/DEPLOYMENT.md` (307 lines).
- `docs/DISASTER_RECOVERY_REHEARSAL.md` (127 lines).
- `docs/GUARDRAILS.md` (28 lines).
- `docs/GUARDRAILS_CHECKLIST.md` (44 lines).
- `docs/KNOWLEDGE_MANAGEMENT.md` (84 lines).
- `docs/KNOWLEDGE_MANAGEMENT_QA.md` (24 lines).
- `docs/LOAD_TESTING.md` (76 lines).
- `docs/MASTER_PRODUCT_PLAN.md` (1047 lines).
- `docs/PRODUCTION_ACCEPTANCE.md` (150 lines).
- `docs/RELEASE_CONTROLS.md` (133 lines).
- `docs/ROADMAP.md` (726 lines).
- `docs/TEST_ISOLATION.md` (31 lines).
- `docs/audits/ECC_EXECUTIVE_SUMMARY.md` (37 lines).
- `docs/audits/ECC_FINAL_VERDICT.md` (64 lines).
- `docs/audits/ECC_FUNCTIONAL_FINDINGS.md` (40 lines).
- `docs/audits/ECC_INTELLIGENT_UI_READINESS.md` (44 lines).
- `docs/audits/ECC_PHASE2_FINAL_VERDICT.md` (13 lines).
- `docs/audits/ECC_PHASE2_FINDINGS.md` (18 lines).
- `docs/audits/ECC_PHASE2_REMEDIATION_BACKLOG.md` (15 lines).
- `docs/audits/ECC_PHASE2_TEST_RESULTS.md` (28 lines).
- `docs/audits/ECC_PHASE3_FINAL_VERDICT.md` (18 lines).
- `docs/audits/ECC_PHASE3_FINDINGS.md` (25 lines).
- `docs/audits/ECC_PHASE3_REMEDIATION_BACKLOG.md` (17 lines).
- `docs/audits/ECC_PHASE3_TEST_RESULTS.md` (81 lines).
- `docs/audits/ECC_PHASE4_FINAL_VERDICT.md` (21 lines).
- `docs/audits/ECC_PHASE4_FINDINGS.md` (32 lines).
- `docs/audits/ECC_PHASE4_REMEDIATION_BACKLOG.md` (17 lines).
- `docs/audits/ECC_PHASE4_TEST_RESULTS.md` (59 lines).
- `docs/audits/ECC_PHASE5_FINAL_VERDICT.md` (25 lines).
- `docs/audits/ECC_PHASE5_FINDINGS.md` (40 lines).
- `docs/audits/ECC_PHASE5_REMEDIATION_BACKLOG.md` (15 lines).
- `docs/audits/ECC_PHASE5_TEST_RESULTS.md` (59 lines).
- `docs/audits/ECC_PHASE6_FINAL_VERDICT.md` (13 lines).
- `docs/audits/ECC_PHASE6_FINDINGS.md` (36 lines).
- `docs/audits/ECC_PHASE6_REMEDIATION_BACKLOG.md` (16 lines).
- `docs/audits/ECC_PHASE6_TEST_RESULTS.md` (53 lines).
- `docs/audits/ECC_REMEDIATION_PLAN.md` (55 lines).
- `docs/audits/ECC_SECURITY_FINDINGS.md` (65 lines).
- `docs/audits/ECC_SESSION_EXPIRY_REVIEW.md` (49 lines).
- `docs/audits/ECC_TEST_EVIDENCE.md` (46 lines).
- `docs/intelligent-ui/ACCESSIBILITY_REPORT.md` (13 lines).
- `docs/intelligent-ui/AI_ORCHESTRATION.md` (19 lines).
- `docs/intelligent-ui/AI_QUALITY_BENCHMARK.md` (23 lines).
- `docs/intelligent-ui/ARCHITECTURE_BASELINE.md` (44 lines).
- `docs/intelligent-ui/BACKEND_INTEGRATION.md` (41 lines).
- `docs/intelligent-ui/COMPONENT_REGISTRY.md` (21 lines).
- `docs/intelligent-ui/CONVERSATION_PERSISTENCE.md` (23 lines).
- `docs/intelligent-ui/DESIGN_SYSTEM.md` (38 lines).
- `docs/intelligent-ui/FEATURE_FLAG_ROLLBACK.md` (27 lines).
- `docs/intelligent-ui/FEATURE_FLAG_ROLLOUT.md` (52 lines).
- `docs/intelligent-ui/FINAL_IMPLEMENTATION_REPORT.md` (86 lines).
- `docs/intelligent-ui/KEY_ROTATION_DESIGN.md` (34 lines).
- `docs/intelligent-ui/KEY_ROTATION_RECOVERY_RUNBOOK.md` (49 lines).
- `docs/intelligent-ui/LIVE_AI_BENCHMARK.md` (30 lines).
- `docs/intelligent-ui/LIVE_PROVIDER_PHASE5_RESULTS.md` (29 lines).
- `docs/intelligent-ui/LIVE_PROVIDER_RESULTS.md` (18 lines).
- `docs/intelligent-ui/OPERATIONS_ROLLBACK_RUNBOOK.md` (37 lines).
- `docs/intelligent-ui/PERFORMANCE_BASELINE.md` (17 lines).
- `docs/intelligent-ui/PHASE2_ARCHITECTURE.md` (42 lines).
- `docs/intelligent-ui/PHASE3_IMPLEMENTATION.md` (22 lines).
- `docs/intelligent-ui/PHASE5_DEVICE_ACCEPTANCE.md` (22 lines).
- `docs/intelligent-ui/PHASE5_IMPLEMENTATION.md` (42 lines).
- `docs/intelligent-ui/PHASE5_PERFORMANCE_RESULTS.md` (24 lines).
- `docs/intelligent-ui/PHASE5_RELEASE_CHECKLIST.md` (30 lines).
- `docs/intelligent-ui/PHASE6_DISASTER_RECOVERY.md` (21 lines).
- `docs/intelligent-ui/PHASE6_INFRASTRUCTURE.md` (44 lines).
- `docs/intelligent-ui/PHASE6_LIVE_AI_RESULTS.md` (13 lines).
- `docs/intelligent-ui/PHASE6_PERFORMANCE.md` (20 lines).
- `docs/intelligent-ui/PHASE6_RELEASE_ACCEPTANCE.md` (34 lines).
- `docs/intelligent-ui/POSTGRES_REDIS_ACCEPTANCE.md` (29 lines).
- `docs/intelligent-ui/RELEASE_ACCEPTANCE_CHECKLIST.md` (28 lines).
- `docs/intelligent-ui/RELEASE_CANDIDATE_CHECKLIST.md` (26 lines).
- `docs/intelligent-ui/ROLLBACK_PLAYBOOK.md` (27 lines).
- `docs/intelligent-ui/SECURITY_ASSESSMENT.md` (31 lines).
- `docs/intelligent-ui/STREAMING_PROTOCOL.md` (35 lines).
- `docs/intelligent-ui/STREAMING_PROXY_ACCEPTANCE.md` (20 lines).
- `docs/intelligent-ui/TEST_RESULTS.md` (50 lines).
- `docs/intelligent-ui/UI_COMPONENT_PROTOCOL.md` (48 lines).
- `docs/operations-console.md` (26 lines).

Roadmap unchecked checklist items encountered: **207**. Their text is retained below to keep broader planned vision visible; these are documentary requirements, not separate accepted feature counts.

- Validate SG5 external/full-custom portal flow on a lab gateway
- Capture exact login form/action/parameters
- Capture required gateway/downstream-client context
- Confirm supported success and failure redirects
- Validate pre-auth walled-garden access to Concierge.Ai
- Preserve gateway state using allowlisted/signed state
- Successfully authenticate a PMS guest through SG5
- Confirm ANTlabs, not Concierge.Ai, creates the Internet session
- Return or resume the guest Concierge after successful login
- Detect ANTlabs session logout/expiry where supported
- Test PMS checkout termination behavior
- Test iOS captive-network-assistant behavior
- Test Android captive-portal behavior
- Test roaming/reconnect without forcing unnecessary re-login
- Dedicated Concierge service VLAN/network design
- Reverse proxy on the on-prem runtime
- Customer hostname configuration
- Split-horizon/internal DNS
- HTTPS/TLS using ACME DNS-01
- Automated certificate renewal
- Ensure each property uses its own key/certificate
- Firewall policy: guest VLAN -> Concierge HTTPS only
- Prevent public inbound access to the on-prem runtime
- ANTlabs pre-auth HTTPS walled-garden configuration
- Canonical `/resume` flow after authentication
- Secure HttpOnly Concierge session cookie
- Session recovery after captive browser closes
- QR code pointing to the same canonical HTTPS URL
- Test Safari, Chrome, iOS captive browser, and Android captive browser
- Optional public informational page when the hostname is accessed off-site
- Per-property fast and advanced model selection
- Cloud-AI budget/usage controls
- Local fallback when public AI is unavailable
- Local embeddings/vector search
- Semantic response cache
- Conversation summarization instead of unlimited chat history
- Live restaurant/place recommendation UI
- Hotel-curated recommendation list as offline fallback
- Never invent business names, ratings, opening hours, or addresses
- Languages
- Intro mode: none / generated preset / custom upload
- Generate intro from uploaded PNG/JPG/SVG logo
- Built-in presets: minimal fade, fade + scale, luxury reveal, particle assemble, line draw, glass/blur, split reveal
- Logo-to-chat-header transition
- Duration, background/brand color, welcome message, and transition controls
- Mobile and desktop preview before publish
- Custom `.lottie` and Lottie `.json` upload
- Initialize guest/chat session while intro is playing where possible
- Keep After Effects `.aep` as a source-project format only; require export to a supported web format
- Later: PNG/JPG vectorization and AI-generated custom motion from logo + prompt
- Luxury hotel
- Business hotel
- Beach/resort
- Boutique hotel
- Serviced apartment
- Conference property
- Pre-auth preview
- Authenticated-guest preview
- Clone template between properties
- Hotel-group brand template
- Approved custom frontend package format
- HTML/CSS/assets/theme manifest
- Strict sandbox/content-security policy
- Asset/file validation
- Optional restricted JavaScript policy
- No arbitrary PHP/server-side code uploads
- Fixed Concierge API contract for custom frontends
- Preview/security scan before publish
- PMS guest-context adapter
- PMS connector interface
- Housekeeping connector
- Maintenance/ticket connector
- POS/dining connector
- Spa/reservation connector
- Messaging connector
- Optional n8n webhook/event connector
- `guest.connected`
- `guest.authenticated`
- `guest.disconnected`
- `guest.checked_out`
- `housekeeping.requested`
- `maintenance.requested`
- `late_checkout.requested`
- `human_handoff.requested`
- Add Buildings / Floors / Facilities / Access Points / Map Editor
- Upload floor plan: PNG/JPG/SVG/PDF
- Lock floor plan as the background layer
- Trace meaningful areas with rectangle/polygon/circle tools
- Map public facilities and aggregate guestroom wings/floors
- Do not require individual guest-room mapping for location analytics
- Place WLAN APs on the floor plan
- AP -> zone/facility mapping
- Navigation paths, entrances, elevators, and stairs
- Operations View with technical/AP information
- Guest View with public facilities/navigation only
- Current-zone API
- Deterministic hotel route graph
- AI explanation of deterministic routes
- Later: assisted area detection/OCR and multi-AP precision positioning
- Sessions tab: Active / History / Devices / Guest Stay / AI Memory / Location History
- Correlate ANTlabs and WLAN session data
- Convert raw MAC/network identity into a property-scoped pseudonymous device ID
- Create Concierge Stay ID
- Optional PMS Guest ID / room association
- Current AP and current zone in active session
- Resume the same active stay after reconnect
- Summarized AI stay memory instead of unlimited conversation history
- Stay-based guest preferences/context
- Configurable retention
- Delete/anonymize memory and location history at checkout/session expiry by default
- Do not create permanent cross-stay identity by default
- Live
- Heatmap
- Areas
- Behavior
- Movement
- Dwell Time
- Peak Hours
- Reports
- live zone occupancy
- unique visitors/devices by zone
- average dwell time
- peak occupancy and peak periods
- visit frequency
- repeat zone visits
- previous/next zone
- aggregated movement paths
- entry/exit areas
- historical trends
- most/least visited public areas
- facility inquiry -> directions
- directions -> observed zone visit
- AI recommendation -> observed facility visit
- facility inquiry -> booking/service request
- Property-based license
- Signed offline-verifiable license
- Asymmetric signature/public verification key
- Installation/node identity
- Allowed node count
- Room/license tier
- Feature entitlements
- Version entitlement
- Maintenance expiration date
- Optional 2-node HA entitlement
- Trial license
- Active/grace/expired/revoked states
- Admin license status page
- License activation API
- License refresh/renewal flow
- Optional periodic control-plane validation
- Signed gateway state
- Replay protection
- CSRF protection
- Rate limiting
- Secret encryption
- PII minimization
- Admin authentication/RBAC
- Audit log
- Privacy/retention controls
- Backup/restore
- Monitoring/alerting
- Health dashboard
- Dependency/security scanning
- Failure-mode tests
- AI-provider outage tests
- Internet-outage/local-fallback tests
- ANTlabs/PMS outage tests
- Load test 5/10/20/50 concurrent AI generations
- 1,000-connected-guest traffic simulation
- p50/p95 latency measurements
- CPU/GPU/memory measurements
- Queue/back-pressure controls
- HA local deployment option
- Multi-property tenancy
- Organization/hotel-group accounts
- Property provisioning
- Central configuration management
- Deployment status/health
- Release channels
- Secure update delivery
- License management
- Central analytics
- Hotel-template library
- Partner/MSP roles
- verified data determines facts
- notification policy determines whether contact is allowed
- AI generates wording only after approval
- quiet hours, consent, frequency caps, and suppression rules
- event notifications
- weather-aware assistance
- restaurant/menu notifications
- reservation reminders
- service-request status updates
- stay-lifecycle assistance
- notification delivery history
- engagement/conversion analytics
- privacy-safe context use
- Voice concierge
- PWA/add-to-home-screen experience
- Push/guest notifications where appropriate
- Restaurant/spa booking actions
- Airport transport workflows
- Late-checkout upsell
- Hotel service recommendations
- Optional guest preference memory limited to active stay
- Post-stay cleanup
- Hotel revenue attribution/analytics

Final tested implementation commit: `ecfe3f42963896cd86a291450fa574a4c26b197f`. Reports/evidence are committed separately; their receipt is discoverable with `git log -1 -- audit/MASTER_PRODUCT_GAP_ANALYSIS.md`. All test results refer to these unchanged committed implementation bytes, including explicitly scoped container receipts and local skips.

2026-10-16 continuation: Q-23 full-archive encryption is implemented locally with AES-256-GCM and an independent operator-recoverable key. Focused tests passed; off-host replication, separately retrieved escrow, legacy archive handling, and clean-host recovery remain blocked on the recovery owner and authorized target.
