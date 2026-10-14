# Remediation summary

**Starting HEAD:** `e4bbd7493fe9d90a513d8224749b54c9e25ddc90`
**Implementation and tested commit:** `a30f95eb8db2ff05151c3473e453f9f38d0dec2d`
**Earlier audit code baseline:** `d5d006e89c38c0d901256d545679fee753175ef8`
**Date:** 2026-10-14 (Asia/Manila)
**Changes:** implementation and tests are committed locally; this report update is documentation-only. No push or deployment was made.

## Changes made

| Area | Change | Evidence |
|---|---|---|
| Restaurant follow-up context | Resolve a uniquely named or cuisine-matched restaurant from recent guest turns. Ask the guest to clarify when the previous turn matches multiple restaurants. Show only that restaurant's published menu items and provide its published location with an explicit no-indoor-routing message when no route exists. | `app/main.py`; `tests/test_intelligent_ui.py::test_restaurant_menu_and_location_followups_keep_the_unique_property_selection` covers “I'm hungry” → Japanese food → menu → location with two synthetic restaurants. |
| Service request idempotency | Serialize the idempotency lookup, service validation and request insert in one SQLite write transaction so concurrent retries return the existing ticket instead of racing into a uniqueness error. | `app/hospitality.py`; 8-thread duplicate submission regression in `tests/test_service_catalog.py`; same proposal replay regression in `tests/test_guest_personal_home.py`. |
| Guest shell | Add an explicit first-party SVG favicon link to the active intelligent guest shell. | `app/guest_v2/index.html`; active-shell response check in `tests/e2e/guest-premium.spec.js`. |
| Playwright fixture isolation | Remove demo map facility profiles after the indoor-map test; assert no HTTP 404 responses in the responsive matrix. | `tests/e2e/guest.spec.js`, `tests/e2e/manual-qa-responsive.spec.js`; full Playwright suite now passes. |
| Audit reports | Updated the eight `docs/audit/*.md` reports with this working-tree test run, the corrected 404 diagnosis, and remaining external gates. | Test and deployment limits are recorded in the linked reports. |

## Verification

- Backend: **1,182 passed, 18 skipped, 0 failed**.
- Playwright: **334 passed, 38 skipped, 0 failed** across Chromium and Pixel 7 emulation; all nine responsive viewports passed in Chromium.
- `npm audit --offline --json`: zero advisories across 3 lockfile dependency entries.
- Bandit: zero High findings and two reviewed Medium B608 SQL-construction alerts for fixed identifiers with bound values.
- Python dependency audit was blocked by unavailable package-network access. The remote `main` refresh was also blocked because DNS could not resolve `github.com`.

## Remaining release position

This work verifies local behavior against synthetic property data. It does not establish hotel-pilot or production readiness. The open gates include the historical credential exposure and authorized history cleanup, an approved location-privacy lifecycle, live SG5/PMS/WLAN acceptance, owner-approved hotel content and geometry, live-provider approval and quality checks, target-host recovery, and progressive capacity testing. See `RELEASE_BLOCKERS.md` for closure criteria.

The historical execution credential is not reproduced in this report; its issuer/audience could not be determined from the sanitized evidence. No credential was rotated, Git history was not rewritten, and no production data, deployment setting, gateway, provider, user account, repository policy, or remote ref was changed.
