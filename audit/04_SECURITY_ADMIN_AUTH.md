# 04 — Security: Admin Authentication & Sessions

## Verified behaviour (evidence-based)

| Control | Status | Evidence |
|---|---|---|
| Password hashing | OK — scrypt (hashed_password field), never plaintext | admin_auth.py create_admin/verify |
| Login lockout | OK — per-username failure counter + cooldown, reset on success | lockout util tests |
| Bootstrap admin | WARN — default admin/ChangeMe123! active unless APP_ENVIRONMENT=production/staging | audit_proof (fresh temp DB login ok), main.py security guard |
| Cookie flags | OK — set_cookie: HttpOnly, SameSite=Strict, path=/; secure only in prod/ADMIN_COOKIE_SECURE=True | runtime set-cookie capture |
| CSRF | OK — X-CSRF-Token hmac compared for every non-GET admin route; token rotated on login | middleware verified in proof run |
| RBAC | OK — 30+ named permissions, path→permission map, 401/403 semantics | permission tests |
| Property scope | OK — can_access_property enforced on property-scoped read/write | code walk |
| Reset token | OK-ish — hashed (sha256 w/ salt?), single-use, 30 min TTL, generic failure messages | admin_auth create/consume |
| Reset delivery | WARN — token in email link query string; no rate limit on token consumption; no `Origin` validation on login (cookie-only CSRF is primary) | main.py reset_url line ~862 |
| Admin audit log | OK — who/what/ip/target/outcome logged on key actions | admin_auth audit |
| Session store | OK — random token, server-side, HTTP-only cookie, JSON principal cache | code walk |
| Logout | OK — cookie cleared + server-side invalidated | middleware |

## Findings

- SEC-002 (MED): Default bootstrap credentials in any deployment that forgets APP_ENVIRONMENT=production (incl. docker-compose default). Verified live on a fresh instance. Fix already exists in code (main.py) — it only activates when env is production/staging. Deliverable: document and recommend CI gate; docker-compose should set APP_ENVIRONMENT=production or require explicit DB_PASSWORD replacement.
- SEC-006 (LOW): Password reset token placed in the email query string; recommend short-lived single-use already present, add random rotation + rate limit per account per 5 min, and prefer no-login reset flow over embedding in the link (defense in depth).
- OBS-004 (INFO): Reset link uses built-in `reset_token` bits=42 (~42 bits). Acceptable; bump to 64 if hosting internet-facing.

## Recommendations
1. Set APP_ENVIRONMENT=production in docker-compose (or otherwise require overriding admin_bootstrap_password) before any internet-facing deploy.
2. Admin login rate-limit at the LB; add per-account throttle on reset consumption.
3. Ship an `onboard.sh` that fails hard if CREDENTIAL_ENCRYPTION_SECRET still equals the default.