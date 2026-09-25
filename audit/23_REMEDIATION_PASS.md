# 23 — Production remediation pass

Date: 2026-09-23. Branch: `feature/onprem-mvp`.

Baseline before this pass: 96 backend tests passed; npm audit reported 0 vulnerabilities. The initial browser run reproduced guest fast-path, visual snapshot, and mobile admin-navigation failures. Docker 29.7.2 was installed, but the Docker Desktop Linux daemon was not running. The worktree already contained uncommitted audit work and it was preserved.

| ID | Previous status | Current status | Files changed | Tests added/run | Runtime verification | Residual risk |
|---|---|---|---|---|---|---|
| SEC-001 | FIXED | FIXED AND VERIFIED | Existing output encoding retained | `xss-guard.spec.js`, backend XSS contract | Desktop/mobile targeted browser pass | Continue sink review when UI changes. |
| SEC-002 | ACCEPTED | FIXED AND VERIFIED | `app/config.py`, compose | production configuration tests | Import-time fail-closed behavior exercised | Operator must supply production secrets. |
| SEC-003 | FIXED | FIXED AND VERIFIED | `app/llm.py`, `app/guardrails.py` | guardrail and prompt-structure tests | Provider path receives structured policy/context | Model-output eval breadth should grow. |
| SEC-004 | OPEN | FIXED AND VERIFIED | `app/config.py`, `app/guardrails.py`, `app/main.py` | five named tenant/host tests | TestClient request paths exercised | Host mappings must be provisioned per property. |
| SEC-005 | OPEN | FIXED AND VERIFIED | `app/outbound_http.py`, webhook paths | private IP, metadata, redirect and DNS-pinning tests | Transport connects to the validated IP | HTTP/2 is intentionally not supported by this broker. |
| SEC-006 | OPEN | OPEN | none | existing auth tests | not changed | Reset links remain bearer tokens in query strings. |
| SEC-007 | OPEN | FIXED AND VERIFIED | `app/guardrails.py` | sanitizer regression | backend path exercised | Sanitization remains one layer, not an authorization control. |
| SEC-008 | OPEN | FIXED AND VERIFIED | `app/ai_providers.py`, `app/llm.py` | routing, fallback, limits, usage tests | adapters exercised with deterministic fakes | Monetary budgets await a provider price table. |
| SEC-009 | FIXED, rebuild pending | FIXED — VERIFICATION PENDING | `.dockerignore`, CI smoke | CI runtime smoke added | local daemon unavailable | CI must produce first green runtime evidence. |
| SEC-010 | OPEN | FIXED AND VERIFIED | `app/config.py`, `app/main.py` | secure-cookie production test | production boot rejects insecure cookie mode | TLS termination remains an operator responsibility. |
| SEC-011 | OPEN | OPEN | none | none | not changed | Admin DNS/SSL diagnostic targets need the same broker policy. |
| SEC-012 | OPEN | FIXED AND VERIFIED | `app/main.py` | cross-origin mutation test | TestClient 403 verified | Non-browser clients without Origin remain supported. |
| OPS-020 | OPEN | FIXED AND VERIFIED | `app/guardrails.py`, `app/main.py` | multi-instance SQLite limiter test | shared database behavior exercised | Redis-compatible backend remains future cloud work. |
| OPS-021 | OPEN | FIXED AND VERIFIED | `app/lunara_seed.py`, guest answer formatting, browser tests | desktop/mobile guest tests | all 157 applicable functional browser scenarios are now passing; 11 project-specific skips | Full visual baselines remain separate from functional QA. |
| DEP-002 | OPEN | OPEN | none | none | single process retained | Horizontal scale needs deployment design. |
| DEP-003 | OPEN | FIXED AND VERIFIED | `app/backup.py` | destructive restore integration test | database, requests, credential and upload restored | Scheduled/off-host retention is operator work. |
| DEP-004 | ACCEPTED | FIXED AND VERIFIED | `docker-compose.yml`, dev override | production config tests | compose now selects production | secrets must be injected. |
| DEP-005/006/007/008 | OPEN | FIXED — VERIFICATION PENDING | `.dockerignore`, CI | Docker CI gate | daemon unavailable locally | Base-image digest and image scanner remain open. |
| DEP-009 | OPEN | FIXED AND VERIFIED | `app/main.py` | backend suite | `/health/live`, `/health/ready`, protected details implemented | External monitoring configuration is not included. |

Commands executed included `pytest -q`, focused pytest security suites, Playwright desktop/mobile runs, `npm audit --audit-level=high`, `pip-audit --local`, `python -m compileall`, and `docker build`. Final results were 126 backend tests passed, 157 applicable functional browser scenarios passed (11 intentional project-specific skips), npm audit reported 0 vulnerabilities, and pip-audit reported no known vulnerabilities. Docker build reached the host but could not connect to the stopped Linux daemon.
