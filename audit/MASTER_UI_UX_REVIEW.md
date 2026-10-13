# Master UI/UX review

- Date: 2026-10-12–13, Asia/Manila; baseline `41c0ea1a7937035db6078cbb944f1e94f2fbad63`.
- Final implementation commit and final browser totals: `MASTER_RELEASE_READINESS.md` and `MASTER_TEST_RESULTS.md`.
- Environment: macOS arm64, Chromium desktop and Pixel 7 emulation, isolated synthetic SQLite/Uvicorn. No physical iOS/Android/Safari/captive browser or screen reader acceptance.
- Commands: `npx playwright test --grep-invert @visual`, targeted privacy/scrollbar/responsive tests with `--trace=on`, and `npx playwright test --grep @visual`, then the complete `npx playwright test --workers=1` candidate run (283 PASS,35 SKIP,0 FAIL). Raw logs/screenshots/traces are in `audit/evidence/browser-2026-10-12`.

## Confirmed corrections

| Finding | Root cause | Correction and regression evidence |
| --- | --- | --- |
| Misleading privacy promises | Menu and static guest copy claimed chats stayed private/session-only while authorized staff can review persisted encrypted transcripts | Correct menu, welcome/header and restaurant dialog disclosures. `guest-privacy.spec.js` asserts staff access/retention; old menu assertion updated to accurate text. Original failing test/screenshot/trace retained |
| Home/chat alignment with classic scrollbars | Home reserved a scrollbar while chat had a different outer width/scrollbar policy; Linux baseline CI showed a 7.5 px left-edge drift, local forced-classic test showed 15 px width drift | Shared capped scroll-container track with stable gutters on both edges. `guest-scrollbar.spec.js` forces 15 px scrollbars through the same-origin stylesheet, preserving CSP and strict x/width comparisons. Before-fix failure and final PASS retained |
| Responsive test sampled unfinished navigation | Linux/mobile test called getComputedStyle on an absent navigation element | Await visible navigation/card/composer before measuring geometry. Original strict bounds/overlap expectations remain |
| Empty-state test teardown race | Absence assertions passed before route.fetch/json completed, disposing an in-flight response | Wait for hotel/home fixture responses and rendered hero before absence assertions; retain the disposed-response failure and later verification |
| Empty Quick actions heading | Configured quick-action renderer appended a heading/grid even after every action was filtered out | Return no section when configured actions plus supported runtime routes are empty. The stricter startup-ready regression failed in both projects before this correction; populated actions and route filtering remain covered |
| Historical screenshots overwritten by tests | Tests wrote current captures directly into earlier documentation evidence | Move guest evidence to per-test output paths and control inventory to current audit evidence; restore original historical captures byte-for-byte |

## Responsive and visible-control scope

Existing matrix exercises 42 admin destinations and five guest views at 320, 375, 390, 430, 768, 1024, 1280, 1440 and 1920 px, checking document/body overflow and console/request failures. Current home/chat and overview/appearance screenshots are retained at every width. The reviewer inspected the 320 px home, 1440 px chat and 1920 px dashboard captures: layouts remain usable, composer/navigation are contained, and synthetic dashboard metrics are labeled as current records/host samples. Empty chat space is the conversation area; it is not evidence that property content or every theme meets a luxury design brief.

Control inventory records **2,130 visible control instances**, **2,099 focusable controls**, zero enabled-but-unfocusable controls, zero missing accessible names and zero invalid composite widgets. This checks names/focus/entry points; it does not execute every control. Named browser workflows cover property onboarding, facilities CRUD/search, branding, draft/publish/discard, builder edits/history/rollback/reordering, knowledge source controls/upload, requests, restaurant staff handoff, reporting controls, and restricted-role UI/API paths. Unexercised combinations remain unverified in the matrix. No blanket WCAG or every-control acceptance is claimed.

## Remaining gaps and next actions

Physical keyboards/safe areas/QR/NFC/captive reopening, assistive technology, translated UI completeness, arbitrary property configurations, map precision/PDF backgrounds and every visible control combination remain separate acceptance work. Saved property-template cloning, pagination and notification scheduling are product gaps. Browser emulation and snapshot comparisons do not close these gaps.

Final suite results and every historical failure are recorded in `MASTER_TEST_RESULTS.md`. Production/pilot acceptance requires the target proxy/network/device environment as well as these local checks.

Final tested implementation commit: `ecfe3f42963896cd86a291450fa574a4c26b197f`. Reports/evidence are committed separately; their receipt is discoverable with `git log -1 -- audit/MASTER_UI_UX_REVIEW.md`. All test results refer to these unchanged committed implementation bytes, including explicitly scoped container receipts and local skips.
