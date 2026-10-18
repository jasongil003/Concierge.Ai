# Personalization Control Center audit

## Scope

The control center manages property policy. Guest consent and stored preferences remain guest/session scoped. This page displays aggregate operational counts only; it never lists guest names, session IDs, preference values, or raw provider credentials.

## Verified behavior

| Area | Current implementation | Control center behavior |
| --- | --- | --- |
| Privacy levels | Private, Stay, and Personal Concierge are supported. A property default suggests the initial guest choice and does not opt a guest in. | Explains the distinction and shows the saved default. |
| Consent | Location, proactive notifications, promotions, and external processing are separate, property/session-scoped choices. Optional choices default off, can be withdrawn, and have expiry. Location consent is tied to an active stay. | Shows aggregate granted/declined consent records inside their expiry window; calls them records, not unique guests. Includes a static copy of the guest choices. |
| Preference memory | Only eligible categories can be stored; writes require guest opt-in. Private mode returns no saved preference values. Sensitive identity/health/political/religious material is rejected by the preference-value filter. | Shows supported category names and aggregate counts without exposing saved values. |
| Personal Concierge | Profile-style preferences are available only when property policy allows them and the guest chooses Personal Concierge. Current profile keys are still scoped to the concierge session; there is no cross-stay guest identity profile. | Describes the session scope and does not imply persistent identity resolution. |
| Retention | Configurable idle expiry is 1–365 days. Active stay-linked preference records are retained until checkout. Checkout always removes privacy consent/location records; preference deletion follows the saved `delete_profile_at_checkout` policy. Expired records are also removed by cleanup and chat-time cleanup. | Shows property policy, aggregate due/expired counts, and labels per-property cleanup job history as not tracked. |
| Hotel recommendations | Published, property-managed recommendations are a separate source. | Shows enabled hotel-managed recommendation count. |
| Nearby recommendations | Google Places requires configured coordinates, a provider credential, relevant guardrails, property recommendation flags, and the guest's separate external-data consent. Credential validity is checked only during an eligible guest search. | Shows readiness prerequisites without revealing the key and avoids claiming live provider health. The location-aware property flag is enforced before search. |
| PMS | No reservation synchronization provider is implemented. PMS login is a Wi-Fi authentication option. The `allow_pms_personalization` policy only gates verified linked-room context on a confirmed service request. | Names the partial room-context behavior and labels reservation sync unavailable. |
| Access and isolation | Personalization policy endpoints use `properties.view` for reads and `properties.edit` for writes. Store queries include the property ID. | New diagnostics/history reads use the same property view permission. Policy updates use the edit permission and write a property-scoped audit event. |

## Changes in this implementation

- Reorganized the page into Overview, Privacy & memory, and Sources & integrations tabs.
- Added clear copy for property policy versus guest choice, all three memory levels, consent categories, expiry, and the partial PMS behavior.
- Added aggregate, property-scoped consent and memory diagnostics.
- Added prerequisite checks for property coordinates, provider configuration, policy switches, and relevant search guardrails. The guest's external-data choice remains a separate runtime requirement.
- Added safe administrative policy-change history for future changes. It includes the actor and changed policy values, not request IP addresses or guest data.
- Added strict policy field/type validation so unknown fields and string booleans cannot be saved.
- Added unsaved-change status, discard, navigation/property-switch confirmation, before-unload protection, and visible save errors.
- Added a static guest privacy-choice preview that does not read or modify a real guest session.
- Enforced the existing location-aware recommendation setting in the guest search path.

## Known gaps and truthful limits

- Cleanup last-success timestamps and failed-job counts are not stored per property. The interface reports “Not tracked”; it does not estimate these values.
- Provider reachability, credential validity, and live inventory are not probed from the admin page. Those can only be determined during an eligible guest search.
- A full PMS connector, reservation sync, and PMS personalization field matrix are not implemented.
- Policy history is read from the latest 500 administrative audit events and returns at most 20 matching policy changes. Older entries may no longer be present in that audit window. Existing changes from before policy audit events were added cannot be reconstructed.
- Consent totals are stored session records within expiry, not deduplicated guests or necessarily current active stays.
- Preference memory does not support a cross-stay identity profile. No guest-specific memory review tool is added to this aggregate page.

## Verification

The test suite covers guest opt-in and withdrawal, expiry and checkout behavior, property/session isolation, aggregate diagnostics redaction, policy validation, policy history, location recommendation gating, and route policy inventory. The Playwright control-center test verifies tabs, consent preview, unsaved/discard behavior, source capability labels, and desktop/tablet/mobile reflow. Generated screenshots are written under `test-results/personalization-control-center/`.
