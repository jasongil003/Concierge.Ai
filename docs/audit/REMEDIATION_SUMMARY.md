# Remediation summary

**Audit target:** `d5d006e89c38c0d901256d545679fee753175ef8`  
**Date:** 2026-10-14 (Asia/Manila)  
**Working tree:** local, uncommitted documentation and one small guest-shell asset fix.

## Changes made in this audit

| File | Change | Reason and verification |
|---|---|---|
| `app/static/index.html` | Added an explicit SVG favicon link. | The first full Playwright run reported the same 404 console error for `/explore` in all nine responsive matrix viewports when the guest SPA changed the URL. The unchanged nine tests passed after adding the icon. |
| `app/static/assets/favicon.svg` | Added a minimal first-party vector Concierge mark. | Removes the missing-icon request without adding a remote asset or copyrighted image. |
| `docs/audit/*.md` | Added the eight requested audit reports. | Captures evidence, test counts, blockers, unresolved security items, limitations, and the exact audited SHA. |

The audited commit itself (`d5d006e…`) already included fixes for local-demo production credentials, loopback-only local demo seeding, and property-media symlink escapes. Current-run regressions for those changes passed. Earlier audit work in this repository records fixes for knowledge publication authorization and the legacy dashboard permission projection; their regression tests also passed in the current complete backend suite.

## Test outcome

- Backend: **1,180 passed, 18 skipped, 0 failed**.
- Initial full Playwright run: **323 passed, 38 skipped, 9 failed**; all nine failures had one common missing-icon 404.
- Post-fix responsive regression run: **9 passed, 0 failed** across all nine declared viewports. The complete Playwright suite was not rerun after this narrow asset fix, so a fully green post-fix suite is not claimed.
- npm lockfile audit: zero advisories offline. Python package audit was blocked by unavailable package-network access. Bandit reported no High findings and two reviewed B608 Medium alerts for fixed SQL identifier fragments.

## Remaining release position

There is no evidence here to approve a hotel pilot or production release. The high-priority remaining gates are historical credential invalidation/history cleanup, property-approved location privacy and notification policies, real SG5/PMS/WLAN acceptance, approved hotel content/maps/photos, provider authorization and quality testing, target-host recovery, and progressive capacity testing. Details and closure criteria are in `RELEASE_BLOCKERS.md`.

No production data, deployment configuration, external provider, gateway, user account, Git history, or remote repository settings were changed. Remote `main` could not be refreshed in this network environment.
