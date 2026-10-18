# Notification & Communication Center audit

Reviewed the campaign routes, notification store, in-app dispatch worker, property/guest preferences, startup worker loop, route policy, and existing backend and browser tests. This document distinguishes campaign capabilities from the broader event-driven guest inbox.

## Confirmed behavior

| Area | Current implementation | Notification Center behavior |
|---|---|---|
| Campaign records | Campaigns are `notification_rules` rows scoped by `property_id`, category `promotional`, and trigger `campaign`. Draft/publish state and revision live in the policy JSON. | List, search, status filters, status counts, and message counts remain property-scoped. |
| Campaign status | `draft`, `publishing`, `published`, and `failed` are represented. Publication stores queued, already-queued, and suppressed totals. There is no campaign scheduling or campaign-expiry status. | Scheduled is shown as unavailable. Expiry is reported as expired guest inbox messages, distinct from campaign status. |
| Source reference | Campaign creation requires a non-empty source/approval reference, but the API does not verify it against an operations system or approval record. | The drawer says the reference is stored for context and is not independently validated. |
| Ownership/history | Previously campaigns had no creator or editor metadata, and there is no lifecycle event log or approval record. New campaign writes now retain the creator display name; old campaigns remain “owner not recorded.” | The queue shows creator when recorded, revision, update time, and current status. It does not imply an approval chain or edit history. |
| Authorization | Campaign list uses `properties.view`; create, edit, preview, and publish use `properties.edit`. `_require_property` and store queries scope by the selected property. | The UI keeps property context and only receives aggregate audience counts. |
| Promotional eligibility | Preview and publish require an active stay, active sessions linked to that stay, consent from every active linked session, and the stay’s promotional preference. Publishing rechecks eligibility; inbox insertion is idempotent and transactionally checks the linked consent state. | The audience is fixed to eligible active stays. No identities or segmentation are shown. |
| Withdrawal and dispatch | The dispatcher rechecks active stay and promotional consent/preference; consent withdrawal purges optional promotional inbox content. Checkout expires pending/visible notices and retention cleanup removes guest-linked records. | The UI explains that eligibility is rechecked and queueing is not receipt. |
| Delivery evidence | The in-app worker records queued, sent, delivered, read, failed, and expired. “Sent” is worker handoff; delivered is a guest-client acknowledgement; read is an explicit client action. | Aggregate counts describe only promotional campaign inbox messages. No guest IDs, bodies, or failure details are surfaced in these metrics. |
| Retry and scheduling | Guest inbox dispatch supports due times, quiet/send windows, leased claims, bounded retry/backoff, idempotency, and dead letters. The app worker polls every 10 seconds when background workers are enabled. | Campaign publishing queues immediately; it does not offer a scheduled campaign date. Generic retry support is not presented as a campaign retry control. |
| Expiry | Campaign notices are queued with a seven-day expiry. Inbox entries may expire sooner due to stay checkout, consent withdrawal, or retention policy. | “Expired notices” is an aggregate delivery-state count, not a campaign lifecycle state. |
| Communication classes | Supported notification categories are `operational`, `assistance`, `experience`, and `promotional`; there is no `transactional` category. Campaign creation is promotional only. Operational service/facility updates and configured hotel event reminders are event-triggered. | The page explains these paths separately and does not add a category selector that could bypass consent rules. |
| Channels | The current campaign API queues to the guest in-app inbox. No email or push campaign transport is connected. | Only in-app publishing is available; unavailable channels are stated plainly. |

## Gaps not represented as working features

- No scheduled campaign creation, campaign cancellation, or scheduled-campaign queue.
- No campaign-level approval workflow, immutable publication/event history, editor attribution, or staff assignment. Creator attribution is recorded for new drafts only; legacy creator data is absent.
- Source/approval references are required as staff-provided text but are not validated against an external record.
- No transactional campaign type. Operational and other system notices use separate event-driven code paths and policies.
- Service request status changes and supported facility changes can generate operational notices; request creation and assignment do not currently have equivalent guest inbox hooks.
- No email or push delivery provider for campaigns.
- No supported campaign audience segmentation; only an aggregate preview of the fixed eligible active-stay audience exists.
- The existing property delivery-history API includes stay identifiers and detailed per-record information. This dashboard does not call it or expose those records; its delivery health metrics are aggregated directly at the store layer.
- Campaign status `published` means publication completed and eligible messages were queued or already existed. It does not mean all notices were delivered or read.

## Verification boundary

Automated tests use the isolated test database and synthetic stays. Browser campaign creation/publishing checks mock campaign endpoints and do not enqueue notices for real guests. Responsive screenshots are captured from the isolated Playwright app. Security verification results are reported separately after running the relevant checks.
