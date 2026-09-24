# 03 — Threat Model

## Assets
- Guest PII + stay memory, chat histories, location/occupancy analytics (PII-lite), uploads; admin users/roles; AI provider API keys and spend records; webhook secrets; gateway (ANTlabs) credentials; the single SQLite DB; the admin console.

## Trust zones
- Z1 Internet / hotel guest Wi-Fi (guest app). Untrusted guests, from allowed CIDRs.
- Z2 Hotel backend LAN (admin console + API + Ollama + Gateway). Operators.
- Z3 Cloud providers (Gemini/OpenAI/Ollama/Places). Data exits property.
- Z4 Platform host (Docker container, volume /state).

## Actors
- Guest, hallway/bot, admin (per role), super-admin, worker (department), viewer/auditor, AI provider, ANTlabs gateway, webhook endpoint, maintenance person.

## Primary threats (STRIDE-ish)
1. Cross-tenant data access by guest or admin (enumeration, property hop). — SEC-004 (guest property selection), SEC-012 (guest session bearer), reviewed admin RBAC.
2. Stored XSS in admin console via guest-supplied text. — SEC-001 (FIXED).
3. Privilege escalation within admin roles (role confusion, super-admin-only ops). — reviewed; see 04.
4. SSRF from the platform (webhooks), DNS rebinding window. — SEC-006.
5. Prompt injection / AI exfiltration of system instructions or other guests. — SEC-008 (classifier bypass fixed; context-isolation hardening OPEN).
6. Default/weak admin credentials at boot. — SEC-002 (guard exists only when APP_ENVIRONMENT=production|staging; docker default is development).
7. Provider outage → availability (legacy fallback chain exists but provider lists/spend not enforced). — SEC-009 (documented; partial).
8. Secret handling: Fernet key default value; SMTP/webhook secrets; audit redaction. — reviewed, SEC-011.
9. Log injection / control chars in AI context and diagnostics. — SEC-010 (LOW).
10. DoS: guest rate limits are in-memory per process; no IP-block burst on chat besides session limits. — OPS-020.
11. Data integrity: SQLite single-file, WAL not enforced; no backup automation. — DEP-003.

## Residual accepted risks
- AI provider sees full guest conversation + property context (privacy trade-off; documented in privacy blurb).
- Local network = trust boundary; guests on the main LAN of the switch can self-issue sessions only if `guest_network_only` misconfigured — by default guest_network_only=True with 127.0.0.0/8 (demo); production must set hotel CIDR.
- Playwright visual suite not part of CI.

## Triage guide
Severity: Critical (remote, no auth, no interaction) > High (unauth or admin-session impact) > Medium > Low. Evidence-before-fix required. Findings IDs: SEC/OPS/DEP/QA-xxx.