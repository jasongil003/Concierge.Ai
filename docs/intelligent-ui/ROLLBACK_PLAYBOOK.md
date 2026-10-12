# Intelligent UI rollback playbook

## Property-level rollback

1. Sign in to the existing admin portal and select the affected property.
2. Open **System → Settings → Guest interface**.
3. Clear **Enable Intelligent UI for this property** and save.
4. Reload the property's guest root URL. It should serve `app/static/index.html` and the legacy `/static/styles.css` asset.
5. Confirm `/api/guest/intelligent-chat` rejects the disabled UI request. Existing `/api/chat` and guest service endpoints remain available to the legacy client.

The browser test `Intelligent UI: server-side rollback restores legacy and query parameters cannot enable v2` executes this sequence. No migration downgrade is needed.

## Global emergency rollback

1. Set `INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=false` in the server environment.
2. Restart the local/application process using the site's normal service procedure.
3. Reload the guest URL. All properties return to the legacy interface regardless of their stored property opt-in.

The global process flag is deliberately not editable through the property portal. Changing it requires a restart, while a property rollback takes effect on the next request.

## State and recovery

- No table, migration, or backend schema was added.
- Existing property configuration is additive JSON; setting its enable flag to false is sufficient.
- V2 conversations live in tab-scoped browser storage and existing guest session credentials. Starting a new conversation drops the current tab transcript and creates another authorized server session.
- Keep the feature branch and v2 files during rollback; the route gate prevents their use. Removing the UI later is a separate reviewed code change.
- Do not reset or delete the database, guest sessions, or hotel content during rollback.
