# Intelligent UI security assessment

Scope: local implementation on `feature/intelligent-guest-ui-v2`; code review plus the focused backend and Playwright checks recorded in `TEST_RESULTS.md`. This is not a penetration test or production certification.

## Controls retained and added

| Boundary | Control |
| --- | --- |
| Property selection | Resolve the property through the existing server-side property guard before choosing HTML, assets, config, or v2 chat. Guest clients cannot submit a tenant ID to the v2 chat route. |
| Global rollout | Global switch defaults off and is server process configuration. A guest cannot turn it on with query parameters, browser storage, or cookies. |
| Property rollout | Property opt-in is JSON validated and writable only through the existing authenticated property settings endpoint with `properties.edit`. |
| Guest session | V2 config/chat and action routes use existing session cookies, session validation, network policy, and property match checks. The browser restores local transcript only after successful session resume. |
| Origin/CSRF | Guest writes use existing guest-origin controls. Admin writes use the existing CSRF-protected admin route. |
| XSS | AI answer is text-only. Pydantic rejects extra fields. The browser allowlist constructs nodes and assigns user/model/property text with `textContent`. No HTML evaluation or dynamic JavaScript exists. |
| Images/network | V2 cards contain no URLs. The hotel logo is limited to same-origin. There is no model-controlled fetch, API route, or map provider. |
| Service actions | Propose/confirm reuse the existing allowlisted guest service flow; the backend verifies property, session, service, action policy, signed confirmation, and duplicate request key. |
| Property cards | Dining cards are built from the current property's guest-visible records. No AI-supplied restaurant ID or cross-property query is used. |
| Telemetry/privacy | No analytics endpoint or raw-conversation telemetry was added. The browser transcript is tab-scoped; it is not persisted as a new server transcript. |

## Findings and limits

- No new Critical or High issue was found in the focused implementation review. The full Python and Playwright regression suites passed on this branch; this is not a penetration test or production certification.
- Existing repository audit documents include unresolved operational/Medium-level and external validation work, including real ANTlabs gateway binding, production proxy/TLS/host configuration, the Linux PDF resource limit, and provider/advisory checks. See `audit/VULNERABILITY_FINDINGS.md` and `audit/CURRENT_READINESS.md`; these are not resolved by this UI work.
- Session state on a shared browser is protected from automatic cross-session display by tab scoping and the explicit New chat action, but `sessionStorage` is not secure against a person who can inspect the same open browser tab. Do not leave a guest tab open on a shared device.
- Suggested prompts and hotel content are property-admin supplied. They render as text and are not treated as trusted model instructions.
- Global switch changes require a server restart. Property-level rollback affects new page loads immediately.
- The whole-response adapter has no streaming retry/replay protocol. No automatic chat replay occurs after a network interruption.

## Verification

See `TEST_RESULTS.md` for the test commands, counts, real browser screenshots, and remaining unverified infrastructure. Existing RBAC regression tests ran as part of the full suite; this document does not claim the new work resolves unrelated audit findings.
