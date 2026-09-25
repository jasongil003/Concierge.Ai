# Concierge.AI — Current QA and Production Readiness Audit

Audit date: 2026-09-25. Scope: current workspace checkout, including changes already present in the worktree. This is a code and automated-test audit, not a live hotel, gateway, or production-provider certification.

# 1. Executive Summary

Concierge.AI is a capable single-service hotel concierge prototype. It has a real FastAPI backend, SQLite persistence, server-side admin authentication and permissions, property-scoped stores, a replaceable AI provider service, deterministic hotel answers, configurable guest services, and browser-tested guest/admin flows.

**It is not ready for production at a hotel.** The main risks are the guest trust boundary and missing operational proof. The server checks client IP against configured CIDRs, but ordinary guest chat does not require an authoritative gateway session. Optional ANTlabs request signing has a five-minute timestamp window and no replay nonce; the browser handoff contract is still a scaffold. RAG is keyword search over whole documents, not embedding/vector retrieval. No load benchmark supports the target of hundreds or thousands of guests. Docker build/runtime and real gateway/provider integration were unavailable.

The repository does implement useful controls: admin passwords use scrypt; admin sessions are server-side and revocable; production startup rejects demo credentials and unsafe secrets; admin writes require CSRF; route permissions are checked on the backend; property ownership is checked; guest network checks are server-side; outbound requests have SSRF controls; uploaded content is size/type constrained. These controls do not replace a tested production gateway boundary.

Verification:

- Python: **142 passed**.
- Playwright desktop Chromium and mobile Chrome: **167 passed, 11 skipped**.
- After the final password-recovery changes, the focused Chromium admin-auth suite passed **6/6**; this is a targeted rerun, not added to the earlier full-suite count.
- Python tests used an isolated temporary SQLite database and demo property. Browser tests used the Lunara seed. No paid model calls were made.
- Docker daemon was unavailable. Load testing and live ANTlabs/provider tests were not run.
- The worktree was already dirty at audit start. Existing user changes were preserved; this report does not attribute every pre-existing diff.

# 2. Architecture Map

Guest/Admin browser → static HTML/CSS/JavaScript → FastAPI/Uvicorn app → SQLite stores, property-scoped service layer, provider adapter service, optional ANTlabs / Google Places / SMTP / webhook integrations.

| Area | Actual implementation |
|---|---|
| Frontend | Plain HTML/CSS/JavaScript in app/static; no frontend framework or build step; Playwright E2E. |
| Backend | Python 3.12+, FastAPI, Starlette, Pydantic and Uvicorn. |
| Database / ORM | SQLite and handwritten SQL in store classes; no ORM. Admin auth has schema versioning and additive column checks; other stores mostly initialize with CREATE TABLE IF NOT EXISTS. |
| Authentication | Admin username/password, scrypt hashes, opaque random session token stored as a hash server-side, expiry/revocation, login lockout, HttpOnly/SameSite cookie, Secure in production and CSRF header on writes. Guests receive temporary session IDs. |
| RBAC | Server middleware maps admin routes to permissions and assigned properties; diagnostic tools check individual permissions on every invocation. |
| AI | AIProvider protocol and AIModelService support Gemini, OpenAI, Groq, OpenRouter, Claude and local OpenAI-compatible Ollama/LM Studio. No native Microsoft/Azure adapter; Copilot is explicitly unavailable. |
| Knowledge / RAG | Text/HTML/CSV/JSON extraction and keyword-overlap retrieval. Documents are stored in SQLite. No embeddings, chunking, vector DB, reranker or reliable conflict resolution. |
| Monitoring | SQLite samples for requests/latency/errors and host metrics when optional psutil exists; DB health and operations diagnostics. No external alerting or measured SLO. |
| Deployment | Non-root Dockerfile; Compose persists /state, sets production flags and healthcheck. TLS, reverse proxy and gateway are operator responsibilities. |
| Backups | SQLite backup/verify/restore code and upload archive support. No scheduled/off-host policy is configured in the repository. |

Major directories: app/ runtime and static UI; tests/ pytest and Playwright; data/ demo and Lunara hotel seed; docs/ architecture, deployment, gateway and provider guidance; audit/ prior audits and this report; scripts/ Docker smoke helper; outputs/ prior QA spreadsheets/screenshots.

# 3. QA Scorecard

| Area | Status | Explanation |
|---|---|---|
| Guest UI | PARTIAL | Browser suite passed; provider and network edge cases remain. |
| Guest AI | PARTIAL | Provider abstraction and deterministic hotel facts exist; live provider behavior was not exercised. |
| Personalization | PARTIAL | Opt-in, session-scoped preference storage and UI exist; broad multi-turn quality needs live evaluation. |
| Admin UI | PARTIAL | Core tested workflows work; several panels are roadmap placeholders and not every control was individually exercised. |
| Admin AI | PARTIAL | Uses permission-checked diagnostic tools and real app data; live model synthesis was not tested. |
| Authentication | PASS | Auth/browser regression tests pass; production config requires a changed bootstrap password and encryption secret. |
| RBAC | PARTIAL | Server permissions/property checks exist. A field disclosure gap was fixed and tested; full custom-role matrix remains. |
| Security | PARTIAL | Strong baseline controls; guest network/gateway trust and production operations remain incomplete. |
| Knowledge Base | PARTIAL | Text/FAQ records with size limits and property scoping; PDF/DOCX ingestion is absent. |
| RAG | FAIL | Keyword matching only; no chunks, embeddings, vector index, reranking or conflict policy. |
| AI Providers | PARTIAL | Multiple adapters and local mode; no Microsoft/Azure implementation or live outage certification. |
| Network Restriction | PARTIAL | Server-side CIDR checks; authoritative gateway-session proof is optional. |
| Monitoring | PARTIAL | Real app/DB metrics; host metrics may be unavailable and external alerting is absent. |
| Reporting | PARTIAL | XLSX/PDF generators and endpoints exist; production-scale values were not reconciled. |
| Performance | FAIL | No load measurements; SQLite write contention is a likely bottleneck. |
| Deployment | PARTIAL | Docker config exists; build/runtime could not run because Docker daemon was unavailable. |
| Backup/Recovery | PARTIAL | Backup/restore tests pass after fixing SQLite close behavior; off-host retention/drill is absent. |
| Production Readiness | FAIL | Gateway trust, RAG, deployment proof, capacity and operational ownership remain open. |

# 4. Critical Issues

| ID | Severity | Component | Problem | Evidence | Risk | Recommended Fix |
|---|---|---|---|---|---|---|
| C-01 | P1 | Guest network / ANTlabs | CIDR proves source network only. Signed gateway validation is optional; ordinary session start can proceed without it when disabled. Session ID is a bearer value and is not bound to a verified gateway session/device. Signature timestamp permits five-minute replay; no nonce store. | _enforce_guest_network, start_session, GatewayGuard.validate in app/main.py and app/guardrails.py; docs/ANTLABS_INTEGRATION.md states real SG5 validation is outstanding. | A device on an allowed subnet or a replay through a trusted network path can obtain a session without proof the guest was admitted by ANTlabs. | Require signed, short-lived assertion for session creation; include property/client/session/audience/nonce; persist nonce consumption; bind session to gateway identity; reject production startup without policy. |
| C-02 | P1 | Knowledge / AI | Retrieval is keyword overlap over whole documents; no chunk index, embedding or vector store. Conflicts can be ranked arbitrarily; citations/source priority are not enforced. | HotelKnowledge.retrieve in app/hotel.py; OperationsStore.search_knowledge and upload_document in app/operations.py. | Policies can be missed or answered from stale/conflicting content; the RAG claim overstates behavior. | Build property-scoped chunks with source/version metadata, source priority, embedding/vector backend, deletion propagation, citations and conflict handling. |
| C-03 | P1 | Reliability / capacity | No measured capacity envelope for 100–1000 guest target. SQLite receives synchronous telemetry, session and chat writes. | ObservabilityStore.record_request in app/observability.py; SQLiteRateLimiter.allow in app/guardrails.py; audit/29_LOAD_TEST_RESULTS.md records no measurements. | Lock contention and synchronous writes may raise latency/failures at scale. | Load test 10/50/100/250/500/1000 mocked-AI clients; profile SQLite/WAL, CPU/memory, p95/p99; define appliance envelope or move DB/limiter/queue. |
| C-04 | P1 | Production integration | ANTlabs mock mode is a development scaffold and browser handoff fields have not been certified against a real gateway. No real authentication round trip was run. | app/antlabs.py, docs/ANTLABS_INTEGRATION.md, example ANTlabs settings. | Production sign-in may fail or report gateway success without proof of real network admission. | Complete a lab integration against target SG5 version, validate signed/session fields, enforce production mode and document recovery. |
| C-05 | P2 | Tenant routing | Guest property selection uses request Host without itself proving the edge proxy accepted that hostname canonically. | PropertyGuard.resolve in app/guardrails.py; _guest_property in app/main.py. | A forged Host reaching the app can select another property’s guest-facing configuration if network controls also admit the request. | Enforce canonical hostnames at proxy and app; map property from trusted gateway assertion rather than arbitrary request headers. |
| C-06 | P2 | Account recovery | Request limits are 12/direct-peer/hour plus 3/hashed-account/hour; confirmation limits are 30/direct-peer/hour plus 10/hashed-token/hour. Reset tokens now use a URL fragment and the login page removes it from browser history. | request_admin_password_reset and confirm_admin_password_reset in app/main.py; fragment handling in app/static/admin-login.js; request/confirmation throttle regression tests and browser coverage. | If several users share one reverse-proxy peer address, the IP limits may aggregate their requests; email quotas are not configured. | Verify client identity and rate limits at the deployed proxy; configure email quotas and alerting. |

# 5. Functional Bugs

| ID | Component | Expected | Actual | Reproduction | Severity |
|---|---|---|---|---|---|
| F-01 | Guest provider routing | Respect selected provider/fallback and local-only policy. | Legacy exception branch called a separate global AI router after configured chain failed. Removed fallback; outage now returns friendly 503. | Force ai_models.concierge_chat to fail and ask advanced question; regression verifies 503 and no legacy call. | P1 — fixed |
| F-02 | Backup/verify on Windows | Close SQLite snapshots before temp directory cleanup. | Context manager committed but did not close connections; cleanup failed with file-in-use. Added explicit closing(). | test_backup_verify_and_actual_restore; final suite passes. | P2 — fixed |
| F-03 | Guest recommendations during outage | Keep verified recommendation cards available. | Chat error hid saved hotel recommendations. UI now shows those recommendations with outage message. | Fail provider and ask for dining; desktop/mobile tests pass. | P2 — fixed |
| F-04 | Admin request selector | Keep selected service during async refresh. | Refresh rebuilt options and reset selection. Preserve selected enabled service. | Create service, open requests, select and create; desktop/mobile test passes. | P2 — fixed |
| F-05 | Facility hours | Use configured pool/gym/spa profiles for combined questions. | Fast path only read legacy PropertyRecord fields. Added read-through to saved profiles. | Ask combined-hours question with structured facilities; Python/browser tests pass. | P2 — fixed |
| F-06 | Non-request admin role | Property content view must not expose service requests to roles lacking requests.view. | Shared hospitality response contained operations rows under property-view permission. It now omits service_requests and notification_rules without request permission. | Content manager requests hospitality overview; regression passes. | P2 — fixed |
| F-07 | Direct prompt filtering | Block explicit credential/admin/log/guest-list/command prompts before provider. | Initial patterns missed several phrases. Expanded classifier; 11-phrase regression ensures no provider call. | Send supplied direct attack list via guest chat; all return fast-path refusal. | P1 — fixed |

# 6. Security Findings

| Finding / attack scenario | Affected component | Severity | Recommended remediation |
|---|---|---|---|
| External user guesses URL or forges X-Forwarded-For to appear hotel-local. | Guest network guard | P1 | Server-side CIDR and spoofed-header denial tests exist. Shield origin, trust exact proxy ranges, and add signed gateway assertion in C-01. |
| Replay a signed session-start request within timestamp window. | GatewayGuard.validate | P1 | Add nonce replay protection and bind signature to a one-time gateway assertion. |
| Forge Host naming another property. | PropertyGuard / reverse proxy | P2 | Canonical host allowlist at edge and app; derive property from trusted gateway assertion. |
| Custom role with properties.view but not requests.view queries hospitality overview. | Admin hospitality endpoint | P2 | Sensitive records are now filtered and regression-tested. Review all mixed-sensitivity endpoints. |
| Flood password reset for a known account or brute-force confirmation. | Public password-reset endpoints | P2 | Generic request response; request and confirmation limits use direct-peer IP plus hashed account/token keys and are regression-tested. Reset token is in a fragment cleared from history. Validate shared-proxy behavior and email quotas. |
| Prompt asks for system prompt, .env, key, admin logs, guests or shell. | Guest AI | P1 | Direct attacks now blocked before provider and covered by regression. Continue testing indirect KB injection and live model output. |
| Upload unusual content or path-like filename. | Knowledge, maps, intro assets | P2 | Knowledge stored as text with limits; binary paths use generated IDs/basename. MIME is caller supplied for some binary assets and signatures are not consistently checked; sniff file signatures and test malformed/active content. |
| Unauthenticated admin call or CSRF. | Admin APIs | Reduced by controls | Server-side session, route permission, property ownership and CSRF exist. 150-route list is inventoried; not every endpoint had negative access tests. |
| SSRF via provider endpoint, webhook or place URL. | Outbound HTTP | Reduced by controls | Outbound broker/InternetGuard restrict protocols, ports and private addresses; existing tests pass. Revalidate DNS at connection and define redirect policy. |
| Steal/replay guest session ID. | Guest session | P2 | Admin token is stored hashed; guest ID is bearer value in sessionStorage and network-gated, not cryptographically bound to device/gateway. Bind session when integration permits and avoid logging IDs. |

Secret scan: .env is not tracked and values were not copied into this report. The local file has nonempty database and credential-encryption settings; provider API-key fields were empty in the scan. Source/tests include demo credentials (admin / ChangeMe123!) in test fixtures and setup docs; production config rejects the default password. Verify deployment secret provisioning.

# 7. AI / RAG Findings

- Grounding: Hotel fast paths read configured facts. Other answers use keyword retrieval, property data and optional external place results. Context titles are returned by API, but guests do not receive reliable source citations.
- Hallucination controls: Prompt tells model not to invent hours, fees, availability or completed actions. This is instruction, not a factual output verifier. Live-model accuracy was not assessed.
- Retrieval: Whole document body has an 8 MB upload ceiling and extracted-text ceiling; basic keyword overlap ranking. No chunk boundaries, embeddings, vector DB, reranker, source freshness or authoritative-source resolution.
- File types: TXT, Markdown, CSV, JSON and HTML text are supported; no PDF/DOCX extractor. Unsupported files are marked error rather than indexed.
- Prompt injection: Supplied direct attacks are now blocked before provider; 11-phrase regression passes. Retrieved/uploaded text is labeled untrusted data. Malicious KB injection was not tested against live model.
- Context: Guest history is session-scoped and bounded; preferences require opt-in and expire. Follow-up rewriting recognizes a short fixed topic list, so broad context continuity is unproven.
- Providers: Adapter abstraction supports multiple providers and local OpenAI-compatible endpoints. No native Microsoft/Azure adapter; Copilot is unavailable. Local-only chain filtering exists. Legacy global fallback that could bypass per-property routing was removed and tested.
- Tool safety: Guest AI has no server-command/admin tools. Admin tools are read-only and permission-checked.

Repeatable provider evaluation cases are in tests/ai_eval_cases.json. Deterministic FAQ/facility/recommendation/direct-injection/RBAC/provider-outage cases passed in controlled tests; live multi-turn, multilingual, conflicting-document and indirect-injection cases are not tested.

# 8. Guest Experience Findings

The mobile-first tested app has branded identity, suggestions, keyboard submission, new conversation, accessible menu actions, service confirmation, recommendation cards, details/directions and error handling. Configured facts/recommendations make it more hotel-aware than generic chat.

Personalization is session-scoped and opt-in. It supports preferences and limited follow-up reconstruction. Staff-like reasoning for “I’m hungry” → “Japanese” → “walking distance,” broad pronoun resolution, flight/traffic planning, multilingual quality and returning-guest identity are not established. No real-provider evaluation was run.

Responses are whole JSON bodies. Streaming, reconnection during an in-flight answer, network-loss recovery and standardized latency messaging are not implemented. Provider outage now preserves saved hotel recommendations.

# 9. Admin AI Findings

Admin AI uses real app stores and metrics through a diagnostic registry: DB health, provider state, request/AI usage, logs, knowledge counts, request analytics and report availability. Planner is constrained to permitted tools; registry re-checks permission; tools are read-only.

Natural-language synthesis comes from configured model. Prompts ask to distinguish observed facts, likely explanations and gaps, but that is not structurally enforced. Provider failure returns deterministic evidence. Live provider quality and role-specific synthesis were not tested.

# 10. RBAC Matrix

Actual built-in roles mapped to requested roles:

| Feature | Super Admin | Hotel Admin | Manager | Knowledge Manager | Support | Viewer |
|---|---|---|---|---|---|---|
| All-property/global settings | All | No | No | No | No | No |
| Property configuration | All | Assigned | View/edit | View/edit | View | View |
| Users / roles | All | Assigned-scope admin | No | No | No | View where granted |
| Knowledge / hotel content | All | Manage | Manage | Manage | View | View |
| Guest conversations / requests | All | Manage | Manage | No management by default | Manage | View |
| Analytics / management reports | All | All | View/export | View/export | No export by default | View/export |
| Provider configuration | All | Manage | View | No | No | View |
| Operations assistant | All | Use subject to tools | Business diagnostics | Permission-filtered | Limited diagnostics | Limited diagnostics |
| Infrastructure / DB telemetry | All | Granted | No | No | No | No |
| Security / audit | All | Assigned | No | No | No | Read only where granted |

Backend RBAC is enforced; UI hiding is not the only check. assistant.use alone does not grant diagnostics. Path-pattern permission dispatch still needs full custom-role/direct-API testing.

# 11. API Inventory

All 150 registered routes (method, endpoint, authentication, permission, status, response and shared validation/limits) are listed in [API inventory](31_API_INVENTORY_COMPLETE.md). Generated from app/main.py; this does not claim every route received a separate access-control test.

# 12. UI Control Inventory

Page/control results are in [UI control inventory](32_UI_CONTROL_INVENTORY.md). Main guest/admin browser flows were run in desktop Chromium and mobile Chrome. Controls still need manual review are marked partial; roadmap features are clearly identified as unavailable.

# 13. Performance Findings

No measured p50/p95/p99, throughput, CPU, memory, DB connection or error-rate figures exist. No paid-provider load was sent.

Likely code bottlenecks, not measured conclusions:

- SQLite connection and synchronous writes for request telemetry, session and chat state.
- SQLite limiter uses BEGIN IMMEDIATE, a serialization point at high rates.
- AI request blocks per conversation to provider timeout; no queue/cancellation/streaming.
- Places lookup is external I/O inside chat path.
- Compose runs one service with a local persistent volume; horizontal replica support is not defined.

# 14. Production Blockers

1. Implement/certify gateway-session proof, replay defense, canonical host and property binding.
2. Complete real ANTlabs authentication round-trip and fail production startup when required gateway policy is absent.
3. Build RAG or limit claims/behavior until chunking, embeddings, citations and conflict handling exist.
4. Mocked-AI load test through requested concurrency and establish capacity envelope.
5. Build/run Docker image; verify volume, restart and health; pin and scan base image.
6. Provision strong secrets, TLS, trusted proxy ranges, gateway ACLs, off-host backup/restore and alert ownership.
7. Run hostile upload, tenant isolation and route-by-route authorization suite in production-like deployment.

# 15. Recommended Fix Order

## Phase 1 — Security / Data Protection
- Require signed gateway assertions for guest chat/session in production; add nonce replay defense and canonical host validation.
- Verify property selection against forged Host and all property-scoped endpoints.
- Test every endpoint × role, including custom roles and admin AI tools.
- Validate password-recovery rate limits through the production proxy and configure email quotas.
- Validate file signatures and quarantine active SVG/HTML.

## Phase 2 — Broken Core Functions
- Complete real ANTlabs handoff/session binding.
- Preserve per-property provider/local-only invariant across every exception/fallback.
- Keep verified recommendations/hotel facts useful on provider outage.

## Phase 3 — Guest AI / Personalization
- Implement versioned chunk retrieval, embeddings, property-scoped index deletion, citations and conflict rules.
- Add live provider evaluation for context, unsupported answers, multilingual and indirect injection.
- Improve follow-up and travel planning without unverified claims.

## Phase 4 — Admin AI / Monitoring
- Structure observed metrics, calculations, recommendations and unavailable values separately.
- Probe provider/KB health with freshness timestamps.
- Add alert delivery, audit retention and permission-scoped logs.

## Phase 5 — Reliability / Performance
- Load-test 1/10/50/100/250/500/1000 mocked guests; then low-quota provider sample.
- Profile DB writes/locks; define metrics retention and scaling architecture.
- Test DB/provider/network failure, restart, disk pressure and Docker restore.

## Phase 6 — UX
- Complete network reconnect/in-flight recovery and long-message rendering.
- Finish screen-reader, contrast, zoom and supported browser review.
- Keep unavailable controls visibly disabled or labeled.

## Phase 7 — Production Hardening
- Document topology, secure update/rollback, TLS/proxy, secret rotation and restore drill.
- Add image digest/scanning, deployment smoke gate, dependency audit cadence and on-call ownership.

# 16. Missing Features

| Classification | Items |
|---|---|
| BUG | Fixed this pass: provider routing escape, Windows SQLite snapshot lock, outage recommendation loss, async selector reset, normalized facility lookup, mixed-sensitivity response, direct injection patterns, password-recovery request/confirmation limits and token URL exposure. |
| INCOMPLETE FEATURE | ANTlabs proof/handoff; network-to-session binding; admin alerts; RAG pipeline; capacity validation; recovery schedule; live provider health; full RBAC/UI control verification. |
| MISSING FEATURE | Embeddings/vector DB/reranker; PDF/DOCX extraction; native Microsoft/Azure provider; real Copilot integration; streamed chat; scalable queue/replica design; external alerting/SLOs. |
| ARCHITECTURE DEBT | Large route-centric app/main.py; path-string permission dispatch; many SQLite stores; keyword retrieval; provider capability mixed with fallback policy; incomplete centralized migrations. |

# 17. Automated Tests Added or Recommended

Added in this pass:
- test_guest_chat_does_not_escape_property_provider_chain_on_outage
- test_facility_hours_answer_uses_saved_facility_profiles
- test_property_viewer_does_not_receive_service_request_records
- test_password_reset_request_is_throttled_without_exposing_username
- test_password_reset_confirmation_is_throttled_with_hashed_token_key
- test_password_reset_email_places_token_in_url_fragment
- Expanded direct prompt-injection provider-bypass cases in tests/test_guardrails.py
- Machine-readable provider cases in tests/ai_eval_cases.json

Final tests: **142 Python passed**. The earlier full Playwright run passed **167**, with **11 skipped**; the final focused Chromium admin-auth rerun passed **6/6**.

Recommended:
- Gateway expiry/replay/wrong-property/session-binding.
- Every endpoint × role permission matrix, tenant A/B IDOR and reset abuse.
- Malformed MIME/content, huge/Unicode/path-like names, SVG active content and delete propagation.
- Conflict/staleness/citation and indirect injection against each provider.
- Docker backup restore with credentials/uploads and app restart.
- Mocked-AI concurrency, DB lock, timeout and provider-failure testing.
- Safari/Firefox, keyboard/screen reader, and browser network-loss testing.

# 18. Final Production Readiness Checklist

- [PASS] Python suite: 142 tests.
- [PASS] Earlier full desktop/mobile browser suite: 167 passed, 11 skipped.
- [PASS] Final Chromium admin-auth rerun: 6 tests.
- [PASS] Admin scrypt, sessions, CSRF, expiry/revocation tests.
- [PASS] Direct injection list blocked before provider in regression tests.
- [PASS] External guest IP and spoofed forwarding-header denial tests.
- [PASS] Provider credentials encrypted and omitted from settings response.
- [PASS] XLSX/PDF endpoints and report generator tests.
- [PASS] Backup/verify/restore tests after explicit SQLite close.
- [PARTIAL] Password recovery: request and confirmation limits plus fragment handling are tested; verify proxy client identity and email quotas in deployment.
- [PARTIAL] Admin RBAC: middleware and filtered mixed-sensitivity response verified; all routes/roles not tested.
- [PARTIAL] Tenant isolation: property checks exist; Host trust and full endpoint matrix remain.
- [PARTIAL] Guest network: CIDR is server-side; gateway assertion/session binding incomplete.
- [PARTIAL] Upload security: type/size checks exist; all hostile formats/content signatures not tested.
- [PARTIAL] Production auth: strong settings enforced; deployment secret/TLS provisioning external.
- [PARTIAL] Monitoring: DB/request metrics exist; host metrics may be unavailable, external alerts absent.
- [PARTIAL] Reporting: formats exist; production-scale reconciliation incomplete.
- [PARTIAL] Recovery: backup code/tests exist; off-host policy and restore drill absent.
- [PARTIAL] Multi-provider: several cloud/local adapters exist; Microsoft/Azure and live credentials absent.
- [FAIL] RAG production capability: keyword retrieval only.
- [FAIL] Guest network guarantee: CIDR is not proof of an admitted gateway session.
- [FAIL] Capacity target: no load measurements.
- [FAIL] Docker runtime verification: daemon unavailable.
- [NOT IMPLEMENTED] Native Microsoft/Azure, PDF/DOCX parser, vector retrieval and streaming.
- [NOT TESTED] Real ANTlabs SG5, real models, malicious KB injection against live model, Safari/Firefox, disk-full/proxy failure and production load.
- [FAIL] Overall production readiness until section 14 blockers close.

