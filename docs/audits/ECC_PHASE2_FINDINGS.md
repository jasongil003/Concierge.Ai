# ECC Phase 2 findings and closure matrix

Assessment is against the local worktree on `fix/intelligent-ui-v2-phase2-completion`, based on starting HEAD `6bf63f642a5fa6bd77db371860ed8d9989e29b2a`. No changes are committed. This report preserves prior finding IDs and adds no Critical or High finding from the local review.

| Finding | Severity | Root cause / evidence | Current status | Required follow-up |
| --- | --- | --- | --- | --- |
| `ECC-UI-001` | Low | Whole-response guest UI had no real provider streaming path. Native adapters, bounded SSE lifecycle, cancellation, schema validation, and browser handling are implemented; focused provider and browser tests cover deltas, ordering, cancellation, and UI flow. | `FIXED-VERIFIED` locally | Validate live providers and target reverse-proxy buffering. |
| `ECC-UI-002` | Low | Global kill switch was process configuration requiring restart. It now has an audited database-backed admin switch read at each request; e2e verifies fresh-page legacy fallback and V2 denial. | `FIXED-VERIFIED` locally | Measure multi-worker propagation on target DB/runtime. |
| `ECC-OPS-001` | Medium | Clean install/upgrade, TLS/proxy, appliance lifecycle, backup/restore, secret recovery, and deployment rollback require target infrastructure. | `BLOCKED` | Run approved acceptance on an isolated target and capture sanitized evidence. |
| `FILE-DOS-01` | Medium | PDF/file-processing bounds exist, but peak RSS termination/recovery across supported operating systems is not evidenced by this local suite. | `FIXED-UNVERIFIED` | Run the approved synthetic expansion fixture with RSS monitoring on each supported OS. |
| `OPS-021` | Low | Breakfast answer needed a direct property-data assertion. New Playwright assertion checks the exact configured answer on desktop and mobile. | `FIXED-VERIFIED` locally | None for local behavior; provider-backed answer path remains untested. |
| `ECC-SES-001` | Historical High | Renewal used response-time expiry and could skip renewal after a valid request crossed the expiry boundary. Commit `41906552` records authentication time and rechecks expiry/revocation under a write transaction. | `FIXED-VERIFIED` locally | Python 3.12 and concurrent PostgreSQL/Redis matrix remain unavailable. |
| `ECC-UI-003` | Low | `selection_form` presents options as a new text turn; it is not a typed date/time/quantity backend form. There is no configured reservation-slot integration. | `OPEN` (scope limitation) | Add typed form/action protocol only with a real configured backend and server-validated identifiers. |
| `ECC-UI-004` | Low | Facility profiles do not currently expose structured facility policies or reservation actions; map data may not exist for a property. | `OPEN` (data/integration limitation) | Add supported fields/integrations as product data becomes available; keep missing-map fallback. |

## New review

The local code review found no confirmed Critical or High vulnerability in the changed streaming, persistence, feature gate, card, facility, or map paths. Stream events carry only validated data; the map builder binds every read to the authenticated property and only reads guest-visible nodes. The application never treats model text as proof of booking or service success. Dynamic SQL flagged by Bandit in `SessionStore` uses generated placeholder counts with all values bound; final scanner counts are in `ECC_PHASE2_TEST_RESULTS.md`.
