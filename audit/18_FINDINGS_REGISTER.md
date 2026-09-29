# 18 — Findings Register (authoritative)

Audit recheck: 2026-09-29, checked-out revision `0c4c98e`. Historical audit notes remain in their original files; this register reflects the current source and regression evidence.

Status legend: **FIXED** means current code plus automated regression coverage; **OPEN** means a reproducible weakness remains; **NEEDS VALIDATION** means a bounded risk requires isolated runtime or deployment verification; **CLOSED** means the old report did not reproduce against current code.

## Security

| ID | Sev | Component | Title | Status | Current evidence |
|---|---|---|---|---|---|
| SEC-001 | CRITICAL | Admin UI | Stored XSS in guest service-request fields | **FIXED** | `tests/e2e/xss-guard.spec.js`; hostile values render as inert text. |
| SEC-002 | MED | Bootstrap/config | Default administrator or encryption secrets | **FIXED** | `tests/test_security_remediation.py`; startup rejects missing/known secrets in every environment. |
| SEC-003 | MED | Guest AI | Known direct prompt-injection patterns | **FIXED (known cases)** | `tests/test_guardrails.py`; injected requests are blocked before provider invocation. Regex is not treated as the security boundary; live-model testing remains manual. |
| SEC-004 | MED | Tenant/property guard | Body-selected property accepted for an unmapped Host | **FIXED** | `tests/test_security_remediation.py`; property selection and hostile Host cases fail closed. Production requires canonical hosts; property host records must be provisioned. |
| SEC-005 | MED | Webhook/outbound HTTP | DNS rebinding and unvalidated redirects | **FIXED** | `tests/test_outbound_http.py`; validated IP is used for the connection, non-global addresses are blocked, and cross-origin redirects are refused. |
| SEC-006 | LOW | Password reset | Reset-link origin, token exposure, limits, replay | **FIXED** | `tests/test_security_remediation.py`, `tests/test_operations.py`, `tests/test_admin_auth.py`; configured public origin, fragment token, rate limits, single-use atomic claim. |
| SEC-007 | LOW | AI input | HTML/control characters and credential data passed through sanitizer | **FIXED** | `tests/test_guardrails.py`; sanitization and secret redaction assertions. Sanitization is defense in depth. |
| SEC-008 | MED | AI provider routing | Stored routing mode, fallback chain, or local-only policy ignored | **FIXED** | `tests/test_ai_providers.py` and guest-provider outage tests enforce configured routing. |
| SEC-009 | MED | Container | Application ran as root | **FIXED** | Non-root Dockerfile and deployment configuration tests. |
| SEC-010 | LOW | Admin cookies | Secure cookie flag disabled in secure deployments | **FIXED** | Secure-environment configuration validation and cookie tests in `tests/test_security_remediation.py`. |
| SEC-011 | LOW | Deployment diagnostics | Admin-checkable domain used as an arbitrary outbound destination | **CLOSED** | Current verifier reads the configured deployment origin, is admin-gated, rejects non-global DNS answers, and pins the checked IP; `tests/test_security_remediation.py::test_deployment_verification_rejects_private_dns_answers`. |
| SEC-012 | LOW | Guest mutations | Weak Origin/Host comparison allowed an unconfigured matching attacker Host | **FIXED** | `tests/test_guardrails.py`; rejects unconfigured matching Origin and Referer, cross-origin requests, and cross-site Fetch Metadata; accepts configured property origins. Origin-less native/server requests remain compatible and session routes enforce their own credentials/gateway checks. |
| SEC-013 | MED | Password reset | Concurrent confirmations could consume one reset token twice | **FIXED** | `tests/test_admin_auth.py::test_parallel_password_reset_confirmation_consumes_token_once` and `tests/test_postgres_integration.py::test_postgres_password_reset_token_is_claimed_once_under_concurrency`. Conditional `UPDATE … RETURNING` is atomic on SQLite and PostgreSQL. |
| SEC-014 | MED | Outbound HTTP | Cross-origin public redirects could receive webhook payloads/signatures; special-use public-looking ranges were accepted | **FIXED** | `tests/test_outbound_http.py` and `tests/test_guardrails.py`; same-origin redirects remain supported, cross-origin redirects and non-global destinations (including CGNAT/benchmark/ULA) are denied. |
| SEC-015 | LOW | Outbound HTTP headers | Control characters in configured request headers could corrupt the raw HTTP request | **FIXED** | `tests/test_outbound_http.py`; invalid header names/values are rejected before DNS or connection. |
| SEC-016 | MED | Deployment verifier | Certificate probe allowed RFC1918/ULA DNS answers because `is_private` was exempted | **FIXED** | `tests/test_security_remediation.py::test_deployment_verification_rejects_private_dns_answers` now covers loopback, RFC1918, CGNAT, and IPv6 ULA and proves no connection occurs. |
| FILE-DOS-01 | MED | Knowledge upload | PDF decompression/extraction work is not bounded by a worker resource limit | **NEEDS VALIDATION** | `app/knowledge_management.py` caps upload size and page count, but checks total text only after extraction. A safe high-expansion resource-isolated test and worker limit are still needed. |

## Operational follow-ups (not confirmed application vulnerabilities)

| ID | Sev | Component | Follow-up | Status |
|---|---|---|---|---|
| OPS-020 | MED | Rate limiting | Configure Redis-backed limits for multi-instance production; SQLite mode is local/shared-file oriented. | **DEPLOYMENT VALIDATION**; Redis limiter integration passes. |
| OPS-021 | MED | Guest fast path | Verify generic fast-path dining responses against product expectations. | **OPEN (product/functional)** |
| DEP-002 | LOW | Runtime | Set and measure worker count for the target appliance/deployment. | **OPEN (capacity)** |
| DEP-003 | LOW | Database operations | Configure off-host backups and complete a restore drill. | **OPEN (operations)** |
| DEP-004 | HIGH(op) | Compose | Set production environment and real deployment secrets/policies. | **OPERATOR ACTION** |
| DEP-005/006/007/008 | LOW/MED | Compose/build | Recheck deployment bind, secret rotation, image pinning, and build context at release. | **DEPLOYMENT VALIDATION** |
| DEP-009 | LOW | Health | Confirm readiness/DB health monitoring and alert ownership. | **OPEN (operations)** |

## Gate

**Security Gate: PASS** under the audit’s stated rule: no known Critical or High vulnerability remains from this review, and security regressions pass. This does not mean production readiness or penetration testing is complete. `FILE-DOS-01`, current dependency advisory scans, live gateway/model behavior, and production network/TLS configuration remain validation items. See [VULNERABILITY_AUDIT.md](VULNERABILITY_AUDIT.md) and [SECURITY_TEST_RESULTS.md](SECURITY_TEST_RESULTS.md).
