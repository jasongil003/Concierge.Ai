# Property Location & Navigation Intelligence

## Capability audit

| Area | Current implementation | Remaining limitation |
| --- | --- | --- |
| Guest location directory | Property-scoped `app_settings.locations`; guest visibility is honored by guest serializers. The editor now validates paired coordinates and geographic bounds. | These lightweight records save directly to property settings and do not have their own draft/publish history. Indoor placement belongs in the map studio. |
| Floor plans and structures | Property-scoped buildings, floors, PNG/JPEG/SVG floor-plan uploads, zone geometry, map object editing, draft revisions, publish, and rollback are implemented. Upload checks validate file contents and dimensions. | No basemap/geocoding or automatic floor-plan digitization is provided. A map is only as accurate as the plan and coordinates supplied by the property. |
| Navigation | A deterministic weighted route graph supports explicit same-floor paths, elevator/stair/ramp transitions, bidirectional edges, and accessible-route filtering. Guest routes are limited to published, guest-visible map data. | No real-time indoor positioning. Guests must use a confirmed start point. WLAN association is not used as a precise starting location. Cross-building paths require separately verified route data. |
| Map readiness | The admin Zones API now reports missing floor plans/waypoints, missing route links, and disconnected guest route groups. The Location workspace surfaces these as review items. | Issues are advisory; a property can publish a partial map. No automatic route generation or external map-quality service exists. |
| Facilities | Structured hospitality facility profiles already support public descriptions, hours, status, images as URLs, and policies; a separate map facility record places facilities in a zone. The redesigned Location workspace links both to their existing editors. | Facility profile and map marker are separate records and are not automatically synchronized. Image uploads and department/service relationships are not supported by the facility profile model. |
| WLAN observations | The existing endpoint checks property, collection guardrail, authenticated session, active stay, guest location consent, property-scoped pseudonymous device identity, and mapped AP identifier before storing an observation. Checkout removes associated records. | The app does not poll or configure a WLAN controller from this screen. It exposes an API ingestion path, not a vendor connector, source health monitor, or credential setup workflow. AP identifiers must be mapped manually. |
| Analytics | A 15-minute summary deduplicates pseudonymous devices per property; historical reports provide observed zone visits, dwell, transitions, and property-local hourly device patterns. The UI labels these as devices, not people. | No person-count estimate, continuous occupancy measure, cleanup job health metric, or small-cohort suppression is implemented. Do not interpret a device as a person. |
| Authorization | Map and facility data are property-scoped. Aggregate report/live endpoints require `analytics.view`; raw observation ingestion now requires `guest_sessions.manage`. | Roles should grant map/facility viewing separately from analytics access. |

## Updated admin flow

The Location page is now a three-part workspace:

1. **Property Maps & Navigation** shows building/floor/waypoint/route counts, publication state, and route-readiness warnings, with a direct link to the existing map studio.
2. **Facilities & Locations** provides searchable generic guest locations and a live summary of structured facilities, with links to the existing Facilities and map editors. New location edits open a responsive drawer; legacy category labels remain editable.
3. **Occupancy & Movement Analytics** shows recent device observations and property-local historical reports only to users with `analytics.view`. Its explanatory copy distinguishes observed devices from people and describes the existing session/consent-gated ingestion path.

## Security and privacy notes

- Raw WLAN MAC values are pseudonymized server-side using a property-specific secret before storage; ordinary analytics responses contain no device identifiers.
- Observation ingestion verifies an authenticated session, active stay, linked device, AP mapping, property collection setting, and guest location consent.
- Checkout cleanup removes location and movement records linked to the stay.
- Property location coordinate writes now require valid latitude/longitude pairs and preserve existing free-text category values for legacy records.
- `POST /location/report` is governed by `analytics.view`; `POST /location/observations` is governed by `guest_sessions.manage`.

## Verification

Verification used an isolated Playwright app and synthetic property `Location Intelligence QA`; the fixture was deleted after each test.

- Location, permission-boundary, and property-setting regressions: **6 passed**.
- Routing safety, map revision, and floor-plan upload security: **44 passed**.
- Playwright desktop and mobile projects: **2 passed**. The desktop run also checked 768px tablet overflow and captured that viewport.
- `node --check`, route-policy JSON parsing, and `git diff --check`: passed.
- The persistent SQLite safeguard reported the configured database unchanged. Pytest emitted only existing Starlette/httpx deprecation warnings.
- Bandit (repository CI command): passed.
- `pip-audit -r requirements-dev.txt`: passed; no known vulnerable dependencies found.
- Gitleaks 8.24.3 (official macOS ARM binary; published SHA-256 verified): scan did not pass. It flagged one generic API-key candidate in the ignored local `.env` and 13 candidates in repository history. The secret values were not displayed. The local file is not tracked or part of this change; the historical findings still need repository-owner triage.

Screenshots are saved under `test-results/location-intelligence/`:

- `desktop.png` — 1440 × 1000
- `tablet.png` — 768 × 1024
- `mobile.png` — 390 CSS px wide (Pixel 7 emulation)

The synthetic property has one guest location and no configured floor map or WLAN observations, so the images show accurate setup and empty-data states rather than fabricated analytics.
