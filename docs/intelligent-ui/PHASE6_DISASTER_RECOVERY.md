# Phase 6 Disaster-Recovery Acceptance

## Implementation present

The repository has application backup/restore support, PostgreSQL backup integration tests, transcript key versioning/rotation tools, and a key-recovery runbook. Backups do not contain the encryption keys needed to read encrypted content. The off-host escrow path must remain separate from the application host and must never put secret material in this document, source control, shell history, or ordinary logs.

## Phase 6 result: BLOCKED

No Linux container runtime, PostgreSQL service, off-host test escrow, or second disposable restore target was available. No Phase 6 database backup was created, no test key was deposited/recovered independently, and no restored guest transcript was read. Existing local backup/key-rotation tests and historical results are not represented as a completed operational recovery rehearsal.

## Required synthetic rehearsal

1. Start the isolated Phase 6 stack and record the source SHA, schema revision, and sanitized service health.
2. Generate separate synthetic credential and transcript keys. Store the recovery copy in an access-controlled test escrow that is independent of the app and database volumes; record custody metadata without recording key values.
3. Insert synthetic transcripts, create a PostgreSQL backup, verify its checksum/archive, and back up only synthetic uploads.
4. Rotate to a second test key in bounded batches. Interrupt a disposable run, verify resume/rollback behavior, and confirm every expected synthetic transcript remains readable.
5. Create a new empty disposable project/database and restore the backup and uploads. Recover the necessary keys through the independent test escrow path and verify synthetic transcript integrity and session state.
6. Record restoration time, row/checksum comparisons, unreadable count, key IDs only, and any failed cleanup. Retain redacted logs outside application volumes.
7. Run rollback while both test keys remain available. Do not retire the old test key until restore and readability checks pass.

Do not use production keys or hotel data. Closing `ECC-HIST-001` operationally requires a successful separately recovered restore; an in-container key copy is insufficient. `ECC-OPS-001` remains blocked until installation, data restore, app rollback, and proxy recovery also pass.
