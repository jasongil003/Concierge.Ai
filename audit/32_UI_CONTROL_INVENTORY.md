# UI Control Inventory

## Verification basis

- Full Playwright run: 167 passed, 11 skipped across desktop Chromium and Pixel 7 mobile Chrome. After password-reset token transport changed, the focused Chromium admin-auth suite was rerun and passed 6/6. The skipped cases are project-specific duplicates for one viewport.
- This is automated coverage, not a manual click-by-click audit of every control. “Partial” means the page has working flows, but every visible control was not individually exercised.
- Roadmap panels explicitly marked unavailable or preview-only are treated as such; they are not counted as working functionality.

| Page | Control / workflow | Expected action | Observed result | Status |
|---|---|---|---|---|
| Guest home | Initial state, hotel identity, suggested prompts | Render branded welcome and send suggestions | Covered in desktop and mobile tests | PASS |
| Guest chat | Typing, send, Enter, Shift+Enter, empty submit | Send message, prevent empty sends, preserve line breaks | Covered in browser tests | PASS |
| Guest chat | Streaming responses | Incrementally render provider tokens | No streaming response path; waits for complete JSON response | NOT IMPLEMENTED |
| Guest chat | Context, follow-up, long input, multiple conversations | Maintain isolated, bounded context and recover from errors | Recent-message store and fixed follow-up helper exist; live multi-turn/provider checks incomplete | PARTIAL |
| Guest chat | AI outage | Friendly error and useful verified fallback | AI error shown; saved hotel recommendations remain available after fix | PASS |
| Guest menu | Open, close, options, new conversation | Menu controls work and session resets | Covered in desktop/mobile browser tests | PASS |
| Guest menu | Hotel information, language, accessibility, privacy, help | Provide configured details or clear status | Covered in browser tests; privacy notice now states idle expiry and opt-in memory | PASS |
| Guest recommendations | Recommendation cards, details, directions | Show safe text, toggle details, open configured map | Covered on desktop/mobile | PASS |
| Guest requests | Service confirmation and submission | Require confirmation and return tracked request id | Covered on desktop/mobile | PASS |
| Guest personalization | Opt in, save/edit/remove/clear preferences | Store guest-scoped memory and honor privacy choice | Backend and UI workflows exist; no cross-browser human evaluation | PARTIAL |
| Guest uploads | Text document upload | Read allowed text types, bound size, pass only current message context | Server restricts to text types and 1 MB; no durable upload or parser for office/PDF files | PARTIAL |
| Guest map | Property map overlay and routes | Show configured map / route nodes | Some map controls are tested; navigation quality and route graph edge cases are not | PARTIAL |
| Admin login | Login, logout, visibility, recovery dialog, reset link | Authenticate, revoke session, show generic reset result, keep reset token out of query/history | Chromium checks pass for fragment parsing/history cleanup; backend verifies email URL generation. Live SMTP delivery is not exercised. | PASS |
| Admin shell | Sidebar, profile, property selector, responsive navigation | Navigate to each panel at phone/tablet/desktop widths | Automated coverage passes; several panels are labeled unavailable | PASS |
| Admin dashboard | Metrics, health, alerts, charts, navigation | Display telemetry-backed data and alert investigation | Backend-backed telemetry and analytics; some host values may be unavailable | PARTIAL |
| Admin hotel configuration | Save/publish/discard/restore, hotel info | Persist configuration and manage drafts | Browser tests pass for tested flows | PASS |
| Admin service catalog | Departments, services, duplication, recommendations | Create/edit/delete hotel content | Browser workflow passes after preserving selection during async refresh | PASS |
| Admin requests | Create, assign, advance, close, staff response | Track property service requests | Tested workflows pass; request permissions still need dedicated security review | PASS |
| Admin knowledge | FAQ/document list, upload, replace, delete | Extract approved content and expose retrieval status | Text ingestion only; no PDF/DOCX extraction, embeddings, or vector index | PARTIAL |
| Admin AI providers | Select provider/model, save secret, test status | Keep credentials server-side and route through provider adapter | UI/API workflows are covered; real credentials and outage behavior not exercised with live providers | PARTIAL |
| Admin operations assistant | Ask questions, inspect evidence, use management reports | Use authorized diagnostic tools and cite observations | Read-only tool calls and evidence output are implemented; live model synthesis not evaluated | PARTIAL |
| Admin reports | XLSX/PDF exports | Export selected-period property analytics | Endpoints exist and report generators are tested; values and file rendering were not visually reconciled against production-scale records | PARTIAL |
| Admin users / roles / audit | Create/edit/revoke users, roles, inspect audit | Enforce server RBAC and trace changes | Main auth/role controls are tested; all custom permission combinations are not | PARTIAL |
| Admin system placeholders | PMS, cloud billing, Microsoft provider, advanced settings | Clearly communicate unavailable state | Roadmap placeholders are marked as unavailable; integrations are not implemented | NOT IMPLEMENTED |

The full route list and shared authorization controls are in [API inventory](31_API_INVENTORY_COMPLETE.md). Existing manual checklist source is [MANUAL_UI_CHECKLIST.md](../MANUAL_UI_CHECKLIST.md); its result fields were blank before this run.
