# Conversation Module Studio audit and plan

## Confirmed implementation

- Modules are currently stored as a JSON list in the property's `guest_modules` column. The column is already property scoped; no module-specific persistence API or schema versioning exists.
- The admin page edits name, free-text prompt, order, and visibility through the general property update API. Saving makes the module immediately visible to guests.
- `/api/hotel` exposes enabled modules through `PropertyRecord.public_profile`. The legacy guest renderer sorts by `order` and sends `module.prompt` as a guest chat message.
- The prompt is an ordinary guest message to the property's configured concierge; it does not directly invoke a privileged backend operation. Existing property/AI guardrails still apply.
- The separate visual page builder already validates typed actions for prompt, property navigation, external links, phone/email, map, property resources, and service-catalog requests. The guest action runner can route a configured service through the proposal and guest-confirmation flow; request creation returns the backend request record.
- Guest service catalog, recommendations, facilities, restaurants, and property location APIs are property scoped. No per-module impression/action analytics are currently recorded.
- Existing module tests cover property persistence and a basic admin panel smoke check. They do not cover typed actions, draft/publish, version history, rollback, or module property isolation.

## Delivery plan

1. Validate module configuration server-side with a strict, typed action allow-list while normalizing legacy prompt-only modules safely. Incomplete but schema-safe configurations may be saved as drafts; publish runs strict validation and verifies Service Catalog references.
2. Add property-scoped module management endpoints that save drafts separately from guest-visible published configuration, enforce revision checks, and retain bounded published snapshots for rollback. The implementation reuses the existing property `guest_modules` JSON column; it adds no destructive migration.
3. Redesign the admin page as a searchable/filterable visual library with starter templates, a responsive editor drawer, action-specific fields, synthetic live preview, keyboard reorder controls, and explicit save/publish/archive/delete actions.
4. Route published module taps through the existing typed guest action handlers; retain prompt-only compatibility for legacy modules.
5. Add backend and browser tests for legacy compatibility, validation, service mapping, property isolation, publishing, rollback, ordering, accessibility, and responsive preview.

## Capability boundaries

- Supported module actions will reuse existing validated paths: AI prompt, property information, property/explore navigation, property map, approved HTTP(S) navigation, and a service-catalog request that remains guest-confirmed.
- A generic guided-workflow engine, indoor turn-by-turn directions, module analytics, locale-specific translated module content, staff escalation policy per module, and external provider readiness checks do not currently exist. The studio must label these unavailable instead of implying they execute.
- Recommendation cards can route guests to the existing Explore experience. External recommendation data remains subject to the property’s existing provider and privacy configuration.
- Publishing applies one property’s validated modules. The latest 20 published snapshots are retained per module. Rollback creates a new draft from a retained snapshot and requires a deliberate publish action.
- The new admin API is `GET/POST /api/admin/properties/{property_id}/conversation-modules`, `PUT/DELETE .../{module_id}`, and explicit `publish`, `archive`, `rollback`, and `reorder` actions. Route policy inventory requires property view for reads and property edit for changes.
- Guest public profiles expose only the last published, enabled configuration. A saved draft does not replace a published configuration. Legacy prompt-only modules remain readable and are normalized to typed prompt actions when edited.

## Verification

- Backend regression coverage: `504 passed, 2 warnings` across conversation modules, properties, operational admin, and route-policy inventory tests. Tests used an isolated synthetic property fixture; the configured local SQLite database was not changed.
- Browser coverage: `8 passed` across Chromium and mobile Chromium for the legacy module admin smoke test, draft-save/publish workflow, typed property-information guest action, and typed service action opening the existing guest confirmation flow. The mobile check also asserts no horizontal document overflow.
- Responsive captures: desktop at 1366px, tablet at 768px, and mobile at 390px. The module editor is usable at all three widths; tablet retains the two-panel editor and mobile stacks the configuration form with a scrollable editor body and preview below it.
- Static checks: JavaScript syntax checks and `git diff --check` pass; trailing whitespace was cleaned up.
- Security checks: Bandit exited successfully at the repository's configured medium severity/confidence threshold; it emitted existing `nosec`/B608 parser warnings. `npm audit` could not resolve `registry.npmjs.org`, `pip-audit` could not prepare its temporary environment because its pip upgrade needs network access, and the pinned Gitleaks executable is not installed locally. Dependency and secret scanning therefore remain unverified in this offline workspace; no scanner was disabled.
- No database migration was required. Existing published module data remains visible while an edited draft is saved; incomplete drafts stay hidden until strict server-side publish validation succeeds.
