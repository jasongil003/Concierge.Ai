# Intelligent UI SSE protocol

## Endpoint and lifecycle

`POST /api/guest/intelligent-chat/stream` returns `text/event-stream`. A request includes the current session ID, a bounded user message, and a stable client-generated `turn_id`. Authentication, property resolution, feature gating, rate accounting, turn idempotency, and property history checks run before model access.

Each event has an SSE `id` of `<turn_id>:<sequence>` and a JSON payload. Sequence starts at 1 and increases once per event. Heartbeats are SSE comments every 15 seconds while work is pending.

| Event | Payload | Meaning |
| --- | --- | --- |
| `turn.started` | schema version, conversation ID, turn ID | Authenticated turn accepted. |
| `text.delta` | safe text | Incremental validated text from a native provider. |
| `action.pending` | validated `request_review` block | A configured action proposal awaits guest confirmation. |
| `component.ready` | validated presentation block | Server-authored or validated data component is ready. |
| `text.completed` | `streamed`, final text when non-streaming | Text part is complete. |
| `turn.completed` | complete protocol response | Final response is validated and persisted. |
| `turn.failed` | safe message and retryable flag | Work failed or stream was interrupted. |

The frontend rejects malformed events, duplicate/out-of-order sequence IDs, mismatched turn/conversation IDs, unknown component payloads, and invalid final response schemas. The client retains the same `turn_id` when retrying the same pending message; the server returns the encrypted completed result or rejects a payload mismatch.

## Provider, bounds, and cancellation

Provider adapters consume native SSE/stream formats; they do not simulate streaming by splitting a completed answer. The response ceiling is 6,000 characters, matching the `TextBlock` schema. Provider calls are bounded by the configured timeout capped at 120 seconds, use the provider bulkhead, and close their async iterator on cancellation. The server queue is bounded to 24 items. Output validation withholds a short tail to catch sensitive or unverified-transaction patterns before release.

Retries/fallbacks may run before any text is sent. Once text has been delivered, an interruption emits `turn.failed` and does not start another provider. Browser cancellation uses `AbortController`; backend cancellation closes the provider stream and releases local/distributed capacity. The client can retry with the same turn ID. A completed turn is not submitted twice.

Non-streaming adapters send a truthful complete `turn.completed` response without `text.delta`. There is no automatic replay after a partial response. Browser reconnect/replay across a new TCP connection is not implemented; the guest retries the turn via the same idempotency key.

## Security properties

- Session cookie and current property are revalidated before each request; client history is ignored.
- Model output can only create schema-validated display data. The stream protocol has no executable tool/function event.
- `action.pending` is display-only. A separate confirmation endpoint validates the signed token, current session, property, and request idempotency.
- Stream failures return safe text and do not serialize provider exceptions or credentials.
- Full provider end-to-end streaming against live credentials, slow-network browser interruption, and proxy buffering have not been verified in a deployment environment.
