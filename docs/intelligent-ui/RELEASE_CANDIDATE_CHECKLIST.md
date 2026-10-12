# Release candidate checklist

## Local implementation evidence

- [x] Dedicated Phase 4 branch starts at reviewed merge `712316989e7baa8dc6b8946ca7192cfa2b22802c`.
- [x] Transcript format/key-ring implementation preserves the pre-ring format until staged configuration is explicit.
- [x] Rotation is operator-invoked, bounded, transactional, resumable, verified, and reversible before key retirement.
- [x] Synthetic SQLite tests cover legacy/mixed keys, key recovery fixture, write failure, interruption/resume, idempotency, concurrent sessions, property scope, and rollback.
- [x] PDF processing has existing upload/archive/page/text/wall-clock bounds; Linux resource limits are configured in the isolated worker.
- [x] No production database, real guest data, provider, or infrastructure was changed.

## Must pass before controlled pilot review

- [x] Full backend and Playwright suite on the candidate SHA with exact pass/fail/skip counts recorded in `docs/audits/ECC_PHASE4_TEST_RESULTS.md`; the first browser run had one unreproduced mobile toggle failure, and the retry-enabled complete run passed.
- [ ] CI-equivalent Bandit, JavaScript syntax, dependency audit, secret scan, and container scan, with unavailable tools called out.
- [ ] Linux hard memory/CPU enforcement and target OS worker cleanup acceptance.
- [ ] Disposable PostgreSQL/Redis migration, isolation, expiry, backup/restore, and failure recovery acceptance.
- [ ] Real-provider 100-case benchmark using explicitly authorized synthetic-only test credentials.
- [ ] Reverse-proxy SSE acceptance with first-event timing, cancellation, disconnect, timeout, and concurrent guests.
- [ ] Off-host encryption-key escrow retrieval and empty-target backup restore rehearsal.
- [ ] Pilot hardware capacity/SLO measurements and target deployment rollback.
- [ ] Physical iOS/Android, Safari/captive portal, and screen-reader acceptance; automated browser coverage alone is insufficient.

## Release gate

Phase 4 local completion is not production or controlled-pilot approval. The final verdict remains **WORKING LOCAL PROTOTYPE** until the blocked staging and target-environment items above have reproducible evidence and a separate release owner approves the pilot.
