# Phase 3 implementation

## Typed guest selections

The versioned `selection_form` protocol now accepts either legacy options or one to six typed fields: date, time, quantity, party size, and configured service options. Pydantic validates field IDs, required flags, ranges, option values, and unique identifiers. The client uses native controls and provides required-field validation, a review screen, edit, cancel, and explicit **Share with concierge** confirmation. Cancel clears the form without sending. Sharing creates one idempotent chat turn and does not call booking or service mutation APIs.

No reservation-slot provider is configured. Date, time, party size, and service preference are collected only for discussion; the interface states that this does not create a booking or service request. No availability or booking success is invented.

## Facility metadata

Facility location and policies live in an additive `facility_metadata` table joined with both `facility_id` and `property_id`. The existing `facility_profiles` table layout stays unchanged, so old positional inserts still work after the upgrade. Hours and image fields remain on their established table. Store-level validation bounds location, hours, image count and URLs, and policy count and lengths.

The Admin Facilities editor can edit location, hours, up to 12 HTTPS/same-origin images, up to 8 guest policies, and a status note. The legacy guest Explore cards and Pure Intelligent UI cards display only configured location, hours, imagery, and policies. Status notes remain status details and are not substituted for a missing location. Existing property-scoped floor maps and their accessible marker list/fallback remain unchanged. No booking actions were added.

## Evidence

- Backend tests cover schema compatibility, legacy positional insertion, property isolation, typed schemas, and safe facility URLs.
- Playwright covers typed review/edit/cancel/share and facility editing/legacy guest rendering in desktop Chromium and mobile Chrome emulation.
- Form screenshots: [selection form](screenshots/selection-form-chromium.png) and [review state](screenshots/selection-review-chromium.png).
- Exact command outcomes are recorded in [ECC Phase 3 test results](../audits/ECC_PHASE3_TEST_RESULTS.md).

All screen captures are desktop Chromium browser output. Mobile Chrome is emulated; no physical iOS/Android or Safari test is claimed.
