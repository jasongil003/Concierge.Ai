# Concierge.AI ECC Audit — Security Findings

**Reviewed checkout:** `fbf9d50635c427f5340098cac48e7bb8eb7ef7a2` plus pre-existing, uncommitted local changes. Review was nondestructive; no external penetration testing was performed.

## Finding register

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| `ECC-SES-001` (historical guest expiry race) | High | Authenticated in-flight request could finish after credential expiry without sliding the stored expiry | **FIXED-VERIFIED** |
| `FILE-DOS-01` (existing register) | Medium | PDF extraction resource guards exist, but high-expansion RSS termination acceptance is not evidenced on every supported OS | **FIXED-UNVERIFIED** |
| `ECC-OPS-001` | Medium | Target appliance, trusted proxy/TLS, clean reboot/update rollback, and off-host restore acceptance are outstanding | **BLOCKED** |
| `ECC-UI-001` | Low | Intelligent guest chat is request/response; SSE streaming and reconnect semantics are absent | **OPEN** |
| `ECC-UI-002` | Low | Global Intelligent UI kill switch is process configuration and takes effect after restart | **OPEN** |

No currently confirmed Critical or High vulnerability was identified. `ECC-SES-001` is a previously reported issue and is included to record independent verification, not as an open defect.

## `ECC-SES-001` — Guest expiry race (historical High)

- **Affected code:** `app/session_store.py:396-479`; `app/main.py:611-711,3524-3620`; regression coverage in `tests/test_security_remediation.py:456-646`.
- **Root cause/history:** Commit `cfb7155ab8e347481af78b33f73f02e0d9ae9ed2` added per-session guest credentials and response-time sliding renewal. The old renewal checked that the expiry was still in the future when the response finished. Authentication could succeed just before expiry, the endpoint could take long enough for expiry to pass, and the successful request would then fail to persist the slide. The CI symptom was a 200 response with `guest_token_expires_at` still near the current time.
- **Fix/history:** Commit `419065052a01467db7f738079d3f2bb6b4f2368e3` carries the authentication timestamp through request state. Renewal accepts only a credential whose expiry exceeded that timestamp, rejects future or over-TTL validation timestamps, rechecks both hashes and revocation in the write transaction, and uses a conditional update. The middleware sets refreshed cookies only when that update succeeds.
- **Verification:** Deterministic test makes the one-second credential expire while `/api/guest/personalization` runs, then checks the persisted expiry is at least approximately 1,700 seconds ahead and the cookie carries `Max-Age=1800`. It also repeats activity. Separate tests reject already-expired credentials, preserve revoked state, and revoke between authentication and renewal. The focused test and full backend suite passed.
- **Impact/exploitability:** The defect shortened active sessions and caused the reported renewal failure; evidence does not show that it let an expired credential start a new request. It was a session-availability/security-control correctness issue, not an observed authorization bypass.
- **Security conclusion:** **FIXED-VERIFIED** for the local tested implementation. New requests with an expired credential fail authentication. A long-running request cannot renew after its authentication timestamp ages beyond the configured TTL. Revocation/hash changes prevent renewal; a successful renewal updates the database before returning cookie lifetime. Cookie flags remain HttpOnly, SameSite Strict, path `/`, and Secure in secure environments. There is no configured separate absolute lifetime cap; the existing inactivity timeout is the policy TTL.
- **Residual coverage:** No controlled concurrent renewal-versus-revocation schedule test was found. The transaction and conditional predicates make the update fail after revocation/hash change, but that interleaving is not independently stress-verified here. Local runtime was Python 3.11.16, not CI’s Python 3.12.

## `FILE-DOS-01` — PDF extraction resource limits

- **Affected code:** `app/knowledge_management.py:122-205`; `app/pdf_extraction_worker.py`; configuration/tests in the same subsystem.
- **Evidence:** Parent process supervises the worker with RSS and wall-time limits and terminates an over-limit process. The worker applies CPU/address-space controls where supported and bounds page count, extracted characters, and sections. Local tests passed. The current acceptance guide explicitly calls for a memory-expansion PDF RSS/kill/reap check on macOS (and the corresponding target OS).
- **Unverified condition:** No high-expansion fixture was run against every supported target OS in this audit. Platform-specific resource-limit behavior is therefore not established by unit tests alone.
- **Impact:** A parser expansion or worker-control regression could consume resources and affect availability; no exploit was reproduced.
- **Recommendation/status:** Keep the worker isolation and configured ceilings; run the approved synthetic expansion fixture on each supported OS and record measured RSS, termination, recovery, and service health. **FIXED-UNVERIFIED**, not an asserted live exploit.

## `ECC-OPS-001` — Environment-dependent production controls

- **Evidence:** `docs/PRODUCTION_ACCEPTANCE.md` and `docs/CONTROLLED_POC_ACCEPTANCE.md` mark target-machine, TLS/proxy, guest-network/gateway, clean boot/update rollback, PostgreSQL/Redis, and off-host restore work as required/not yet accepted. 17 backend integration tests were skipped locally, including PostgreSQL/Redis and platform-only checks. Live GitHub CI could not be queried.
- **Impact:** Deployment assumptions and operational recovery are not independently proven for a target installation.
- **Recommendation/status:** Execute the existing acceptance checklists on disposable target infrastructure using synthetic data and capture sanitized evidence. **BLOCKED** on external environment and CI evidence; this is not a code vulnerability.

## `ECC-UI-001` — No streaming protocol

- **Evidence:** `app/main.py:6277-6343` returns the complete response from `/api/guest/intelligent-chat`; no SSE endpoint or event protocol is present.
- **Impact:** Streaming, reconnect, cancellation, and partial-response behavior cannot be delivered by this adapter. This is a scope/readiness gap, not an authorization flaw.
- **Recommendation/status:** If streaming is required, design a bounded event protocol preserving session authentication, property isolation, cancellation, response validation, and rate limits. **OPEN**, Low.

## `ECC-UI-002` — Global emergency rollback requires process restart

- **Evidence:** `app/main.py:523-536` requires both a process-global setting and a property flag; page, asset, and API paths check it. Local tests verify disabled mode falls back to legacy. The global value is loaded from process settings, so changing it requires a restart; a per-property disable takes effect on later requests without a restart.
- **Impact:** During incident response, a global disable depends on restart time and operational access. Existing already-open pages may require reload and can retain stale client state until they make a subsequent request.
- **Recommendation/status:** Document and rehearse restart-based rollback before any pilot; consider an operationally controlled dynamic global flag only if it can fail closed and be audited. **OPEN**, Low.

## Other reviewed security areas

- **Authentication/session:** Opaque, hashed guest credentials, constant-time comparison, per-session cookies, revocation, expiry, logout, property binding, and cookie attributes were inspected and covered by regression tests.
- **RBAC/tenant isolation:** Existing remediation work and current route/policy checks were reviewed; targeted policy/property isolation tests passed as part of the full suite. No current bypass was reproduced. Historical `AUDIT-001`/`AUDIT-002` fixes are not duplicated as new findings.
- **Web risks:** Bandit passed at the CI severity/confidence thresholds. `npm audit --audit-level=high` and `pip-audit -r requirements-dev.txt` reported zero known vulnerabilities. Python compile, JavaScript syntax, shell syntax, and workflow YAML parsing passed. No local Gitleaks or Trivy binary was available; Docker daemon was unavailable.
- **AI-specific risks:** The new protocol forbids extra schema fields, bounds content, has no model-selected route/action/URL fields, and the browser builds DOM using text nodes. Service actions use the existing proposal and explicit confirmation flow. This does not establish resistance to every prompt injection or provider-specific failure mode; external tests and provider credentials were not exercised.
- **Coverage boundary:** No destructive tests, live network penetration, hotel gateway/PMS testing, or production load testing were performed.

## Standards reference

This review considered relevant principles in [OWASP ASVS](https://github.com/OWASP/ASVS), the [OWASP API Security Top 10 (2023)](https://api-security.owasp.org/editions/2023/en/0x03-introduction/), and the [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/). This is an evidence-based code review, not a formal standards certification.
