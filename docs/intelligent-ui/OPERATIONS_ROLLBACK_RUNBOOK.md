# Operations and rollback runbook

This procedure is for a disposable target or approved staging environment. Do not run restore or rollback commands against production without the organization's separate change approval and backup procedure.

## Candidate preparation

1. Record the source and candidate commit, runtime, schema revision, deployment mode, and operator.
2. Take a normal application backup and verify its checksum before applying the candidate. The backup does not contain `CREDENTIAL_ENCRYPTION_SECRET`; escrow that key separately.
3. Copy the database and upload directory into disposable staging resources. Verify the copied database and upload checksums, and keep the source read-only.
4. Install/upgrade the candidate through the supported installer. Startup migrations are additive. In this release, facility location/policies use a new `facility_metadata` table, leaving the existing `facility_profiles` columns unchanged for older-release positional inserts.
5. Run health checks and the acceptance checklist. Save sanitized counts and outcomes only.

## Backup and restore rehearsal

Use the repository backup APIs on temporary paths; the automated `tests/test_backup_restore.py` suite exercises SQLite create, verify, and restore without touching the persistent application database. For a manual disposable rehearsal, call `create_backup(source_db, source_uploads, archive_path)`, `verify_backup(archive_path)`, and `restore_backup(archive_path, empty_target_db, empty_target_uploads)` from a local Python harness that supplies only temporary paths. Do not pass `replace=True` unless the target is disposable and intentionally being replaced.

PostgreSQL restore requires `pg_dump`/`pg_restore` and a separate empty disposable database. This host did not have the PostgreSQL service/tooling evidence needed for that check. For appliance/off-host disaster recovery, follow [DISASTER_RECOVERY_REHEARSAL.md](../DISASTER_RECOVERY_REHEARSAL.md).

## Intelligent UI rollback

1. With an account that has `system.configure`, disable the persisted global Intelligent UI switch using the existing Admin control/API.
2. Read back the switch and verify its audit event.
3. Open a fresh guest page: the legacy experience must load. V2 assets, chat, and history must fail closed while disabled.
4. Verify existing guest session data remains subject to normal expiry/revocation and has not been deleted.
5. If the database switch cannot be reached, set the installation-level `INTELLIGENT_GUEST_UI_GLOBAL_ENABLED=false`; restart only through the target's service manager if environment configuration must reload.

See [feature-flag rollback details](FEATURE_FLAG_ROLLBACK.md). Do not manually delete guest transcript, session, or provider records as part of rollback.

## Release rollback

1. Stop candidate traffic through the target load balancer or service manager; preserve logs and sanitized failure details.
2. Select the previously approved release through the deployment system and start it against the same backed-up disposable state first.
3. Check `/health/live`, `/health/ready`, login, legacy guest routes, and a synthetic property. Facility metadata stays in an extra table and old releases may ignore it; do not drop it during downgrade.
4. If schema or data behavior differs, stop and restore only the verified backup to a disposable target. Never reset or overwrite the production database from this runbook.
5. Keep the global Intelligent UI flag disabled until the root cause and rollback decision are reviewed.

Record source/candidate commits, backup verification, health result, old/new UI behavior, migration outcome, operator, date, and go/no-go. Never place secrets, cookies, guest transcripts, or raw database rows in the evidence.
