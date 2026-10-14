# Guest concierge design and evidence contract

- **Purpose:** let an in-house guest quickly ask the hotel concierge for verified information or request a configured service.
- **Audience:** guests using a shared phone, tablet, or desktop browser during a stay.
- **Tone:** calm, warm, and premium; useful conversation comes before hotel marketing content.
- **Memorable detail:** short category chips make dining, facilities, nearby discovery, and room requests one tap away while the composer stays attached to the conversation.
- **Hierarchy:** hotel identity; compact welcome; contextual prompt chips; readable conversation and verified cards; persistent, labeled composer.
- **Reference observation:** the local classic guest page showed a large static welcome, quick action tiles, empty highlights, and a failed greeting response inside a chat card. The redesign promotes the already implemented structured chat surface and keeps hotel facts grounded in current property records.
- **Responsive targets:** `390x844` mobile, `768x1024` tablet, and `1440x900` desktop.
- **Data and action constraints:** only guest-visible, property-scoped content may appear; request status is scoped to the active guest session and linked active stay; service requests require backend confirmation; indoor paths use configured guest-visible nodes and edges only.
- **Accessibility constraints:** labeled composer, keyboard send, visible focus, semantic headings and lists, minimum 44 px prompt/action targets, reduced-motion support, and responsive text wrapping.

## State contract

| State | Trigger | Visible feedback | Safe next action |
| --- | --- | --- | --- |
| Loading | Concierge checks a submitted message | Status text, progress indicator, and Stop response control | Wait or stop |
| Empty | No linked guest service request exists | Says no linked request is available yet | Describe a need to see configured services |
| Error | Request or response fails | Bounded error text and retry guidance | Retry or start a private chat |
| Partial | Map exists without a known starting point, or a hotel record is unpublished | Only available markers are shown; missing route/data is stated | Provide a known origin or contact the Front Desk |
| Success | Backend confirms a service request | Confirmation followed by its current request status | Ask for another service or track the request |
| Permission | Guest session expires or property interface is unavailable | Session or property access message | Start a new chat or contact hotel staff |
