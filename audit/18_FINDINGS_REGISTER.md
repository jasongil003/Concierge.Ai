# 18 — Findings Register (authoritative)

Status legend: FIXED=code changed & verified | OPEN=reproduced, fix recommended | ACCEPTED=rationale + owner noted | OBS=informational.

## Security
| ID | Sev | Component | Title | Status | Evidence / Doc |
|---|---|---|---|---|---|
| SEC-001 | CRITICAL | admin.js ~2417 | Stored XSS: guest service-request fields via innerHTML in admin console | **FIXED** | proof + e2e (07/19/20) |
| SEC-002 | MED | auth bootstrap | Default admin/bootstrap password unless APP_ENVIRONMENT=production | ACCEPTED (operator action) | live proof (04/13) |
| SEC-003 | MED | guardrails | Prompt-injection classifier bypass "ignore all previous system instructions" | **FIXED** | unit+proof (08/20) |
| SEC-004 | MED | property guard | Guest property selectable via body when Host unmapped (multi-brand risk) | OPEN | proof (05/15) |
| SEC-005 | MED | webhooks | DNS-rebinding TOCTOU between validate_url and httpx.post | OPEN (LAN-only low until internet) | code walk (06) |
| SEC-006 | LOW | reset | Reset token in email query string; recommend +rate limit +origin | OPEN | code (04) |
| SEC-007 | LOW | sanitizers | AIInputSanitizer does not strip control chars/HTML (only secret redaction+truncate) | OPEN | proof FAIL (08) |
| SEC-008 | MED | ai_providers | routing_mode/fallback_chain/limits stored but never enforced at runtime | OPEN | code walk (09) |
| SEC-009 | MED | Dockerfile | Ran as root, no healthcheck, unpinned base | **FIXED** (no rebuild this env) | (12) |
| SEC-010 | LOW | cookies | Admin cookie `secure` off unless production/ADMIN_COOKIE_SECURE | OPEN | runtime (04/13) |
| SEC-011 | LOW | diagnostics | check_dns/check_ssl accept admin-supplied domains (admin-only path) | OPEN | 14 |
| SEC-012 | LOW | guest POSTs | No Origin validation on guest mutations | OPEN | 05/15 |

## Operations
| ID | Sev | Component | Title | Status |
|---|---|---|---|---|
| OPS-020 | MED | rate limits | In-memory per-process counters; per-IP gate missing on shared deploy | OPEN |
| OPS-021 | MED | guest fast-path | mobile-chrome fast-path answers return generic dining text (pre-existing) | OPEN (verify) |
| DEP-002 | LOW | runtime | Single uvicorn worker default; scale >200qps needs workers+shared limits | OPEN |
| DEP-003 | LOW | DB | SQLite WAL + automated backup/restore not configured | OPEN |
| DEP-004 | HIGH(op) | compose | Must set APP_ENVIRONMENT=production before internet deploy | ACCEPTED (action) |
| DEP-005/006/007/008 | LOW/MED | compose/build | Bind interface, secret rotation doc, digest pin, .dockerignore | OPEN |
| DEP-009 | LOW | health | Extend /health with DB reachability | OPEN |

## Accepted-risk summaries
- SEC-002 without guard in dev docker default is dangerous only if operator forgets env; production guard code verified present.
- SEC-012 / SEC-011 are admin/gated or no-impact by session scoping; fix opportunistically.
- OPS-021 needs product decision; priority below SEC-003 fix.

## Post-audit CI gate
Block merge on: pytest not green, xss-guard + admin-auth e2e red, `npm audit` high+, and any new innerHTML-with-untrusted sink (lint rule pending).