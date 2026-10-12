# Intelligent UI conversation persistence

## Storage model

`SessionStore` remains the owner of the guest session and transcript. A new additive `guest_ui_turns` table stores `(property_id, session_id, turn_id)`, a keyed request digest, encrypted user message, encrypted response, status, and millisecond creation order. It does not accept an arbitrary conversation ID as an authorization selector.

New guest/assistant transcript content is Fernet-encrypted at rest with the existing credential encryption secret and a `fernet:v1:` prefix. Reads decrypt versioned content and continue to read older plaintext rows for backward compatibility. New turn messages and responses are encrypted independently; request digests are HMACed. Existing records are not discarded by the additive schema change.

The browser stores the active session selector and transient composer state, not an authorization transcript. It clears legacy transcript keys and restores history only from `GET /api/guest/intelligent-history`, after current session cookie, expiry, revocation, property, and feature checks. History is bounded to the latest 40 turns in the page; server retention follows the configured conversation retention and expired-session cleanup. A stale in-progress claim can be recovered after five minutes. Failed turns may be retried with the same turn ID; a completed turn replays its encrypted response, and a different request using that ID is rejected.

## Isolation and shared devices

- Every lookup includes the authenticated `session_id` and resolved `property_id`.
- Another session cannot request a history ID to read the first guest's turns.
- Revocation, session end, and expiry cleanup remove associated Intelligent UI turns.
- “New chat” calls `/api/session/end`, revokes the old guest credential, clears the browser transcript, and starts a new session.
- Turn IDs are not bearer credentials. The session cookie remains required.

## Retention and key operations

The turn table is cleaned with session deletion/expiry and transcript retention. No destructive bulk rewrite of the existing transcript is performed. Historical plaintext rows remain readable until their existing retention lifecycle removes them; deployments that require all historical data encrypted need a separately scheduled, backed-up migration. Losing or rotating the configured encryption secret without the approved recovery procedure makes encrypted messages unreadable; the application returns a safe unavailable marker rather than exposing ciphertext.

The schema is created additively by `SessionStore` initialization. Local SQLite tests exercise this path. PostgreSQL migration, backup, restore, key recovery, and multi-worker behavior require the unavailable external test services/target environment and remain blocked.
