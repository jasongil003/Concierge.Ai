# Concierge.AI — Current QA and Production Readiness Audit

Audit date: 2026-09-26. Scope: worktree on `audit/production-readiness-final` at `5a71800`, matching the locally cached `origin/main` ref. The initial worktree contained 15 modified tracked files; they were preserved. `git fetch origin` could not authenticate to GitHub, so the current remote tip could not be verified. This is a code and automated-test audit, not a live hotel, gateway, or production-provider certification. No commits or pushes were made.

# 1. Executive Summary

Concierge.AI now includes a property-scoped restaurant operations workflow alongside its hotel concierge features: admins create and archive restaurants, managers and staff receive permission-bounded restaurant assignments, menu and promotion changes pass approval before publication, and staff can take over guest conversations. Backend checks enforce role and restaurant scope on direct API calls.

**NOT READY for production certification.** Signed ANTlabs assertions have persistent one-time nonce consumption, timestamp bounds, source CIDR checks, and property binding. These checks do not prove that ANTlabs admitted a guest to the network or bind the Concierge guest session to a gateway device. Real SG5 and hotel Wi-Fi validation, production proxy/TLS setup, live provider checks, higher-concurrency load testing, and Docker runtime verification remain outstanding. Knowledge retrieval uses source-located lexical chunks with explicit fact-conflict review; dense semantic search and guest-visible citations remain open.

The repository does implement useful controls: admin passwords use scrypt; admin sessions are server-side and revocable; production startup rejects demo credentials and unsafe secrets; admin writes require CSRF; route permissions are checked on the backend; property ownership is checked; guest network checks are server-side; outbound requests have SSRF controls; uploaded content is size/type constrained. These controls do not replace a tested production gateway boundary.

Verification (local, 2026-09-26):

- Python: **516 passed, 0 failed, 8 skipped**; two upstream deprecation warnings. `compileall` passed.
- Playwright desktop Chromium and mobile Chrome: full run **170 passed, 4 failed, 14 skipped**. The functional suites passed; the four failures are missing Darwin screenshot baselines (the checked-in snapshots are Win32). The assignment-checkbox workflow passed after fixing an overlapping-request race.
- `npm audit --audit-level=high`: **0 vulnerabilities**.
- `pip-audit -r requirements.txt`: **no known vulnerabilities**. `npm audit`, Python compile, JavaScript syntax checks, YAML parsing, `docker compose config --quiet` with temporary local secrets, `git diff --check`, Bandit, and SQLite integrity checks passed. Tests used local SQLite and the Lunara seed. No paid model calls were made.
- Mocked-AI Locust smoke: 10, 25, and 50 guest users passed with zero failures; the 100-user stage hit the configured per-source-IP session-start limit (96 HTTP 429s), so higher concurrency was not meaningful from this single injector. No database-lock errors appeared.
- GitHub Actions definitions include pytest, compileall, Python and npm audits, Playwright, Docker build/runtime and persistence smoke. CI was not run from this workspace. Docker daemon access confirmed unavailable. GitHub fetch also failed because credentials were unavailable.
- FastAPI's default OpenAPI and interactive documentation routes are registered without app-level authentication; production exposure should be disabled or restricted if these pages are not intended to be public.

# 2. Architecture Map

Guest/Admin browser → static HTML/CSS/JavaScript → FastAPI/Uvicorn app → SQLite stores, property-scoped service layer, provider adapter service, optional ANTlabs / Google Places / SMTP / webhook integrations.

| Area | Actual implementation |
|---|---|
| Frontend | Plain HTML/CSS/JavaScript in app/static; no frontend framework or build step; Playwright E2E. |
| Backend | Python 3.12+, FastAPI, Starlette, Pydantic and Uvicorn. |
| Database / ORM | On-prem Compose uses SQLite and handwritten SQL stores. Optional PostgreSQL adapter and migration tooling are present in synchronized `main` but are not selected by the on-prem profile. Store classes do not use an ORM. |
| Authentication | Admin username/password, scrypt hashes, opaque random session token stored as a hash server-side, expiry/revocation, login lockout, HttpOnly/SameSite cookie, Secure in production and CSRF header on writes. Guests receive temporary session IDs. |
| RBAC | Server middleware maps admin routes to permissions and assigned properties; diagnostic tools check individual permissions on every invocation. |
| AI | AIProvider protocol and AIModelService support Gemini, OpenAI, Groq, OpenRouter, Claude and local OpenAI-compatible Ollama/LM Studio. No native Microsoft/Azure adapter; Copilot is explicitly unavailable. |
| Knowledge / RAG | Review-first ingestion for PDF, DOCX, XLSX, CSV, TXT, Markdown, JSON, PPTX and images, with property-scoped lexical chunks and source locations. Explicit key:value conflicts are withheld pending human review. Image OCR requires Tesseract; dense embeddings, semantic reranking, arbitrary contradiction detection and guest-visible citations are not implemented. |
| Monitoring | SQLite samples for requests/latency/errors and host metrics when optional psutil exists; DB health and operations diagnostics. No external alerting or measured SLO. |
| Deployment | Non-root Dockerfile; Compose persists /state, sets production flags and healthcheck. TLS, reverse proxy and gateway are operator responsibilities. |
| Backups | SQLite backup/verify/restore code and upload archive support. No scheduled/off-host policy is configured in the repository. |

Major directories: app/ runtime and static UI; tests/ pytest and Playwright; data/ demo and Lunara hotel seed; docs/ architecture, deployment, gateway and provider guidance; audit/ prior audits and this report; scripts/ Docker smoke helper. Generated QA output is ignored by Git.

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
| Restaurant operations | PASS (local tests) | Restaurant CRUD/archive, assignment scoping, manager/staff capabilities, approval, hours, menus and promotions are implemented; live hotel workflow has not been run. |
| Human conversation takeover | PASS (local tests) | Server-controlled escalation, accept/assign/reassign/reply/resolve/return-to-AI and AI pause are implemented; concurrent requests are guarded atomically. |
| Security | PARTIAL | Strong baseline controls; guest network/gateway trust and production operations remain incomplete. |
| Knowledge Base | PASS (local format/workflow tests) | Property-scoped review-first pipeline accepts PDF, DOCX, XLSX, CSV, TXT, Markdown, JSON, PPTX and images; image OCR requires Tesseract. |
| RAG | PARTIAL | Property-scoped lexical chunks include source/location metadata and explicit key/value conflict resolution; dense vector search and guest-visible citations are not implemented. |
| AI Providers | PARTIAL | Multiple adapters and local mode; no Microsoft/Azure implementation or live outage certification. |
| Network Restriction | PARTIAL | Server-side CIDR checks; authoritative gateway-session proof is optional. |
| Monitoring | PARTIAL | Real app/DB metrics; host metrics may be unavailable and external alerting is absent. |
| Reporting | PARTIAL | XLSX/PDF generators and endpoints exist; production-scale values were not reconciled. |
| Performance | PARTIAL | Local mocked-AI runs passed at 10/25/50 users. At 100, session-start requests were throttled by the configured per-source-IP limit; production capacity remains unverified. |
| Deployment | PARTIAL | Docker config exists; build/runtime could not run because Docker daemon was unavailable. |
| Backup/Recovery | PARTIAL | Backup/restore tests pass after fixing SQLite close behavior; off-host retention/drill is absent. |
| Production Readiness | FAIL | Gateway trust, RAG, deployment proof, capacity and operational ownership remain open. |

# 4. Critical Issues

| ID | Severity | Component | Problem | Evidence | Risk | Recommended Fix |
|---|---|---|---|---|---|---|
| C-01 | P1 | Guest network / ANTlabs | Signed assertion mode now checks a five-minute timestamp window, HMAC over timestamp/nonce/body, source CIDRs, property equality and persistent one-time nonce consumption. Session IDs remain bearer values and are not bound to a verified gateway device/session; a signed assertion is not proof of native ANTlabs network admission. | `GatewayGuard.validate`, `gateway_assertion_nonces`, guest request validation; regression covers replay and property mismatch. Real SG5 validation remains open. | Without required production enforcement and a certified gateway contract, network admission cannot be inferred from Concierge's assertion check. | Validate the contract against target SG5, require gateway policy in deployment, bind a session to verified gateway identity where supported, and enforce canonical host/proxy configuration. |
| C-02 | P2 | Knowledge / AI | Managed sources are parsed into property-scoped, source- and location-aware lexical chunks. Explicit `key: value` conflicts are detected and withheld from guest retrieval until a human resolves them. Search is not semantic/vector based; conflict detection does not cover paraphrases or arbitrary contradictions, and guest responses do not render citations. | `app/knowledge_management.py`, its `km_sources`/`km_items`/`km_chunks`/`km_conflicts` stores and retrieval path; ingestion, versioning and conflict tests. | Keyword retrieval can miss paraphrases; unsupported conflicts can remain unnoticed; guests cannot inspect source citations. | Measure recall against hotel questions; add semantic retrieval only if needed, broaden conflict review, and evaluate guest citation UX and indirect injection with live providers. |
| C-03 | P1 | Reliability / capacity | Production capacity is unverified. A local SQLite/mock-AI smoke passed at 10, 25 and 50 guests; a 100-user run hit the 240 session starts/source IP/5-minute limiter (96 HTTP 429s), so it does not establish 100-user capacity. | Locust results in §13; `ObservabilityStore.record_request` and `SQLiteRateLimiter.allow`; no DB-lock errors in the measured runs. | Results from one Mac, one process and one injector do not predict a hotel appliance or larger multi-IP deployment. | Repeat with distributed injectors and enough source IPs; record sustained CPU/RAM/DB metrics, p50/p95/p99 and errors on target hardware before setting a supported capacity. |
| C-04 | P1 | Production integration | Supported modes are centrally constrained to `mock` and `browser_handoff`; production browser handoff requires an auth URL. Neither mode has been certified against a real gateway. | `app/config.py`, `app/antlabs.py`, `docs/ANTLABS_INTEGRATION.md`. | Production handoff may fail or be misconfigured, and Concierge must not be treated as the system granting network access. | Complete a lab integration against the target SG5 version and document recovery behavior. |
| C-05 | P2 | Tenant routing | Guest property selection uses request Host without itself proving the edge proxy accepted that hostname canonically. | PropertyGuard.resolve in app/guardrails.py; _guest_property in app/main.py. | A forged Host reaching the app can select another property’s guest-facing configuration if network controls also admit the request. | Enforce canonical hostnames at proxy and app; map property from trusted gateway assertion rather than arbitrary request headers. |
| C-06 | P2 | Account recovery | Request limits are 12/direct-peer/hour plus 3/hashed-account/hour; confirmation limits are 30/direct-peer/hour plus 10/hashed-token/hour. Reset tokens now use a URL fragment and the login page removes it from browser history. | request_admin_password_reset and confirm_admin_password_reset in app/main.py; fragment handling in app/static/admin-login.js; request/confirmation throttle regression tests and browser coverage. | If several users share one reverse-proxy peer address, the IP limits may aggregate their requests; email quotas are not configured. | Verify client identity and rate limits at the deployed proxy; configure email quotas and alerting. |
| C-07 | P1 | Docker proxy routing | Compose renamed the API service to `concierge` while Nginx still routed to `api:8080`; the proxy would return upstream errors. Fixed the upstream to `concierge:8080`. | Reproduced by comparing Compose service names with `deploy/nginx.conf`; `tests/test_deployment_config.py::test_nginx_upstream_targets_a_compose_service` passes. | Guests and administrators could not reach the application through the published proxy. | RESOLVED in this branch; Docker runtime smoke remains blocked by the unavailable daemon. |
| C-08 | P2 | Container filesystem | The non-root app user owned `/app` and could modify application code at runtime. Removed `/app` from the `chown`; `/state` remains writable. | `Dockerfile`; `tests/test_deployment_config.py::test_container_runs_non_root_with_only_state_owned_by_the_app_user` passes. | A compromised process could alter its own code in the writable container layer. | RESOLVED in this branch; runtime permissions still need Docker verification. |
| C-09 | P2 | Load-test tooling / CI | Direct execution of `scripts/configure_loadtest_ai.py` failed to import the repo's `app` package, and Locust still scheduled the optional admin user with zero fixed users. Added repo-root import setup and a zero weight when admin credentials are absent. | Reproduced with the same direct script command used in CI; `tests/test_loadtest_tooling.py` verifies direct invocation and user scheduling. | The CI mocked-load job could fail before load, or report an invalid login as a load failure. | RESOLVED in this branch; rerun CI after pushing this branch. |
| C-10 | P2 | API documentation exposure | FastAPI's default `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, and `/redoc` routes are mounted without application authentication; Nginx forwards all paths to the app. | `app/main.py` constructs `FastAPI` without `docs_url`, `redoc_url`, or `openapi_url` overrides; `deploy/nginx.conf` proxies `location /` without path restrictions. | Publicly reachable API schemas and interactive docs disclose route shapes and make the API explorer available wherever the deployment is reachable. | Disable docs/OpenAPI in production or restrict these paths at the trusted proxy; retain local development docs if needed. |

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
| F-08 | Compose proxy | Nginx must resolve the API container declared in Compose. | Nginx targeted the removed `api` service after Compose renamed it `concierge`; upstream now targets `concierge:8080`. | `test_nginx_upstream_targets_a_compose_service` passes. | P1 — fixed |
| F-09 | Container filesystem | Non-root service should write persistent state without owning its source tree. | Dockerfile now grants the app user write access to `/state` only. | `test_container_runs_non_root_with_only_state_owned_by_the_app_user` passes; Docker runtime check is pending. | P2 — fixed |
| F-10 | Load-test utility | CI must be able to invoke the AI-routing utility directly and omit an admin actor when no credentials are configured. | Added repository-root import handling; Locust sets the optional admin class weight to zero without credentials. | Direct CLI and class-scheduling regression tests pass. | P2 — fixed |

# 6. Security Findings

| Finding / attack scenario | Affected component | Severity | Recommended remediation |
|---|---|---|---|
| External user guesses URL or forges X-Forwarded-For to appear hotel-local. | Guest network guard | P1 | Server-side CIDR and spoofed-header denial tests exist. Shield origin, trust exact proxy ranges, and add signed gateway assertion in C-01. |
| Replay a signed session-start request within timestamp window. | GatewayGuard.validate | Fixed in code and local regression test | Persistent SHA-256 nonce hashes are consumed atomically with an expiry index; timestamp, source CIDR and property checks are enforced. This does not certify that the assertion originated from an actual ANTlabs admission event. |
| Forge Host naming another property. | PropertyGuard / reverse proxy | P2 | Canonical host allowlist at edge and app; derive property from trusted gateway assertion. |
| Custom role with properties.view but not requests.view queries hospitality overview. | Admin hospitality endpoint | P2 | Sensitive records are now filtered and regression-tested. Review all mixed-sensitivity endpoints. |
| Flood password reset for a known account or brute-force confirmation. | Public password-reset endpoints | P2 | Generic request response; request and confirmation limits use direct-peer IP plus hashed account/token keys and are regression-tested. Reset token is in a fragment cleared from history. Validate shared-proxy behavior and email quotas. |
| Prompt asks for system prompt, .env, key, admin logs, guests or shell. | Guest AI | P1 | Direct attacks now blocked before provider and covered by regression. Continue testing indirect KB injection and live model output. |
| Upload unusual content or path-like filename. | Knowledge, maps, intro assets | P2 | Managed knowledge checks supported type signatures, archive bounds, per-file/extracted-text limits and server-generated storage paths; PDF/Office/image extraction is implemented. Hostile malformed files, OCR exhaustion, and all map/intro asset formats still need adversarial testing. |
| Unauthenticated admin call or CSRF. | Admin APIs | Reduced by controls | Server-side session, route permission, property ownership and CSRF exist. The 199-method/path route matrix is published; not every endpoint had negative access tests. |
| Public API schema/docs access. | FastAPI default documentation routes | P2 | `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, and `/redoc` are public in app defaults and pass through the Nginx catch-all. Restrict or disable them for production if not intentionally public. |
| SSRF via provider endpoint, webhook or place URL. | Outbound HTTP | Reduced by controls | Outbound broker/InternetGuard restrict protocols, ports and private addresses; existing tests pass. Revalidate DNS at connection and define redirect policy. |
| Steal/replay guest session ID. | Guest session | P2 | Admin token is stored hashed; guest ID is bearer value in sessionStorage and network-gated, not cryptographically bound to device/gateway. Bind session when integration permits and avoid logging IDs. |

Secret scan: .env is not tracked and values were not copied into this report. The local file has nonempty database and credential-encryption settings; provider API-key fields were empty in the scan. Source/tests include demo credentials (admin / ChangeMe123!) in test fixtures and setup docs; production config rejects the default password. Verify deployment secret provisioning.

# 7. AI / RAG Findings

- Grounding: Hotel fast paths read configured facts. Managed knowledge is property-scoped and contributes lexical chunks with source and document-location metadata. Admin AI can return citations; guest answers do not display explicit citations. Other answers may use property data and optional external place results.
- Hallucination controls: Prompt tells model not to invent hours, fees, availability or completed actions. This is instruction, not a factual output verifier. Live-model accuracy was not assessed.
- Retrieval: Sources are parsed into bounded fact items and property-scoped lexical chunks with source, page/paragraph/sheet/row/slide/line location and effective/expiry metadata. Explicit `key: value` conflicts are detected, withheld from guest retrieval while open, and resolved through an audited workflow. Search is term-frequency/keyword based; no dense embeddings or semantic reranker exists, and arbitrary contradictions are not guaranteed to be found.
- File types: PDF, DOCX, XLSX, CSV, TXT, Markdown, JSON, PPTX, PNG, JPEG and WEBP are supported by the managed review-first pipeline. Image OCR requires the Tesseract executable; scanned PDFs currently fail clearly rather than using OCR. Legacy document rows remain for admin review but are excluded from Guest AI retrieval.
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

# Restaurant Operations and Conversation Takeover

Restaurant operations are implemented behind permission checks and property/restaurant assignment validation:

| Workflow | Current behavior | Verification |
|---|---|---|
| Restaurant management | Admin can create, edit, disable and archive restaurants. IDs are server-generated. Historical records are retained by archive; there is no destructive restaurant-delete action. Restaurant details include guest-facing and internal notes, hours, meal periods, reservations, contact/location, facility, cuisine, capacity and images. | Restaurant workflow tests and admin Playwright coverage. |
| User assignment | `user_restaurants` maps users to restaurants. Admin assignment updates validate the actor's scope and target restaurant's property; manager/staff APIs filter all restaurant resources by assignment. | RBAC and restaurant workflow tests. |
| Manager and staff | Manager can edit restaurant details/hours, menu items and promotions, then approve/publish. Staff can view guest-approved content and handle assigned conversations; staff cannot approve or publish content or change protected settings. | Permission and manager/staff API tests. |
| Content workflow | Menu and promotion edits invalidate previous approval. Content is exposed to guests only when active and published. Restaurant internal notes are omitted from guest content. | API and UI tests. |
| Conversation lifecycle | `ai_active`, `waiting_for_staff`, `assigned`, `human_active`, `resolved`, and `returned_to_ai` are backend states. Guests can explicitly request restaurant staff. Managers/staff can accept, assign/reassign, reply, resolve, and return to AI. | Atomic state-transition and AI-pause tests; desktop/mobile guest and admin E2E suites. |
| Concurrency and audit | Conditional SQL transitions ensure only one staff accept succeeds. State changes and staff replies record actor/action metadata without duplicating message bodies into generic audit events. | Atomic transition and audit tests. |

SQLite integrity covers restaurant-to-menu, menu-to-item, restaurant-to-promotion, and assignment-to-user/restaurant relationships with composite property/resource keys. Foreign keys are enabled on the corresponding store connections. Conversation queues and messages are property-scoped by their store operations; they do not yet have a relational foreign key to `restaurants`, so that integrity remains application-enforced.

### Database and PostgreSQL boundary

On-prem Compose uses SQLite at `/state/concierge.db`, persisted through `concierge-state`; it starts no database or Redis container. `DATABASE_URL` is forced empty in this profile, and the rate limiter uses the shared SQLite table. No SQLite-to-PostgreSQL migration runs for this on-prem deployment. Optional PostgreSQL adapter, Alembic schema, and migration tooling were already present in the synchronized `main` commits; that path is outside this SQLite deployment and still needs its own operational validation. No per-restaurant database is used. New operational tables are `user_restaurants`, `restaurant_audit_events`, `gateway_assertion_nonces`, and `conversation_audit_events`. Existing `restaurants`, `menus`, `menu_items`, `restaurant_promotions`, `conversation_state`, and `conversation_messages` hold the new scoped data and workflow state. Composite keys/indexes support property-plus-resource lookups and queue, expiry, assignment, and audit queries. Existing stores apply additive columns/indexes during initialization; this is not a versioned cross-store SQLite migration framework.

PostgreSQL remains a possible scaling path for heavier concurrency. The local follow-up keeps the supported on-prem profile on SQLite; do not enable or migrate to PostgreSQL without a separate deployment decision and completed migration, backup/restore, concurrency, and operational validation.

# 10. RBAC Matrix

Built-in roles and their effective scope:

| Capability | Super Admin | Property Administrator | Property Manager | Restaurant Manager | Restaurant Staff | Viewer / Auditor |
|---|---|---|---|---|---|---|
| Global settings / all properties | All | No | No | No | No | No |
| Property configuration | All | Assigned property | Assigned property | View assigned property | View assigned property | View where granted |
| Users and roles | All | Assigned-property administration | No | No | No | Read only where granted |
| Hotel knowledge/content | All | Manage assigned property | Manage assigned property | No | No | View where granted |
| Restaurant records | All | Assigned property | All restaurants in assigned property | Assigned restaurants | Assigned restaurants | View where granted |
| Menus / hours / promotions | All | Manage and approve | Manage and approve | Manage and approve assigned restaurants | View only | View where granted |
| Guest conversations | All | Assigned property | Assigned property | Accept, assign, reassign, reply, resolve and return for assigned restaurants | Accept, reply, resolve and return for assigned restaurants | View where granted |
| Restaurant analytics | All | Assigned property | Not explicitly granted | Assigned restaurants | No | Not explicitly granted |
| Provider / system configuration | All | AI and integrations within assigned property; no global system configuration | View provider state; no provider configuration | No | No | View only where granted |
| Security / audit | All | Assigned property | No | No | No | Read only where granted |

Backend RBAC is enforced; UI hiding is not the only check. Permission delegation is bounded by the actor's effective permissions during role and user operations, including assignment, and is covered for forged privileged slugs. Assistant access remains individually permission checked. The whole API-by-role matrix still needs production-like review.

# 11. API Inventory

The [API inventory](31_API_INVENTORY_COMPLETE.md) lists all 191 application method/path combinations, including the hidden `/metrics` route. The companion [route-level endpoint matrix](33_API_ENDPOINT_MATRIX.csv) covers all 199 registered method/path combinations, including FastAPI's four framework documentation paths with GET and HEAD methods. It records authentication, permission, property/restaurant scope, CSRF, rate limits, request models/parameters, response types, direct handler-call hints, and audit-event notes. Generic handler-defined response shapes and indirect helper side effects remain identified for source review; the inventory does not claim every route received a separate access-control test.

# 12. UI Control Inventory

Page/control results are in [UI control inventory](32_UI_CONTROL_INVENTORY.md). Main guest/admin browser flows were run in desktop Chromium and mobile Chrome. Controls still need manual review are marked partial; roadmap features are clearly identified as unavailable.

# 13. Performance Findings

Deterministic mock-AI load was run against one development Uvicorn process and an isolated SQLite database. The results are a local smoke only; they do not establish hotel-appliance or production capacity.

| Virtual guests | Duration | Requests | Failures | Throughput | Median | p95 | p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 20s | 329 | 0 | 17.5 req/s | 10 ms | 58 ms | 350 ms |
| 25 | 20s | 866 | 0 | 43.7 req/s | 7 ms | 59 ms | 110 ms |
| 50 | 20s | 1,739 | 0 | 87.7 req/s | 8 ms | 72 ms | 120 ms |
| 100 | 20s | 3,091 | 96 | 154.9 req/s | 13 ms | 120 ms | 220 ms |

The 100-user failures were HTTP 429 responses from the configured 240 session-start requests per source IP per five minutes, after several progressive stages from the same injector. No database-lock errors were reported. The 100-user sample is therefore rate-limit-bound, not a capacity pass. A one-shot `top` sample after this stage showed 87 MB RSS and approximately 0.1% instantaneous app CPU; this is not a peak or sustained resource measurement. No paid-provider traffic was sent. Do not claim support for 100 concurrent guests from these results.

Likely code bottlenecks, not measured conclusions:

- SQLite connection and synchronous writes for request telemetry, session and chat state.
- SQLite limiter uses BEGIN IMMEDIATE, a serialization point at high rates.
- AI request blocks per conversation to provider timeout; no queue/cancellation/streaming.
- Places lookup is external I/O inside chat path.
- Compose runs one service with a local persistent volume; horizontal replica support is not defined.

# 14. Production Blockers

1. Certify the assertion contract and browser handoff against the target ANTlabs SG5 and verify any session-binding fields it supports. Replay protection, timestamp/source validation and assertion-property matching are implemented locally.
2. Configure the production reverse proxy, TLS, canonical host allowlist, trusted proxy ranges and required gateway policy; verify client identity through the actual hotel network.
3. Measure retrieval recall on hotel questions. Property-scoped chunks, source metadata and explicit conflict review exist; dense vector search and guest-visible citations remain open product choices.
4. Repeat the mocked-AI load test with multiple injector IPs, capture sustained CPU/RAM/database metrics, and establish a target-hardware capacity envelope. The single-injector run passed at 10/25/50 and was rate-limited at 100.
5. Run Docker build/runtime and volume persistence smoke; the local Docker daemon was unavailable. CI contains these checks but they were not executed here.
6. Provision strong secrets, gateway ACLs, off-host backup/restore and alert ownership.
7. Validate real hotel Wi-Fi routing, run live AI-provider checks, and perform route-by-route authorization/tenant-isolation review in a production-like deployment. Complete multi-user concurrency/load checks and staff/operator training and configuration.
8. Disable or restrict public FastAPI docs/OpenAPI paths in production unless intentionally exposed.

# 15. Recommended Fix Order

## Phase 1 — Security / Data Protection
- Exercise signed gateway assertions in SG5 lab, require the correct production policy, and validate canonical hosts at proxy and app.
- Verify property selection against forged Host and all property-scoped endpoints in production-like deployment.
- Expand the API × role matrix beyond the local high-risk RBAC regression cases, including admin AI tools.
- Validate password-recovery rate limits through the production proxy and configure email quotas.
- Validate file signatures and quarantine active SVG/HTML.

## Phase 2 — Broken Core Functions
- Complete real ANTlabs handoff/session binding; mode validation and local assertion replay/property protections are implemented.
- Preserve per-property provider/local-only invariant across every exception/fallback (the known global fallback bypass was removed and tested).
- Keep verified recommendations/hotel facts useful on provider outage (implemented and browser-tested).

## Phase 3 — Guest AI / Personalization
- Measure lexical retrieval recall and indirect injection; consider semantic search if recall needs it. Chunking, source/version metadata, property scoping and explicit-key conflict resolution are implemented; guest-visible citations remain open.
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
| BUG | Fixed and covered locally: provider routing escape, Windows SQLite snapshot lock, outage recommendation loss, async selector reset, normalized facility lookup, mixed-sensitivity response, direct injection patterns, password-recovery request/confirmation limits and token URL exposure, unbounded permission delegation, manual indefinite lock handling, ANTlabs nonce replay, and restaurant/conversation scope. |
| INCOMPLETE FEATURE | Real ANTlabs proof/handoff certification; network-to-session binding; admin alerts; measured retrieval recall and optional semantic search; guest-visible source citations; capacity validation; recovery schedule; live provider health; full API-role verification and operator training. |
| MISSING FEATURE | Dense embeddings/vector DB/reranker; scanned-PDF OCR; native Microsoft/Azure provider; real Copilot integration; streamed chat; scalable queue/replica design; external alerting/SLOs. |
| ARCHITECTURE DEBT | Large route-centric app/main.py; path-string permission dispatch; many SQLite stores; keyword retrieval; provider capability mixed with fallback policy; incomplete centralized migrations; conversation restaurant integrity is enforced in application scope rather than a relational FK. |

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
- RBAC permission-delegation ceilings, role-assignment scope, indefinite manual lock behavior, persistent ANTlabs nonce replay/property checks, restaurant assignment/isolation, composite restaurant foreign keys, approval and conversation takeover/AI-pause/concurrency coverage in `tests/test_admin_auth.py`, `tests/test_guardrails.py`, `tests/test_security_remediation.py`, and `tests/test_restaurant_workflows.py`.
- In this follow-up: explicit gateway assertion negative cases, temporary lock expiry, disabled-account rejection, a deterministic public-DNS test fixture, production SQLite configuration checks, Playwright coverage for restaurant assignment checkbox mapping and overlapping-request races, Compose/Nginx and container permission regressions, and load-test CLI/optional-user regressions.

Final tests: **516 Python passed, 0 failed, 8 skipped**. The eight skips are PostgreSQL/Redis integrations requiring external services. The full Playwright run is **170 passed, 4 failed, 14 skipped** on macOS; all functional flows passed and the four failures are absent Darwin visual baselines (checked-in baselines are Win32). `compileall`, Bandit, JavaScript syntax, Compose config parsing, `git diff --check`, `npm audit` (0 vulnerabilities), `pip-audit -r requirements.txt` (no known vulnerabilities), and SQLite integrity/foreign-key checks passed. CI was not run locally.

Recommended:
- Gateway expiry and real SG5 origin/session-binding verification; nonce replay and wrong-property cases have local regression coverage.
- Every endpoint × role permission matrix, tenant A/B IDOR and reset abuse.
- Malformed MIME/content, huge/Unicode/path-like names, SVG active content and delete propagation.
- Conflict/staleness/citation and indirect injection against each provider.
- Docker backup restore with credentials/uploads and app restart.
- Multi-IP mocked-AI load beyond 50 concurrent guests; DB lock, timeout and provider-failure testing at higher load.
- Safari/Firefox, keyboard/screen reader, and browser network-loss testing.

# 18. Final Production Readiness Checklist

- [PASS] Python suite: 516 passed, 0 failed, 8 skipped (PostgreSQL/Redis integration services unavailable).
- [PARTIAL] Full desktop/mobile browser suite: 170 passed, 4 failed, 14 skipped. The four failures are missing Darwin visual snapshots; checked-in visual baselines are Win32. Functional admin, guest, security, and assignment flows passed.
- [PASS] `npm audit --audit-level=high`: zero vulnerabilities.
- [PASS] `pip-audit -r requirements.txt`: no known vulnerabilities.
- [PASS] Python compileall, Playwright JavaScript parsing, YAML parsing, Compose config interpolation, and `git diff --check`.
- [PASS] Admin scrypt, sessions, CSRF, expiry/revocation tests.
- [PASS] Direct injection list blocked before provider in regression tests.
- [PASS] External guest IP and spoofed forwarding-header denial tests.
- [PASS] Provider credentials encrypted and omitted from settings response.
- [PASS] XLSX/PDF endpoints and report generator tests.
- [PASS] Backup/verify/restore tests after explicit SQLite close.
- [PARTIAL] Password recovery: request and confirmation limits plus fragment handling are tested; verify proxy client identity and email quotas in deployment.
- [PARTIAL] Admin RBAC: permission ceilings, restaurant manager/staff scope, and sensitive response filtering have targeted coverage; all routes/roles need full matrix review.
- [PARTIAL] Tenant isolation: restaurant/property API scoping and composite menu/promotion/assignment constraints are tested; canonical Host deployment and conversation relational FK remain open.
- [PARTIAL] Guest network: CIDR, signed assertion, nonce replay and property checks are local-tested; assertion-to-real-ANTlabs identity/session binding is not certified.
- [PARTIAL] Upload security: type/size checks exist; all hostile formats/content signatures not tested.
- [PARTIAL] Production auth: strong settings enforced; deployment secret/TLS provisioning external.
- [PARTIAL] Monitoring: DB/request metrics exist; host metrics may be unavailable, external alerts absent.
- [PARTIAL] Reporting: formats exist; production-scale reconciliation incomplete.
- [PARTIAL] Recovery: backup code/tests exist; off-host policy and restore drill absent.
- [PARTIAL] Multi-provider: several cloud/local adapters exist; Microsoft/Azure and live credentials absent.
- [PARTIAL] Knowledge retrieval: source-located lexical chunks and explicit conflict workflow exist; dense semantic retrieval and guest-visible citations are not implemented.
- [FAIL] Live gateway guarantee: local HMAC assertion checks are not proof of an admitted gateway session.
- [PARTIAL] Mocked-AI load: 10/25/50 guest stages passed with zero failures. 100 users encountered 96 expected HTTP 429s from the configured single-source session-start limit; no production capacity claim is supported. CPU peak/sustained resource and multi-IP testing remain open.
- [BLOCKED] Docker build/runtime and persistence smoke: local Docker daemon is not running; workflow is configured in CI.
- [NOT IMPLEMENTED] Native Microsoft/Azure, scanned-PDF OCR, dense vector retrieval and streaming.
- [NOT TESTED] CI run, real ANTlabs SG5, real hotel Wi-Fi, live AI providers, malicious KB injection against a live model, Safari/Firefox, disk-full/proxy failure, production TLS/reverse proxy, multi-IP load/concurrency, and operator training/configuration.
- [PARTIAL] Hotel production readiness remains blocked by the section 14 deployment and live-validation items. The local changes are ready for human re-review; the current remote main tip could not be fetched because GitHub credentials were unavailable.
- [PARTIAL] FastAPI's default OpenAPI and interactive documentation routes are public at the application; production access policy is not yet verified.

## Evidence labels for this revision

| Status | Evidence |
|---|---|
| IMPLEMENTED | RBAC permission ceilings, property/restaurant scoping, restaurant assignment UI/API, content approval, human conversation takeover, AI pause, and SQLite Compose deployment. |
| LOCALLY TESTED | 516 pytest passed; targeted security suite passed; Playwright functional flows passed, including assignment mapping; mocked load passed to 50 users. |
| CI TESTED | Not run from this workspace. CI retains PR-to-main, audit, browser, and Docker jobs. |
| LIVE GATEWAY TESTED | Not tested against ANTlabs SG5. |
| LIVE PROVIDER TESTED | Not tested against production AI credentials/providers. |
| NOT TESTED | Production TLS/reverse proxy, hotel Wi-Fi, multiple injector IP load, operator training/configuration. |
| BLOCKED | Docker image/runtime/persistence smoke by stopped local Docker daemon; macOS-only visual baseline checks by absent Darwin snapshots. The GitHub browser job targets Windows, matching the checked-in Win32 snapshots, but CI was not run. |

# Final Verdict

NOT READY
