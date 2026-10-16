# Off-host disaster recovery rehearsal

Run this rehearsal on a clean, disposable Ubuntu or Apple Silicon macOS
environment. Record source/target releases, archive checksum, operator, date,
restored property and record counts, health results, and pass/fail for each
step. Do not include database rows, credentials, keys, cookies, or full
environment files in the evidence. This procedure has not yet been performed
by the current repository audit.

## Prepare an encrypted off-host backup

1. On the source appliance, create and verify a backup:

   ```bash
   sudo concierge backup
   ```

   The application writes an authenticated AES-256-GCM archive named
   `concierge-<timestamp>.zip.enc`. It contains the database and uploads but
   excludes `CONCIERGE_BACKUP_ENCRYPTION_KEY` and
   `CREDENTIAL_ENCRYPTION_SECRET`. Locate the archive in
   `/var/backups/concierge/` on Ubuntu or
   `/Library/Application Support/Concierge.AI/Backups/` on macOS and record its
   SHA-256 checksum.
2. Copy the encrypted archive and checksum to a separate account or failure
   domain. Confirm retention, access controls, and a second copy per the
   organization's backup policy. Do not decrypt the archive before transfer.
3. Confirm both `CONCIERGE_BACKUP_ENCRYPTION_KEY` and
   `CREDENTIAL_ENCRYPTION_SECRET` are escrowed in separate records in the
   organization's approved secrets vault, with access limited to recovery
   operators. Neither key belongs in the archive or off-host backup directory.
   Confirm both records can be retrieved without displaying key values in a
   terminal, ticket, or audit log.

## Restore to a clean environment

1. Install a clean disposable Concierge target. Do not point it at the source
   database or upload directory. Copy the encrypted archive to a restricted
   path on the target and verify the recorded checksum.
2. Retrieve the matching `CONCIERGE_BACKUP_ENCRYPTION_KEY` and
   `CREDENTIAL_ENCRYPTION_SECRET` from their separate escrow records. Inject
   them into the target's protected Concierge environment using the approved
   secret-management procedure. Do not paste key values into a command line,
   shell history, transcript, or report. Keep the file owner and permissions
   restrictive. The backup key must match the archive; the credential key must
   match the source database so encrypted provider credentials remain readable.
3. Stop the application before replacing target state:

   ```bash
   sudo concierge internal-stop
   ```

   On Ubuntu, copy the encrypted archive into the configured backup directory
   (installed default `/var/backups/concierge`) and run restore in the stopped
   application container. Substitute the actual archive basename:

   ```bash
   RELEASE_VERSION=$(sudo cat /opt/concierge/current/RELEASE_VERSION)
   sudo env CONCIERGE_CONFIG_FILE=/etc/concierge/concierge.env \
     CONCIERGE_VERSION="$RELEASE_VERSION" \
     docker compose --project-name concierge \
       --project-directory /opt/concierge/current \
       --env-file /etc/concierge/concierge.env \
       -f /opt/concierge/current/docker-compose.yml \
       run --rm --no-deps concierge python -m app.backup restore \
       /backups/restore.zip.enc --replace
   sudo systemctl start concierge.service
   ```

   On macOS, keep the archive in a root-only path. Open a root shell, source
   the protected appliance environment, and restore using the installed
   virtualenv:

   ```bash
   sudo -s
   set -a
   . "/Library/Application Support/Concierge.AI/concierge.env"
   set +a
   cd /opt/concierge/current
   /opt/concierge/current/.venv/bin/python -m app.backup restore \
     "/private/var/root/restore.zip.enc" --replace
   /usr/local/libexec/concierge-restart
   exit
   ```

   `--replace` is destructive to the disposable target's current state. Never
   use it against the source appliance or a target with data that has not been
   backed up and independently approved for replacement. Restore validates
   the GCM authentication tag and archive manifest before applying the database
   and uploads. Historical plaintext ZIPs are rejected unless
   `--allow-legacy-unencrypted` is explicitly supplied for a trusted archive.
4. Run `sudo concierge doctor`, then query `/health/live`, `/health/ready`, and
   `/health/version`. Confirm the public version endpoint contains only
   `status` and `version`. Sign in as Platform Admin and confirm
   `/api/admin/system/diagnostics` is healthy and sanitized. Confirm the
   restored property and a known non-sensitive record are present, upload files
   open, and expected row/file counts match the source evidence.
5. Through authenticated Platform Admin diagnostics, confirm restored provider
   integrations report their expected configured or connected state. Do not
   display, export, or record credential values. A controlled provider check
   may use only an approved non-production endpoint and test credential.
6. Verify the original source appliance remains unchanged and healthy. Confirm
   the off-host archive checksum and separately escrowed keys remain
   accessible to the recovery role. Remove disposable state using the approved
   secure disposal process.

## Rehearsal result

Record PASS, FAIL, or NOT RUN for archive encryption, off-host transfer,
checksum verification, independent key retrieval, clean-target restore,
credential decryption validation, application startup, health checks,
data/upload validation, source integrity, and cleanup. A local encrypted backup
does not establish off-host recovery acceptance.
