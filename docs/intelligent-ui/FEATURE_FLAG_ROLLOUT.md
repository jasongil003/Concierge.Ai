# Intelligent UI feature flag and rollout

## Evaluation

The interface is selected at `GET /` only after `_guest_property` resolves the current property and `_enforce_guest_network` accepts the guest request. v2 is served only when both conditions are true:

```text
INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=true
AND
app_settings.guest_experience.intelligent_ui.enabled=true
```

The global setting defaults to `false`. The property setting defaults to `false`. Guest query parameters, cookies, local storage, and headers cannot turn it on. The asset route and v2 API check the same conditions on every request. No property is opted in by default.

## Property configuration

The existing Admin → System → Settings panel provides property-scoped controls for enablement, welcome copy, and up to six approved starter prompts. The values are saved in `app_settings.guest_experience` using the existing property update route. The backend requires `properties.edit` and validates the shape. Existing admin mutation audit records capture the property path and actor.

Example:

```json
{
  "guest_experience": {
    "intelligent_ui": { "enabled": true },
    "welcome_message": "Ask me about the hotel's verified services.",
    "suggested_prompts": [
      "What time is the pool open?",
      "Where can I have dinner?"
    ]
  }
}
```

The property toggle is only effective after the server-wide switch is on. The global switch is process configuration and changing it requires the normal application restart. It is not exposed through property administration.

## Local synthetic demo

1. Use an isolated local test/demo property, never a production property. Set `DB_PATH` to a dedicated local demo database before starting if the normal `.env` database contains user or hotel data.
2. Run `./scripts/start-intelligent-ui-demo.sh`. It binds to loopback, checks the selected port, and turns on the global switch for this process only. Set `INTELLIGENT_UI_DEMO_PORT` to choose another port.
3. In Admin for the synthetic property, enable Intelligent UI and save the approved welcome and suggested prompts.
4. Open `/` on that property. The response should load `/intelligent-ui/styles.css`.
5. Confirm another property remains on the legacy HTML, then switch the demo property back to legacy and reload.

The Playwright server uses a temporary database, sets the global switch for the test process, and creates/opts in the synthetic test property only within that test run.

## Emergency disable and rollout control

- Property rollback: clear **Enable Intelligent UI for this property** in Admin and save. New root-page loads immediately serve the legacy shell; v2 assets and API calls fail closed.
- Global emergency stop: set `INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=false` in the server environment and restart. This disables v2 for every property.
- The database schema does not depend on v2. Rollback preserves the legacy guest app, property data, sessions, and existing admin portal.

Do not opt in production properties from this local branch. There is no automatic rollout and no deployment action in this implementation.
