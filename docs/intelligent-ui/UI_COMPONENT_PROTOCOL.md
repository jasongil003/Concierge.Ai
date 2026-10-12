# Intelligent UI component protocol

## Version 1.0 envelope

`app/intelligent_ui.py` defines the Pydantic server contract. Each response contains a fixed `schema_version`, opaque conversation ID, turn ID, and validated blocks with stable per-response block IDs.

```json
{
  "schema_version": "1.0",
  "conversation_id": "opaque-session-id",
  "turn_id": "opaque-turn-id",
  "blocks": [
    {"id": "text-…", "type": "text", "content": "Pool hours are listed as 6:00 AM to 10:00 PM."}
  ]
}
```

Every Pydantic block rejects unrecognized fields. The client checks the envelope and validates block shape again before rendering. Unknown or invalid blocks become a fixed, safe fallback sentence. The UI never evaluates response data.

## Supported block types

| Type | Validated data | Client behavior |
| --- | --- | --- |
| `text` | Bounded text | Plain text paragraph |
| `suggestion_chips` | Up to six bounded label/prompt pairs | Buttons submit their prompt as a normal guest message |
| `entity_card` | Restaurant/facility type and bounded text fields | Text-only card |
| `card_collection` | Bounded title and up to eight entity cards | Responsive card list |
| `details_panel` | Bounded title and up to twelve label/value pairs | Definition list |
| `selection_form` | Bounded labels and values | Choice buttons submit only the visible label as a guest message |
| `request_review` | Bounded summary and signed proposal token | Displays review; confirm calls the existing authorized action endpoint |
| `verified_confirmation` | Bounded confirmation text | Displayed only after a successful backend result |
| `map_view` | Title and bounded latitude/longitude | Coordinate text only; no remote map is loaded |
| `loading_state` | Bounded status message | Accessible progress text and local animation |
| `error_state` | Bounded message and strict boolean | Safe error panel |

The first live chat adapter emits text, suggestions, and property-scoped dining card collections. Service review/confirmation blocks are created from the existing proposal API response and then verified through the existing confirmation API. Other schemas are ready for deterministic server use but are not emitted by the current vertical slice.

## Trust rules

- AI output is only the `content` of a `text` block. It cannot select component types or supply a tool name, property/guest ID, route, URL, HTML, image origin, or executable code.
- Entity cards are assembled server-side from `hospitality.guest_facilities(current_property_id)`. Only names, cuisine, descriptions, location, and hours are copied. No IDs or URLs are sent to the renderer.
- Action authorization never comes from a model. The existing endpoint re-resolves the property and guest session, validates a signed proposal, checks action policy, and deduplicates the resulting request.
- The client uses DOM creation and `textContent`, not `innerHTML`.
- Components with remote resources are not currently supported. The brand logo is loaded only from the current origin.

## Compatibility behavior

`POST /api/chat` keeps its original response shape. `POST /api/guest/intelligent-chat` is additive and fails closed when the global or property flag is off. Schema construction errors fall back to one bounded text block. An unrecognized client block renders an inert fallback.
