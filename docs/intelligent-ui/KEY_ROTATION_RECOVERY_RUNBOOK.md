# Transcript key rotation and recovery runbook

## Off-host escrow requirements

Store `CREDENTIAL_ENCRYPTION_SECRET` and each `CONVERSATION_ENCRYPTION_KEYS` value in the organization's approved off-host secrets manager or offline recovery escrow. Require encrypted storage, least-privilege access, MFA, and two-person break-glass approval for production retrieval. Keep a separate access path from the application host. Record key IDs, owners, custody dates, and recovery-test outcomes; never copy secret values into this runbook, source control, tickets, shell history, or application logs.

The database backup does not contain encryption keys. A backup is recoverable only when its matching secret material and application version can also be recovered.

## Read-only inventory

Use the approved release virtual environment and a disposable or explicitly approved target. For SQLite, pass an existing database path. For PostgreSQL, set the approved `DATABASE_URL` in the process environment and omit `--database`.

```sh
APP_ENVIRONMENT=staging .venv/bin/python -m app.transcript_rotation \
  --database /secure/staging-copy/concierge.db
```

The command reports aggregate cell counts, unreadable count, key IDs, and a stable fingerprint. It does not print plaintext or secret values. Stop if the expected schema is missing, any row is unreadable, the copy is not disposable/approved, or the fingerprint changes unexpectedly.

## Rehearsal and apply

1. Make a disposable copy of the database and uploads; verify checksums and keep the source unchanged.
2. Recover the legacy credential secret and required old/new ring entries from escrow into the approved process secret mechanism. Set `CONVERSATION_ENCRYPTION_ACTIVE_KEY_ID` to the intended target. Deploy the dual-read application to all workers before migration.
3. Run inventory and preserve the sanitized output with the change record.
4. Rehearse on the disposable copy:

```sh
APP_ENVIRONMENT=staging .venv/bin/python -m app.transcript_rotation \
  --database /secure/staging-copy/concierge.db \
  --target-key-id candidate-2026 \
  --batch-size 100 --apply
```

5. Confirm the command's final inventory has `unreadable: 0`; perform a separate read-only inventory and compare it with the completion output. Verify synthetic transcripts for two properties, normal guest access, and staff conversation review.
6. For an approved production operation only, use the organization's separate change authorization and explicit `--allow-production` CLI gate. No production rotation was run for Phase 4.

## Interruption and resume

Each committed batch is atomic and verified. If the process exits or a database error occurs, preserve the sanitized error and do not delete keys. Re-run inventory; restore any key identified as unavailable from escrow. Re-run the same apply command with the same target ID. Target-format records are skipped; unchanged/uncommitted rows remain available for resume. Confirm zero unreadable rows after completion.

## Rollback

Before retiring a prior key, keep it in the key ring and verify it decrypts the post-rotation sample. To reverse a completed migration to a retained versioned key, run apply with that key ID as `--target-key-id`. To roll back to a pre-key-ring application, first run the tool with `--target-key-id legacy`; this writes v1 message ciphertext and untagged guest-turn ciphertext, then verify and deploy the previous application. Keep the legacy credential secret unchanged because provider credential storage also depends on it.

If a database write fails, the current batch rolls back. If a transcript fails decryption, the tool stops before mutation. Preserve the database and logs, restore the required key from escrow, and use the inventory command before resuming. Do not replace the database with an unverified backup.

## Recovery test status

The local regression uses synthetic key material in a mode-0600 temporary fixture, recovers it into the key ring, reads old/new ciphertext, rotates and rolls back a disposable SQLite database, and verifies failure/resume behavior. This validates application mechanics only. Actual off-host escrow authorization, target backup restore, PostgreSQL recovery, and organizational dual-control remain staging acceptance items.
