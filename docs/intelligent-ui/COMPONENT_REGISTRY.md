# Intelligent UI component registry

Protocol schemas are strict Pydantic models in `app/intelligent_ui.py` (`extra="forbid"`). The browser uses allowlisted DOM construction and `textContent`; it never inserts model text as HTML. Blocks are versioned as schema `1.0`, bounded in count and size, and validated again when restored from server history.

| Component | Current behavior | Data/action boundary |
| --- | --- | --- |
| `text` | Bounded plain text. | No HTML or executable fields. |
| `suggestion_chips` | Sends a bounded follow-up prompt. | A prompt is not an action authorization. |
| `entity_card` / `card_collection` | Restaurant and facility cards with approved image, description, hours, location, and published data. | Data is loaded from the authenticated property's stores. Reservation link appears only when configured; no availability slots are invented. |
| `details_panel` | Label/value facts. | Server-authored text only. |
| `selection_form` | Presents safe choices that submit a new text turn. | It is not a typed booking form and cannot itself mutate state. A typed date/time/party-size booking flow remains unsupported until a real backend integration exists. |
| `request_review` | Shows the configured service, description, department, and a signed confirmation token. | Explicit confirm/cancel UI; backend rechecks token, guest/session/property, service availability, and idempotency before mutation. |
| `verified_confirmation` | Shows only a backend-verified result. | The model cannot generate successful action state. |
| `map_view` | Displays the property's stored floor plan with interactive location markers, image alt text, selectable marker labels, and a text alternative. | Map and guest-visible nodes come from the current property's `ZoneStore`; coordinates are checked against image dimensions. Missing data produces a Front Desk fallback. No directions from the guest's room are fabricated. |
| `loading_state` / `error_state` | Safe progress/failure display. | Retry only follows the server's retryable flag and reuses the turn ID. |

Restaurant cards can lazily load published menu items from the property-scoped guest menu endpoint. Images and reservation destinations are constrained to HTTPS or same-origin paths by the schema and client. Restaurant reservations remain links to configured external systems; this application does not claim a reservation is made.

Facility cards use saved facility profiles and guest-visible zone/floor/building labels. The current facility profile schema has descriptions and status notes but no structured policies field; the UI does not invent policy copy or booking actions.

Forms with typed date/time/quantity validation and verified reservation/service scheduling are still a product/integration gap. A map image with no guest-visible markers is not represented as an interactive map.
