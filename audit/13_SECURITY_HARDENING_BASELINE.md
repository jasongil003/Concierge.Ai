# 13 — Security Hardening Baseline (executable checklist)

Rows verified in THIS session; assign status S=set by default, U=needs change.

| # | Control | Default | Status | Where |
|---|---|---|---|---|
| 1 | Admin bootstrap creds guarded by env | CRITICAL/secured only in production|staging | U | main.py guard; compose default = development |
| 2 | Cookies HttpOnly + SameSite=Strict | true | S | capture proved Strict |
| 3 | Cookie secure flag | only prod / ADMIN_COOKIE_SECURE | U for LAN | config.py |
| 4 | CSRF on admin mutations | enforced | S | middleware |
| 5 | Admin session idle timeout | 30min | S | session_store |
| 6 | Lockout | enabled | S | |
| 7 | Secret at rest (provider keys) | Fernet + CREDENTIAL_ENCRYPTION_SECRET | S (default value → U) | ai_providers |
| 8 | Store PII minimised | sessions auto-expire, no raw upload logs | S | |
| 9 | DB write by non-root (container) | was root → now concierge | S | Dockerfile fixed |
| 10 | Health-check for auto-restart | was none → HEALTHCHECK | S | Dockerfile fixed |
| 11 | Webhook SSRF pin (single resolution) | validate-then-post (TOCTOU) | U | see 06 |
| 12 | Prompt-injection classifier regex | strengthened | S | guardrails.py fixed |
| 13 | AI context untrusted-tagging | not implemented | U | see 08 |
| 14 | Guest property selection host-bound | body-selectable when unmapped host | U | see 05 |
| 15 | Rate limiting shared across workers | in-memory per process | U | see 11 |
| 16 | Uploads MIME allow-list | enforced (pdf/images/txt subset) | S | |
| 17 | Upload size cap | 1MB base64 then to filesystem | S | |
| 18 | SQLite WAL + backup | not enforced | U | DEP-003 |
| 19 | Reporting formula injection | inlineStr (fixed) | S | reporting.py |
| 20 | HTML output encoding in admin | guest fields escaped | S | admin.js fixed |
| 21 | Reset-token hardening | 30m single-use hashed | S+check origin/rate | see 04 |
| 22 | Secret log redaction | built-in sanitize + audit redaction | S | |

## Fast-path "must do before internet"
1. compose: APP_ENVIRONMENT=production
2. rotate CREDENTIAL_ENCRYPTION_SECRET (and re-encrypt provider rows per DEP-006)
3. bind to LAN / reverse-proxy
4. pin webhook resolution (06) + enable network CIDR = hotel Wi-Fi
5. add Origin check for guest POSTs if kiosk shared browsers (05)