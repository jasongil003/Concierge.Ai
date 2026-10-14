# Concierge.Ai ECC executive summary

**Date:** 2026-10-14 (Asia/Manila)  
**Audited baseline:** `82f9df2bafb4b3a632912762364fd6c7dff4a532` on `codex/guest-concierge-premium-2026-10-13`. Audit fixes and reports are local and uncommitted.

## Decision

Concierge.Ai is suitable for **internal developer testing** and an **isolated synthetic hotel demo**. It is **not ready for an external hotel proof of concept or production**. Two high-priority blockers remain: a credential-bearing blob in reachable Git history whose revocation is unconfirmed, and an incomplete consent/retention/deletion lifecycle for guest location observations. Live hotel network, PMS/ANTlabs, physical-device, recovery, and capacity acceptance are also outstanding.

## What the audit found

The feature matrix records **44 major feature rows**: **13 implemented and locally verified**, **18 partially implemented**, **3 not implemented**, **4 blocked by external dependency**, and **6 unverified**. Those classifications apply to stated test behavior with synthetic data; a backend pass does not prove physical-device behavior or live property truth. The technical finding ledger records **five high**, **four medium**, and **one low** items; four findings were corrected locally. The high count includes two external acceptance gaps and one corrected backup defect, while the two unresolved security findings remain release blockers.

Local backend verification passed **1,187 tests with 18 environment/platform skips** after the fixes. The final functional browser run completed **332 passed, 38 project-specific skips, 0 failed** across desktop Chromium and Pixel 7 emulation. Focused chat-scroll and test-isolation browser regressions passed in both projects. Bandit reported no medium/high findings; offline npm audit found no cached advisories. Local Gitleaks was unavailable and pip-audit did not complete, so no clean secret/dependency conclusion is claimed. Prior GitHub CI did detect the known historical credential and failed closed.

## Local improvements

1. Corrected the legacy chat's scroll target and anchoring so a long new reply stays visible. Fresh 390×700 Chromium before/after captures and focused Chromium/Pixel 7 tests support the fix.
2. Prevented pytest and Playwright's synthetic server from loading repository `.env` values, with regression assertions.
3. Preserved an existing SQLite database if staged restore replacement fails, with a failure-injection test.
4. Corrected the management PDF's empty comparison-period wording, with missing and numeric cases.

## Next release actions

1. Credential issuer owner confirms invalidation/rotation; repository owner authorizes full-ref history cleanup and verifies a forced-text secret scan. Keep the finding visible until closure.
2. Property/privacy owner approves the location observation lifecycle; implement consent, opt-out, checkout behavior, retention, export, and deletion with multi-property negative tests before real collection.
3. Validate approved hotel content, restaurant opening status, map routes, service operations, and ANTlabs/PMS/WLAN handoff in an authorized staging environment on physical iOS/Android devices.
4. Correct property-local calendar windows in analytics and define trustworthy “open now” behavior before relying on those claims operationally.
5. Prove backup/key recovery, target-host install/upgrade, TLS/network controls, required remote CI gates, and a staged representative load/soak plan before production capacity claims.

Detailed evidence: `ECC_FULL_AUDIT.md`, `ECC_FEATURE_MATRIX.md`, `ECC_SECURITY_REPORT.md`, `ECC_GUEST_EXPERIENCE.md`, `ECC_RBAC_MATRIX.md`, `ECC_TEST_RESULTS.md`, `ECC_PERFORMANCE_REPORT.md`, `ECC_REMEDIATION_LOG.md`, and `ECC_RELEASE_READINESS.md` in this directory.
