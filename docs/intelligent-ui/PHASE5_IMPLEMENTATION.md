# Phase 5 implementation

## Candidate and change scope

Baseline: `6fd9d2309f28137a2ab3823ca99794656998b5d8`. Branch: `fix/intelligent-ui-v2-phase5-stabilization`. The source changes are uncommitted and limited to:

- `app/static/app.js`
- `tests/e2e/guest.spec.js`
- `tests/test_transcript_rotation.py`
- `tests/test_backup_restore.py`

The other Phase 5 files are evidence and operator-acceptance documents. There is no commit SHA for the working tree.

## `ECC-UI-006`: confirmed cause and repair

The browser trace showed this sequence: the guest expanded a restaurant recommendation while `/api/chat` was pending; the async response mutated the in-flight assistant message and called `renderMessages()`; `renderMessages()` cleared the message list and constructed new card DOM. The expanded state existed only in the old paragraph's `hidden` property, so the replacement card was collapsed and displayed `Details`. Git history confirms the triggering renderer change: commit `f22c0b2a` (2026-10-02) introduced clearing/rebuilding both message lists; the Details handler's DOM-only toggle dates to `7c520d56` (2026-09-21). The race reproduced intermittently on the mobile emulation path.

The repair keeps expanded recommendation keys on the assistant message object. Each response message receives a stable per-request ID; a recommendation result key uses its stable provider/place ID when present and otherwise uses name, address, map URL and index. Rendering derives paragraph visibility, button text, `aria-expanded`, and `aria-controls` from that state. Before replacement, rendering captures focus on a recommendation Details control and restores it to the matching control after rebuild with `preventScroll`. The click handler updates the message state and visible/accessibility state together.

The browser regression intentionally holds `/api/chat`, expands the saved recommendation, releases the response, then checks one card remains expanded, the control is named “Hide details,” `aria-expanded` is true, and focus survives. It then collapses and expands again. Existing UI test assertions now check both states. The test always releases the held response in `finally`.

Pre-fix controlled runs failed 4 of 24 times. After the repair, the focused toggle and async-rerender tests passed 32 of 32 runs across desktop Chromium and Pixel 7 emulation. The full-suite Phase 5 outcome is in [test results](../audits/ECC_PHASE5_TEST_RESULTS.md).

## Additional failure-mode regressions

- `tests/test_transcript_rotation.py`: a corrupted ciphertext makes inventory report an unreadable row. Rotation fails before writes; a before/after fingerprint proves the database content is unchanged.
- `tests/test_backup_restore.py`: a ZIP with a manifest but missing its declared database member is rejected before restore targets are created.
- Existing rotation tests cover missing/wrong keys, batch interruption/resume, transaction write failure/rollback, read compatibility and old-format rollback, concurrent new writes, property scope and idempotence. Existing backup tests cover verified SQLite restore into a separate destination and preservation of the source. These are local temporary fixtures, not actual key escrow or a pilot backup.

## Security impact

These changes do not modify server-side guest authorization, session expiry/revocation, RBAC, property scoping, signed service-action confirmation, provider routing, feature-flag defaults, cryptographic key material or persistent application data. Recommendation expansion is view state only. Rotation/restore regressions assert fail-closed behavior; they do not weaken key or archive checks.

## Reproduction

```sh
npm run test:e2e -- --grep 'guest: restaurant card details button toggles verified details|guest: expanded restaurant details survive a chat response rerender' --repeat-each=8 --reporter=list
.venv/bin/pytest -q tests/test_transcript_rotation.py tests/test_backup_restore.py
/tmp/phase5-venv/bin/python -m pytest -q tests/test_transcript_rotation.py tests/test_backup_restore.py
```

The full Python/browser commands and outcomes are recorded in [Phase 5 test results](../audits/ECC_PHASE5_TEST_RESULTS.md). No commit, push, merge, provider request, production rotation, or deployment occurred.
