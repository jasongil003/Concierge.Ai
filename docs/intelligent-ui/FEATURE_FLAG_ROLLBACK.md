# Intelligent UI feature flag and rollback

## Source of truth

The guest experience requires all three conditions:

1. Environment master `INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=true`.
2. Persisted global operational switch enabled in the existing `platform_settings` store.
3. The current property's `guest_experience.intelligent_ui.enabled` is strict boolean `true`.

Any missing, malformed, or disabled setting fails closed. Request parameters, cookies, and browser storage cannot override the decision. The environment master is an installation-level ceiling: an administrator cannot turn the UI back on while it is off.

## Emergency disable

An administrator with `system.configure` may update `PUT /api/admin/system/intelligent-ui` with CSRF protection. The handler writes the global setting to the shared database, records an audit event, and reads it on each decision; there is no process-local flag cache. The change therefore applies on the next request across workers that share the operational database. The legacy homepage is served when disabled. V2 assets, config, history, and chat routes check the same flag and return 404.

Per-property enablement remains independent underneath the global ceiling. Disabling the global switch preserves property settings, sessions, and stored turns; it does not delete data. Existing guest sessions remain subject to normal expiry and revocation. Re-enable requires the environment master on and an authorized admin action.

## Rollback procedure

1. Use an account with `system.configure` and a valid CSRF token.
2. Set the global switch to disabled.
3. Verify the audit event and read the value from `GET /api/admin/system/intelligent-ui`.
4. Verify a fresh guest page receives the legacy UI, and V2 page assets/chat/history endpoints reject requests.
5. Confirm guest sessions and data remain intact.

The isolated Playwright rollback test verifies legacy fallback and rejects query-parameter enablement. Cross-worker propagation and operator response time are not measured against the production database/runtime. If the database is unavailable, the switch read fails closed to the environment default; an environment-level disable remains the ultimate fallback and may require a process restart for configuration reload.
