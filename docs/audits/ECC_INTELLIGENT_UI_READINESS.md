# Concierge.AI ECC Audit — Intelligent UI Readiness

> Historical pre-Phase 2 snapshot. Current implementation and verified status are recorded in [ECC_PHASE2_FINAL_VERDICT.md](ECC_PHASE2_FINAL_VERDICT.md), [ECC_PHASE2_FINDINGS.md](ECC_PHASE2_FINDINGS.md), and the Phase 2 docs under `docs/intelligent-ui/`.

## Assessment

The current working tree contains a parallel, feature-gated Intelligent UI implementation. The backend can safely support a **non-streaming internal prototype** based on the reviewed controls and local tests. It is not ready for a controlled guest pilot or production release: release cleanliness, environment acceptance, exact answer-quality checks, streaming requirements, and rollback operations remain incomplete.

## Capability review

| Capability | Assessment |
| --- | --- |
| Conversation-first UI | Present in the parallel guest page; existing guest session is reused. Browser and backend coverage exists. |
| Structured AI response | Versioned Pydantic protocol (`app/intelligent_ui.py:151-174`); extra fields forbidden; bounded block count and content. **Pass for current v1** |
| Adaptive UI blocks | Text, suggestions, entity cards, detail panels, selection/review/confirmation, map, loading, and error block types are allowlisted. |
| SSE streaming | Not implemented. `/api/guest/intelligent-chat` returns a complete response. **Gap `ECC-UI-001`** |
| Restaurant cards | Adapter loads from the authenticated session’s property and bounds visible card count/fields (`app/main.py:6277-6343`). |
| Guest service workflow | Proposal/review and explicit confirmation use existing signed, scoped backend actions; no model-selected tool route is exposed. |
| Session continuity | Guest cookie/session can be resumed. Conversation transcript is in tab-scoped `sessionStorage`, not durable server history. On a shared device, it is visible to same-origin scripts and browser users for that tab/session. |
| Property presentation/isolation | Welcome/config and cards derive from the resolved property. Existing session route checks remain in path. |
| Feature flag | Page, asset, config, and chat gates require global process flag plus strict property flag; malformed property settings fail closed (`app/main.py:523-536,1232-1256,1414-1431`). |
| Legacy rollback | Per-property disable applies on subsequent requests. Global disable requires a process restart; open clients may require reload. **Gap `ECC-UI-002`** |

## Security controls observed

- `app/intelligent_ui.py` uses strict Pydantic schemas with `extra="forbid"`, literals for block types, explicit limits for text/list sizes, and schema version `1.0`. The protocol carries no HTML, script, arbitrary URL, API path, or model-selected action field.
- `app/guest_v2/app.js` validates block types and constructs DOM through element/text APIs. AI-provided text such as `<script>…</script>` stays text; it is not inserted as HTML.
- `/api/guest/intelligent-chat` first authenticates with `_guest_session`, checks the feature gate, then delegates to the established `chat()` path to preserve retrieval/provider/rate-limit policy. It returns bounded blocks; invalid response data falls back to one bounded text block.
- Restaurant data is selected from `session.property_id`; the browser cannot supply a restaurant URL/action to the adapter.
- Service actions require backend proposal and explicit signed confirmation. The front-end confirmation is not treated as the authorization decision.
- The global feature switch is default-off and property setting must be strict boolean true. Unknown settings fail closed.

## Required adaptations before a pilot

1. Decide whether SSE is a requirement. If it is, specify event limits, authentication, cancellation, heartbeat, replay/reconnect behavior, output validation, rate-limit accounting, and disconnect cleanup before implementing it.
2. Add exact end-to-end assertions for representative property-grounded questions (including breakfast hours and unknown-hours response) across desktop and mobile. Current generic evaluation claims are not enough.
3. Rehearse the global rollback on the target deployment and record disable/restart/reload timings. Confirm asset/API gates fail closed while a restart is in progress.
4. Define shared-device transcript retention, clearing, and privacy behavior. `sessionStorage` limits persistence to the tab but is not a security boundary from same-origin scripts or a later user of an open tab.
5. Review the complete Intelligent UI source/test changes on a clean release branch and repeat CI; the implementation is currently uncommitted local work.
6. Validate the experience with synthetic hotel content and a disposable appliance before enabling for guests.

## Verdict

**Compatible for an internal demo; not yet a pilot candidate.** Current data-only schema, existing authorization path, property-derived cards, inert text renderer, and explicit action confirmation are sound safeguards for the implemented scope. Streaming and operational rollback expectations need resolution, and target environment acceptance remains outstanding. Findings: `ECC-UI-001` and `ECC-UI-002`, both Low/Open.
