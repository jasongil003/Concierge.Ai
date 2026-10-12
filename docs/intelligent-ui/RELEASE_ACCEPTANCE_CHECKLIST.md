# Release acceptance checklist

Local checks below were run on the uncommitted worktree based on `2915974fceae9bf3ea46195254f52392968a0667`; repeat them on the exact candidate commit after one is created. Keep the final verdict at **WORKING LOCAL PROTOTYPE** until every required target item has recorded evidence.

## Local evidence

- [x] Full `.venv/bin/pytest -q` passes: 1091 passed, 17 skipped, 0 failed, 2 warnings; skips and warnings are recorded.
- [x] Full Playwright suite passes in desktop Chromium and mobile Chrome emulation: 277 passed, 35 skipped, 0 failed.
- [x] Python compilation, JavaScript syntax, CI Bandit, and `git diff --check` pass.
- [x] Additive facility metadata migration preserves rows and old positional inserts.
- [x] Guest expiry/revocation, encrypted history, property isolation, signed action confirmation, and feature-flag rollback regressions pass.
- [x] Typed selections validate, review, edit, cancel without sending, and require a share action; no booking is claimed.
- [x] The legacy guest interface displays configured facility metadata.
- [x] Persistent database checksum is unchanged by isolated tests.

## Target acceptance (not evidenced locally)

- [ ] Python 3.12 and every supported host OS pass the security suite.
- [ ] PostgreSQL migration and backup/restore pass on a disposable database; Redis distributed limit tests pass on a disposable service.
- [ ] Clean install, upgrade, service restart/shutdown, encryption-key recovery, and rollback pass on the target appliance.
- [ ] Reverse proxy preserves SSE events, disables buffering, meets idle timeouts, and propagates disconnect cancellation.
- [ ] TLS, allowed host, guest captive portal, and management-network controls pass on the target deployment.
- [ ] A live AI benchmark is run with authorized credentials and synthetic data, or remains explicitly `NOT RUN`.
- [ ] WCAG 2.2 AA scan, keyboard/screen-reader checks, Safari, and physical-device checks are complete.
- [ ] Dependency audit, secret scan, and image scan pass on the exact candidate commit.
- [ ] An operator records go/no-go and the tested rollback result.

Do not use production guest data for acceptance. The implementation and limitations are summarized in [Phase 3 implementation](PHASE3_IMPLEMENTATION.md); target recovery steps are in [Operations rollback runbook](OPERATIONS_ROLLBACK_RUNBOOK.md).
