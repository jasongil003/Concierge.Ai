# Concierge.AI ECC Audit — Guest Session Expiry Review

## Conclusion

**The guest sliding-expiry race reported against commit `cfb7155ab8e347481af78b33f73f02e0d9ae9ed2` is fixed in the audited checkout and locally verified.** The deterministic regression test covers the original boundary case, cookie lifetime, repeated activity, rejection of expired credentials, and non-revival after revocation. No token is renewed merely because its session row exists.

## Root cause and history

The original implementation authenticated a guest credential before route handling, then attempted renewal after the response. The renewal function required `guest_token_expires_at > now` at response time. A token valid at authentication could expire while a request was being handled. The route still returned 200, but renewal failed, leaving the SQLite expiry near “now”; this matches the reported CI symptom.

Commit `cfb7155ab8e347481af78b33f73f02e0d9ae9ed2` introduced per-session guest cookies and response-time sliding renewal. Commit `419065052a01467db7f738079d3f2bb6b4f2368e3` carries an authentication timestamp through request state and changes renewal validation to use it. These history findings were checked before reaching the current implementation conclusion.

## Current request flow

1. `_guest_session` resolves the session id, loads its row, verifies both guest credential hashes and revoked/expiry fields, and captures `validated_at` after the database read (`app/main.py:646-711`; `app/session_store.py:450-479`). Expiry at or before this authentication instant is rejected.
2. The authenticated dependency records a refresh candidate for the request. Routes such as `/api/guest/personalization` use this dependency.
3. After a successful response, middleware attempts renewal (`app/main.py:611-643,3524-3620`). Error responses do not refresh cookies; invalid credentials may trigger cookie cleanup.
4. `extend_guest_credentials_if_needed` rejects absent credentials, a future validation time, or validation older than one TTL. In a write transaction it rereads current hashes, expiry, and revocation state, compares hashes in constant time, and updates only if the row still matches and expiry exceeded `validated_at` (`app/session_store.py:396-448`).
5. Only when the database update succeeds does the response set the guest cookie with the same configured TTL. The DB write occurs before `Set-Cookie` is emitted.

For SQLite, writes use `BEGIN IMMEDIATE`; PostgreSQL begins a transaction and the update has conditional row predicates. Revocation/hash changes prevent the conditional update from renewing stale credentials. A separate absolute lifetime cap is not configured in the reviewed implementation. Renewal is bounded by the configured guest inactivity TTL and the `last_seen_at` inactivity check.

## Independent verification matrix

| Requirement | Evidence/result |
| --- | --- |
| Expired before authentication is rejected | `test_expired_guest_credential_is_rejected`; HTTP 401. Related expired-resume test verifies row removal and no refreshed cookie. **Pass** |
| Valid at authentication may finish across expiry and renew | `test_active_guest_activity_slides_expiry_and_refreshes_cookie_age` advances a deterministic clock during personalization. **Pass** |
| Database expiry slides | Test asserts at least `clock.current + 1700` for an 1800-second TTL. **Pass** |
| Cookie lifetime aligns | Response carries the session cookie with `Max-Age=1800` after successful renewal. **Pass** |
| Repeated activity slides again | Same deterministic test moves expiry near and asserts a second renewal and cookie refresh. **Pass** |
| Revoked before request cannot be used | `test_revoked_guest_credential_is_rejected`; HTTP 401 and revoked row remains unchanged. **Pass** |
| Revoked after validation is not revived | `test_sliding_guest_refresh_does_not_restore_credentials_revoked_after_authentication`; renewal returns false and hashes/expiry remain cleared. **Pass** |
| Credential hashes revalidated | Constant-time checks before update plus conditional hash predicates; covered by security regression suite. **Pass by code review/tests** |
| Errors do not refresh | Middleware exits for status >=400; covered by expired/revoked checks. **Pass** |
| Concurrent revoke/renewal state | Transaction and conditional update inspected; no deterministic concurrent interleaving test was found. **Not fully verified** |
| Python version matrix | Local Python 3.11.16; CI workflow config uses Python 3.12. Python 3.12 was not installed and live CI could not be queried. **Unverified here** |

## Test outcomes

- Targeted regression: **1 passed, 2 warnings**.
- Full backend pytest: **961 passed, 17 skipped, 2 warnings**.
- The full suite ran against an isolated test database. The persistent `/state` database size and SHA-256 fingerprint remained unchanged.

## Security assessment

The fix preserves the distinction between an already-authenticated request finishing during the expiry boundary and a new request presenting an expired credential. The latter fails before route execution. The renewal authority expires after at most one configured TTL from validation, the database rechecks current revocation and hashes before writing, and cookie refresh follows persisted renewal. There is no evidence of wrong `SessionStore` selection, an uncommitted write, selected-route-only refresh logic, or cookie-only refresh in the current implementation.

**Status:** `ECC-SES-001` — High historical issue, **FIXED-VERIFIED** in this checkout. Complete confidence across concurrent interleavings and Python 3.12 remains limited by the test environment described above.
