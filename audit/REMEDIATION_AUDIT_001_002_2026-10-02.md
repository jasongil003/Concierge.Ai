# ECC remediation: AUDIT-001 and AUDIT-002

Date: 2026-10-02
Repository: `jasongil003/Concierge.Ai`
Base: `main` at `96e8ddd9d1f65e00ca24131b58dac55ba0caaeaf`
Branch: `fix/ecc-high-rbac-boundaries`

## Scope and baseline

This change addresses only the two High findings AUDIT-001 and AUDIT-002 from `audit/FINAL_ECC_AUDIT_2026-10-02.md`. No change was made to PROD-003 through PROD-011 or AUDIT-003 onward. Before implementation, both findings were exercised against an isolated checkout of the audited main commit with temporary SQLite data. The pre-fix reproduction confirmed unauthorized reads and persisted writes for protected AI, ANTlabs, guardrail, deployment, and stay values. The temporary checkout and reproduction data were outside the repository and were not added to this branch.

The audited data model has property ownership for properties and department ownership for departments, service catalog entries, and service requests. Guest identity/stay rows do not contain a department relationship. No ownership is inferred from room names, department names, or other strings.

## AUDIT-001 — HIGH (remediated)

**Root cause:** The generic property serializer returned a broad property record to roles with only property read access. The generic `PUT /api/admin/properties/{property_id}` accepted the same broad model and persisted privileged nested configuration under the route's general `properties.edit` permission.

**Affected roles:** Content Manager was the confirmed vulnerable default role: it has `properties.edit` but not AI, security, or integration configuration permissions. The same issue applied to any custom role with `properties.edit` and without the relevant field-domain permissions. The read exposure applied to any role whose property read permission admitted the generic record.

**Affected routes:**

- `GET /api/admin/properties` and `GET /api/admin/properties/{property_id}`.
- `PUT /api/admin/properties/{property_id}`.

**Protected fields exposed or writable before the fix:** AI settings and provider/model/routing values; personality; ANTlabs authentication and integration configuration; guardrails including the ANTlabs signature secret; domain/deployment settings; and nested application/deployment settings. The pre-fix persistence reproduction inspected stored records after writes rather than relying on response bodies alone.

**Fix:** The generic serializer now applies permission-based field projections and nested allowlists. Secret-like values in authorized AI, integration, and application settings are redacted. Generic updates are partial: omitted protected fields remain intact, and a redacted secret round-trip retains its stored value. Explicit field ownership is enforced before persistence:

| Field group | Required permission |
| --- | --- |
| AI settings and personality | `ai.configure` |
| ANTlabs configuration | `integrations.configure` and `security.configure` |
| Guardrails | `security.configure`; network guardrail keys also require `network.manage` |
| Knowledge sources | `knowledge.edit` |
| Domain | `domains.configure` and `network.manage` |
| Deployment mode | `domains.configure` |
| Application locations/settings | `properties.edit`, with unknown nested keys requiring `system.configure` |
| Deployment settings | `domains.configure` and `network.manage`, with unknown nested keys requiring `system.configure` |
| Other app-setting groups or unknown guardrail keys | `system.configure` (plus the parent field's permission) |

The dedicated AI, guardrail, network, and integration endpoints retain their explicit route policies. The admin UI now submits only fields the current principal can edit and omits server-managed deployment verification state.

**Tests:** `tests/test_high_rbac_boundaries.py` checks Content Manager reads and writes, nested/unknown keys, database state after denials, preservation of protected data during normal edits, redacted-secret round-trips, and the six-role matrix. The full backend suite also covers existing AI, property, and guardrail behavior.

## AUDIT-002 — HIGH (remediated by fail-closed denial)

**Root cause:** Department Manager had `guest_sessions.view` and `guest_sessions.manage`, but stay/session list and mutation paths were property-scoped. Guest stay records have no reliable department owner, so a server-side department ownership predicate cannot be evaluated safely.

**Affected routes:**

- `GET /api/admin/properties/{property_id}/sessions`.
- `GET` and `PUT /api/admin/properties/{property_id}/conversations/retention`.
- `POST /api/admin/properties/{property_id}/sessions/reconnect`.
- `PUT /api/admin/properties/{property_id}/stays/{stay_id}/memory`.
- `POST /api/admin/properties/{property_id}/stays/{stay_id}/checkout`.

The stay routes use the explicit `guest_sessions.view` or `guest_sessions.manage` policies in `app/admin_route_policies.json`. The department-scoped role no longer receives those permissions. Authentication also strips the two permissions from the effective Department Manager principal if legacy or customized role rows still contain them. This remains fail-closed until guest session/stay records gain a reliable department ownership relation.

**Department ownership rule:** No guest session/stay ownership is currently derivable from the data model. Department Managers therefore cannot access guest session/stay operations, including records that might appear operationally related to their department. Their existing department-scoped service request and catalog workflows remain available through their established department identifiers and predicates. Property Managers and Super Admin retain the existing property-wide guest-session behavior subject to property scope.

**Tests:** The regression creates two departments, two managers, distinct sentinel stays, matching department names across two properties, and a legacy role-row permission grant. It calls session listing, query-parameter variants, retention, reconnection, direct stay IDs for both departments, cross-property paths, memory updates, and checkout. Tests assert denial and verify stored stay/memory/retention state remains unchanged. The role matrix verifies Super Admin and Property Manager behavior remains available.

## Permission matrix

Derived from `DEFAULT_ROLES`, `PERMISSIONS`, route policies, and the effective Department Manager permission filter. “Normal property edit” means the general property update route; roles may have other feature-specific editing permissions.

| Role | Normal property read | Normal property edit | AI read | AI edit/configure | Security/integration edit | Guest sessions view | Guest sessions manage | Department scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Platform Admin (`super-admin`) | Yes, all properties | Yes | Yes | Yes | Yes | Yes | Yes | Platform-wide |
| Hotel Manager (`property-manager`) | Yes, assigned property | Yes | Yes | No (`ai.view` only) | No | Yes | Yes | Property-wide within assigned property |
| Content Manager (`content-manager`) | Yes, assigned property | Yes | No | No | No | No | No | Content/features within assigned property |
| Department Manager (`department-manager`) | Yes, assigned property | No | No | No | No | No | No | Assigned department for supported service/catalog operations; guest stays unavailable |
| Restaurant Manager (`restaurant-manager`) | Yes, assigned property | No | No | No | No | No | No | Assigned restaurant resources within property |
| Restaurant Staff (`restaurant-staff`) | Yes, assigned property | No | No | No | No | No | No | Assigned restaurant resources within property |

`ai.edit` is not a canonical permission in this repository; AI writes require `ai.configure`. In this matrix, security/integration edit refers to generic guardrail and ANTlabs configuration; their write boundary requires `security.configure`, and ANTlabs additionally requires `integrations.configure`. Network configuration uses `network.manage` on its dedicated routes.

## ECC security review

An independent second-pass review traced the generic list/detail/update routes, route-policy inventory, privileged endpoint families, role authentication, and every `PropertyStore.upsert` call site in `app/main.py`.

1. A principal with `properties.edit` but without `ai.view`/`ai.configure` cannot read or update protected AI configuration through the generic property routes. Dedicated AI reads and writes remain permission-gated.
2. Generic nested mass assignment for guardrails, network/deployment, integration, and authentication-related configuration is checked at the privileged object boundary. Unknown nested app, deployment, and guardrail fields fail closed behind `system.configure`; network keys require `network.manage` as well.
3. Department Managers cannot access guest/session/stay records through the inventoried routes because the effective principal lacks both guest-session permissions.
4. Direct stay IDs, query variations, and alternate session operations remain denied at the route-policy/authentication boundary before mutations execute.
5. Property isolation remains enforced by the admin middleware's property access check and property-keyed stores. Regression tests use another property with the same department name and verify cross-property access is denied.

Other `PropertyStore.upsert` sites were reviewed: logo update is protected by `properties.edit`; guardrail and network mutations use their dedicated policies and checks; deployment verification is permission-gated. No additional defect using the same generic property serializer/update mechanism was identified. No unrelated audit finding was changed.

## ECC code review

The post-change review checked permission consistency, partial-update compatibility, secret redaction and round-trip behavior, stale permission rows, property/department boundaries, frontend field assumptions, and negative-test persistence assertions. No blocking finding remained in the scoped changes. The frontend tolerates omitted protected fields and omits unauthorized settings when saving. Existing `PropertyStore.upsert` call paths outside the generic endpoint retain their explicit permissions.

## Verification

| Check | Result |
| --- | --- |
| Pre-fix isolated AUDIT-001/AUDIT-002 reproduction | Confirmed vulnerable behavior before changes |
| Targeted authorization regression tests | 3 passed |
| Full backend pytest | 815 passed, 16 skipped, 0 failed |
| Playwright (`npm run test:e2e`) | 257 passed, 35 skipped, 0 failed |
| Python compile check | Passed: `.venv/bin/python -m compileall -q app` |
| JavaScript syntax | Passed: `node --check app/static/admin.js` |
| Bandit | Passed at medium severity/confidence; existing B608 `nosec` annotation warnings were reported |
| CI YAML parse | Passed |
| Shell syntax | Passed for deployment shell scripts |
| ShellCheck | Passed with `--severity=warning -x` across deployment shell scripts |
| Docker Compose config | Passed using temporary validation-only values and `/dev/null` for the absent local `.env` |
| `git diff --check` | Passed |

Playwright initially could not bind its configured local server under the default sandbox. The same suite was rerun with local test-server permission and completed successfully. Skips are the suite's configured project-specific exclusions, including desktop-only checks in the mobile project.

## Remaining findings

The audited report counted 0 Critical, 2 High, and 14 Medium findings before this remediation. AUDIT-001 and AUDIT-002 are remediated by this change; no other finding was modified. Remaining after this scoped remediation: **Critical 0, High 0, Medium 14**.
