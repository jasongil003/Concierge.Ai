# Phase 5 release checklist

## Local candidate

- [x] Dedicated branch `fix/intelligent-ui-v2-phase5-stabilization` created from baseline `6fd9d2309f28137a2ab3823ca99794656998b5d8`.
- [x] Details toggle race reproduced from Playwright trace and corrected; no acceptance assertion was weakened.
- [x] Repeated desktop and mobile-emulation tests verify accessibility state and response rerender focus.
- [x] Python 3.11 and isolated Python 3.12 full suites run; final counts are in [test results](../audits/ECC_PHASE5_TEST_RESULTS.md).
- [x] Transcript corrupt-ciphertext and incomplete-archive fail-closed regressions added.
- [x] Bandit run at CI medium/medium threshold passed; compile checks passed.
- [ ] Final `git diff --check` after all evidence documents.
- [x] Full Playwright result recorded: 279 passed, 35 skipped, 0 failed.
- [x] Python 3.11 and 3.12 results recorded: each 1,100 passed, 18 skipped, 0 failed. The initial concurrent Python 3.11 run's isolated PDF timeout is documented with its passing sequential rerun.
- [x] npm audit (zero vulnerabilities) and pip-audit (no known vulnerabilities) completed.
- [ ] Candidate source and documents reviewed by the repository owner.

## External pilot gates — all remain open

- [ ] Query latest GitHub commit and required Actions checks for the exact candidate revision.
- [ ] Run disposable PostgreSQL 16 / Redis 7 acceptance, migrations, concurrency, restart and recovery.
- [ ] Run authorized live 100-case AI benchmark using synthetic data and a disposable non-production credential.
- [ ] Run target reverse-proxy SSE buffering, timeout, disconnect and concurrency acceptance.
- [ ] Restore a disposable backup with keys recovered independently from test escrow; verify integrity and transcripts.
- [ ] Complete clean install, upgrade, service restart, health checks, flag rollback, legacy UI fallback and application rollback on target appliance.
- [ ] Verify PDF OS/container hard limits and worker recovery on every target platform; retain macOS limitation.
- [ ] Complete physical iPhone/iPad/Android/Safari/tablet/captive-browser and assistive-technology review.
- [ ] Define pilot SLOs and complete bounded load tests on representative target hardware.
- [ ] Obtain operational owner approval for data handling, credentials, rollout/rollback, monitoring, and incident response.

This checklist does not authorize a commit, push, merge, production key rotation, external provider call, or deployment. The current verdict is **WORKING LOCAL PROTOTYPE**; do not promote to a controlled pilot based on local evidence alone.
