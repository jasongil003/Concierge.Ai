# UI Control Inventory

## Verification basis

- Full Playwright run after the PR #31 restaurant workflows and dependency upgrades: **173 passed, 13 skipped, 0 failed** across desktop Chromium and Pixel 7 mobile Chrome. Chromium-only mutation workflows are skipped on mobile; remaining skips are viewport-specific duplicates.
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
| Guest menu | Talk to Restaurant Staff | Select a restaurant and explicitly route a guest request to its staff queue | New desktop E2E creates a restaurant, opens the staff dialog, submits the request and verifies the escalation response; backend enforces property, restaurant and rate limits | PASS (local automated) |
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
| Admin restaurants | Create, edit, hours, disable/archive, guest/internal details | Manage property-owned restaurants and assigned restaurant views | Desktop E2E creates a venue, edits weekly hours, approves/publishes a menu and promotion, then archives it; API tests cover manager/staff assignment and isolation | PASS (local automated) |
| Admin restaurant content | Menu/item editing and promotion approval/publication | Keep guest-facing information approved and property/restaurant scoped | Desktop E2E covers the menu/item and promotion state transitions; backend tests cover role permission boundaries and guest filtering | PASS (local automated) |
| Admin users / roles | Restaurant Manager/Staff assignment checkboxes, select all, clear | Restrict accounts to the selected restaurants | Backend tests cover restaurant ID/property validation and role ceilings; visible assignment controls exist, but the checkbox sequence is not yet a dedicated browser test | PARTIAL |
| Admin conversations | Restaurant inbox accept, assign/reassign, reply, resolve, return to AI | Route conversations to assigned staff and pause AI during takeover | Backend workflow tests cover restaurant ownership, atomic accept, audit events and AI pause; existing browser test covers the legacy hotel conversation path, not the full restaurant-staff inbox UI | PARTIAL |
| Admin requests | Create, assign, advance, close, staff response | Track property service requests | Tested workflows pass; request permissions still need dedicated security review | PASS |
| Admin knowledge | FAQ/source upload, processing, review, approval, publish, replace, conflict resolution | Extract supported files into reviewable property-scoped knowledge | PDF, DOCX, XLSX, CSV, TXT, Markdown, JSON, PPTX, PNG, JPEG and WEBP are supported; chunks retain source/location metadata, conflicts are reviewed before guest use, and image OCR requires Tesseract. No dense vector retrieval; guest answers do not show citations. | PARTIAL |
| Admin AI providers | Select provider/model, save secret, test status | Keep credentials server-side and route through provider adapter | UI/API workflows are covered; real credentials and outage behavior not exercised with live providers | PARTIAL |
| Admin operations assistant | Ask questions, inspect evidence, use management reports | Use authorized diagnostic tools and cite observations | Read-only tool calls and evidence output are implemented; live model synthesis not evaluated | PARTIAL |
| Admin reports | XLSX/PDF exports | Export selected-period property analytics | Endpoints exist and report generators are tested; values and file rendering were not visually reconciled against production-scale records | PARTIAL |
| Admin users / roles / audit | Create/edit/revoke users, roles, inspect audit | Enforce server RBAC and trace changes | Main auth/role controls are tested; all custom permission combinations are not | PARTIAL |
| Admin system placeholders | PMS, cloud billing, Microsoft provider, advanced settings | Clearly communicate unavailable state | Roadmap placeholders are marked as unavailable; integrations are not implemented | NOT IMPLEMENTED |

The full 190 method/path route list and shared authorization controls are in [API inventory](31_API_INVENTORY_COMPLETE.md). The manual checklist source is [MANUAL_UI_CHECKLIST.md](../MANUAL_UI_CHECKLIST.md); this report reflects automated checks, not a separate hotel-operator click-through.
