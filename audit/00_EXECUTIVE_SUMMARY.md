# 00 — Executive Summary

Scope: full audit of Concierge.Ai `feature/onprem-mvp` — security (auth, xss, tenant isolation, network/SSRF, AI guardrails, secrets), QA/functional, ops/reliability, deployment, monitoring, data lifecycle. Evidence-based; all claims verified by running code or tests. Baseline and post-fix states captured in audit/02 and audit/20.

## Verdict
Boundary of this audit: on-prem single-property appliance. The product is **solid for its declared boundary** after three fixes, with a short, explicit operator checklist before ANY internet-facing or multi-brand deployment.

## Headline numbers
- pytest: **94 → 96 passed** (2 new regression tests), 0 failures.
- Playwright: xss-guard **1/1**, admin-auth **12/12**, guest 65/72 (7 = pre-existing mobile fast-path issue, unrelated).
- `npm audit --omit=dev`: **0 vulnerabilities**.
- Proof harness: 26/27 PASS; the 1 FAIL is a documented LOW observation (SEC-007 control-char sanitization).

## Critical fixes shipped this session
1. **SEC-001 (CRITICAL)** Stored XSS in the admin console via guest service requests — html-escaped in admin.js; verified with a browser-level regression test that would fail on any reintroduction.
2. **SEC-003 (MEDIUM)** Prompt-injection classifier bypass ("ignore all previous system instructions") — regex hardened; 4-variant unit regression.
3. **SEC-009 (MEDIUM)** Container hardening — non-root user + healthcheck added to Dockerfile.

## Operator must-do before internet exposure (DEP-004 checklist)
- APP_ENVIRONMENT=production (activates bootstrap-password guard + secure cookies)
- rotate CREDENTIAL_ENCRYPTION_SECRET
- bind to LAN port / reverse-proxy
- webhook resolution pinning (SEC-005) + hotel-wifi CIDR (SEC-004 context)
- decide on kiosk Origin policy (SEC-012)

## Open items pipeline (not blockers for LAN appliance)
SEC-008 (spend limits wiring), OPS-021 (mobile fast-path content), DEP-003 (WAL/backup), OPS-020 (shared rate limiting), SEC-004 (multi-brand host binding).

## Portfolio docs
01 System Map · 02 Baseline Conformance · 03 Threat Model · 04 Auth · 05 Cross-Tenant · 06 Network/SSRF · 07 XSS · 08 Prompt Injection · 09 AI Providers · 10 QA Functional · 11 Reliability · 12 Deployment · 13 Hardening Baseline · 14 Monitoring · 15 Multi-Tenancy · 16 Data LifeCycle · 17 Compliance · 18 Findings Register · 19 Fixes Applied · 20 Regression Evidence · 21 QA Walkthrough · 22 Final Re-audit.