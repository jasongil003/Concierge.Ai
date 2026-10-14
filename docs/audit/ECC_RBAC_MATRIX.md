# ECC RBAC matrix

Date: 2026-10-14 (Asia/Manila)  
Source of truth: `app/admin_auth.py:20-204` role definitions and `app/admin_route_policies.json` method/path policies at HEAD `82f9df2bafb4b3a632912762364fd6c7dff4a532`.

The application defines **54 permissions, nine system admin roles, and 188 admin route policies**. The table shows selected high-impact permissions exactly as seeded; `—` means the role does not receive that permission by default. Custom roles may have a subset of the creator's permissions. The guest is a separate session principal and is not an admin role.

| Role | Property scope | Users / roles | Property edit | Knowledge edit / publish | Restaurant manage / menu approve | Requests manage | Conversations reply | Guest stays manage | AI configure | Network / security configure | Reports export |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Super Admin | All | Both | Yes | Both | Both | Yes | Yes | Yes | Yes | Both | Yes |
| Property Administrator | Assigned property | Both | Yes | Both | Both | Yes | Yes | Yes | Yes | Both | Yes |
| Property Manager | Assigned property | — | Yes | Both | Both | Yes | Yes | Yes | — | — | Yes |
| Department Manager | Assigned property and department | — | — | — | — | Yes | — | — | — | — | Yes |
| Restaurant Manager | Assigned property and restaurants | — | — | — | Both | — | Yes | — | — | — | — |
| Restaurant Staff | Assigned property and restaurants | — | — | — | — | — | Yes | — | — | — | — |
| Concierge / Front Desk | Assigned property | — | — | — | — | Yes | Yes | — | — | — | — |
| Content Manager | Assigned property | — | Yes | Both | Both | — | — | — | — | — | Yes |
| Viewer / Auditor | Assigned property | — | — | — | — | — | — | — | — | — | Yes |
| Guest | Bound guest session/property | — | — | — | — | Own guest actions only | Own conversation only | — | — | — | — |

**Scope enforcement:** `app/main.py:397-447` checks route permission, property path, and CSRF server-side. `app/admin_auth.py:653-787` validates user role/property assignment and permission delegation. Department object boundaries are checked in the service request handlers; restaurant assignments use `user_restaurants` and handler checks. These are runtime checks, not UI visibility rules.

**Important permission domains:** `properties.edit` can edit ordinary property content but protected fields such as provider settings, network configuration, security guardrails, and deployment settings require additional permissions (`app/main.py:802-891`). Location observation/report routes currently use `properties.edit`; they are covered by SEC-H02 in the security report because that permission does not establish guest consent or a retention lifecycle. The configuration assistant's confirm endpoint has route permission `assistant.use`, then validates the proposed action and required domain permissions server-side.

**Negative verification:** 472 focused auth/RBAC/security tests passed, including route inventory, every system role's permission set, content manager protected-field writes, department cross-scope requests, cross-property checks, and session controls. The eight additional guest/network/upload/SQL suites passed 166 tests. These results support the listed controls and do not certify every untested object path.
