# Guest Sessions Intelligence

## Record boundaries

The administration view keeps four existing records distinct:

- `sessions` are Concierge application sessions. Guest access expires when the guest credential expires or is revoked. Conversation state and message counts are shown only to staff with `conversations.view`.
- `guest_sessions` are WLAN or integration associations. Unlinking removes this association only; it does not delete the app session, stay, or device record.
- `concierge_stays` are temporary property-scoped guest stays. They remain active until staff check them out. The configured retention period begins at checkout.
- `device_identities` contain property-scoped HMAC pseudonyms. The raw WLAN MAC is used only for server-side conversion and is not returned by the administration APIs. Device IDs are masked in staff views.

## Guest 360 and access

The Guest 360 endpoint loads a stay with a `property_id` and `stay_id` predicate. It returns linked WLAN visits, sanitized service request fields, and conversation lifecycle summaries without message bodies. Request details require `requests.view`; conversation metadata requires `conversations.view`; staff notes and link/session mutation controls require `guest_sessions.manage`. External PMS and gateway references are masked unless the principal has `integrations.view`.

The directory continues to use bounded, property-scoped server pagination. The Link Device drawer calls the existing reconnect workflow. Reconnect validates any supplied Concierge session against the selected property and refuses to associate an already-linked active session with a different device. Expiration revokes only that session's guest credentials. Checkout uses the existing privacy cleanup and retention workflow.

## Known integration limits

- PMS data is not looked up or synchronized here. The existing stay record stores the room and PMS guest reference supplied by an authorized operator or integration; the UI does not claim these values were verified against a PMS.
- WLAN association `last_seen_at` is initialized when the link is created. This admin path does not receive live access point heartbeats to refresh it. Concierge app activity uses the app session's own `last_seen_at`; these timestamps are presented separately in Guest 360.
- Device count represents the explicit device identity associated with the stay. It is not a count of concurrently connected radios or physical occupants.

## Verification

Backend tests exercise property boundaries, note and conversation redaction, safe request summaries, raw-MAC non-disclosure, cross-property session rejection, prevention of session relinking to a different active device, unlink preservation, and guest-credential expiration. Playwright covers the directory and both drawers at desktop, tablet, and mobile widths using an isolated test server and test property.
