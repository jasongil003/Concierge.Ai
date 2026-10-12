# Concierge.AI ECC Audit — Executive Summary

**Assessment date:** 2026-10-12

**Scope:** current working tree at `fbf9d50635c427f5340098cac48e7bb8eb7ef7a2`, including pre-existing local changes. This was a read-only audit of application files; only this report set was added.
**Deployment verdict:** **INTERNAL DEMO ONLY**

## Summary

The reported guest-session sliding-expiry race is fixed in the current checkout and passes deterministic regression tests. A credential valid when authenticated may finish an already-authorized request across its expiry boundary; renewal remains bounded to one configured guest TTL, checks current credential hashes and revocation state transactionally, and sets the response cookie only after the server-side expiry update succeeds. A credential already expired at authentication is rejected. No current Critical or High security finding was confirmed in the reviewed code and local test evidence.

The application’s backend is functionally stable for the exercised local flows: the full backend suite passed, the non-visual Playwright suite completed with 265 passed and 35 skipped, static checks passed, and dependency audits found no advisories. See [test evidence](ECC_TEST_EVIDENCE.md). Those results do not certify production readiness. PostgreSQL/Redis integration cases are skipped locally, a Python 3.12 runtime was unavailable, the live GitHub remote could not be reached, and no clean appliance, hotel-network, external gateway, reboot/update rollback, or off-host restore acceptance was performed.

The intelligent guest UI work is present in uncommitted working-tree changes. Its structured response schema, two-key feature gate, existing authenticated chat path, property-scoped cards, inert text rendering, and explicit confirmation workflow provide a sound prototype boundary. It has no SSE streaming implementation; global emergency disable requires a process restart; and this UI branch has not been promoted through a clean release/CI and target-appliance acceptance cycle.

## Direct answers

1. **Is guest session expiry fixed?** Yes, in the current checkout. The original race and the fix are reviewed in [session expiry review](ECC_SESSION_EXPIRY_REVIEW.md); deterministic boundary, repeated-slide, expired-token, revoked-token, and cookie assertions pass locally.
2. **Any open Critical or High findings?** None confirmed. Historical `ECC-SES-001` is `FIXED-VERIFIED`. This is not a claim that every external environment or unrun integration is secure.
3. **Is the existing backend stable?** Stable for the tested local SQLite/application flows. Production stability across PostgreSQL, Redis, real providers, target hardware, and operating-system lifecycle remains unverified.
4. **Can it support Intelligent UI 2.0?** It supports a safe, non-streaming structured prototype. SSE, operational rollback, shared-device transcript handling, and end-to-end response quality need further work.
5. **Internal demo, pilot, or production?** Internal demo only, using synthetic data and an isolated environment. The controlled pilot checklist and production acceptance are not complete.
6. **What should Codex do next?** Complete the prioritized work in [remediation plan](ECC_REMEDIATION_PLAN.md): run the verified release on a clean target with PostgreSQL/Redis as intended, finish appliance and recovery acceptance, validate PDF resource limits on each supported OS, automate guest-response quality checks, then review and release the Intelligent UI changes.

## Finding counts

No current Critical or High issue was confirmed. The previously reported High guest-session race is `FIXED-VERIFIED`. The remaining tracked items are one Medium control needing platform acceptance (`FILE-DOS-01`, `FIXED-UNVERIFIED`), one Medium deployment acceptance blocker (`ECC-OPS-001`, `BLOCKED`), and two Low Intelligent UI gaps (`ECC-UI-001`, `ECC-UI-002`, `OPEN`). A historical breakfast-answer report (`OPS-021`) is `FIXED-UNVERIFIED` pending an exact guest-facing regression assertion. These are documented with evidence and limits in the detailed reports.

## Baseline and limits

- Branch: `feature/intelligent-guest-ui-v2`; HEAD: `fbf9d50635c427f5340098cac48e7bb8eb7ef7a2`.
- Cached local `origin/main`, local `main`, and `origin/HEAD` point to this HEAD. Live remote freshness could not be checked because DNS/network access to GitHub failed.
- Existing modified and untracked application/UI/test files were present before this audit and have been preserved. No commit was created.
- Local Python was 3.11.16; CI declares Python 3.12. Cross-version behavior is therefore not independently established here.
- The persistent SQLite state fingerprint remained unchanged during backend pytest; browser state and browser artifacts were kept under `/private/tmp`.

See [final verdict](ECC_FINAL_VERDICT.md) for the complete evidence summary and caveats.
