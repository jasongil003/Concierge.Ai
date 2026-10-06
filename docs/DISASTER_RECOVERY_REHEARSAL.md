# Off-host disaster recovery rehearsal

Run this rehearsal on a clean, disposable Ubuntu or Apple Silicon macOS
environment. Record the source/target releases, backup checksum, operator,
date, restored property and record counts, health results, and pass/fail for
each step. Do not include database rows, credentials, keys, cookies, or full
environment files in the evidence. This procedure has not been performed by
the current repository audit.

## Prepare an encrypted off-host backup

1. On the source appliance, create and verify a normal application archive:

   ```bash
   sudo concierge backup
   ```

   The archive contains the database and uploads but does not contain
   `CREDENTIAL_ENCRYPTION_SECRET`. The application archive itself is not
   encrypted. Locate the new ZIP in `/var/backups/concierge/` on Ubuntu or
   `/Library/Application Support/Concierge.AI/Backups/` on macOS and record its
   SHA-256 checksum.
2. Using the organization's approved file-encryption tool and off-host
   recipient, encrypt the ZIP before copying it off the appliance. For an
   approved `age` setup, use the escrowed recipient public key (this is not the
   Concierge credential key):

   ```bash
   age -r "$OFFSITE_AGE_RECIPIENT" -o "/mnt/offsite/concierge-backup.zip.age" \
     "/path/to/concierge-backup.zip"
   ```

   Copy the encrypted `.age` file and its checksum to a separate account or
   failure domain. Confirm retention, access controls, and a second copy per
   the organization's backup policy. Never upload the plaintext ZIP.
3. Confirm the Concierge credential key is escrowed separately in the
   organization's approved secrets vault, with access limited to recovery
   operators. It must not be copied into the backup archive, encrypted beside
   that archive, or stored in the off-host backup directory. Confirm the
   escrow record is retrievable without displaying the key in a terminal,
   ticket, or audit log.

## Restore to a clean environment

1. Install a clean disposable Concierge target using the supported-platform
   procedure. Do not point it at the source database or upload directory. Copy
   the encrypted archive to a restricted temporary directory on the target and
   verify its recorded checksum before decrypting it.
2. Decrypt with an identity authorized for the rehearsal. Keep the decrypted
   ZIP in a root-only temporary or backup directory, verify its application
   archive checksum, and run the archive's built-in verification before
   applying it. The identity used to decrypt this outer archive is also
   independent of `CREDENTIAL_ENCRYPTION_SECRET`.
3. Retrieve the matching `CREDENTIAL_ENCRYPTION_SECRET` from the separate
   secrets vault. Inject it into the target's protected Concierge environment
   file using the organization's secret-management procedure. Do not paste it
   into a command line, shell history, transcript, or report. Keep the file
   owner and permissions restrictive. The escrowed value must match the source
   backup so encrypted provider credentials can be decrypted.
4. Stop the application before replacing target state:

   ```bash
   sudo concierge internal-stop
   ```

   On Ubuntu, copy the verified plaintext ZIP into the configured backup
   directory (installed default `/var/backups/concierge`) and run the restore
   one-off in the stopped application container. Substitute the actual ZIP
   basename for `restore.zip`:

   ```bash
   RELEASE_VERSION=$(sudo cat /opt/concierge/current/RELEASE_VERSION)
   sudo env CONCIERGE_CONFIG_FILE=/etc/concierge/concierge.env \
     CONCIERGE_VERSION="$RELEASE_VERSION" \
     docker compose --project-name concierge \
       --project-directory /opt/concierge/current \
       --env-file /etc/concierge/concierge.env \
       -f /opt/concierge/current/docker-compose.yml \
       run --rm --no-deps concierge python -m app.backup restore \
       /backups/restore.zip --replace
   sudo systemctl start concierge.service
   ```

   On macOS, keep the verified ZIP in a root-only path. Open a root shell,
   source the protected appliance environment there, and restore using the
   installed virtualenv:

   ```bash
   sudo -s
   set -a
   . "/Library/Application Support/Concierge.AI/concierge.env"
   set +a
   cd /opt/concierge/current
   /opt/concierge/current/.venv/bin/python -m app.backup restore \
     "/private/var/root/restore.zip" --replace
   /usr/local/libexec/concierge-restart
   exit
   ```

   `--replace` is destructive to the disposable target's current state. Never
   use it against the source appliance or a target with data that has not been
   backed up and independently approved for replacement. The restore command
   verifies checksums before applying the database and uploads.
5. Run `sudo concierge doctor`, then query `/health/live`, `/health/ready`, and
   `/health/version`. Confirm the public version endpoint contains only
   `status` and `version`. Sign in as Platform Admin and confirm
   `/api/admin/system/diagnostics` is healthy and sanitized. Confirm the
   restored property and a known non-sensitive record are present, upload files
   open, and expected row/file counts match the source evidence.
6. Through authenticated Platform Admin diagnostics, confirm the restored
   provider integrations can be read and report their expected configured or
   connected state. Do not display, export, or record credential values. A
   controlled provider connection check may be performed only with the
   organization's approved non-production endpoint and test credential.
7. Verify the original source appliance remains unchanged and healthy. Confirm
   the backup still decrypts from the off-host copy and the independent key
   escrow remains accessible to the recovery role. Remove decrypted temporary
   archives and disposable state using the approved secure disposal process.

## Rehearsal result

Record PASS, FAIL, or NOT RUN for encryption, off-host transfer, checksum
verification, independent key retrieval, clean-target restore, credential
decryption validation, application startup, health checks, data/upload
validation, source integrity, and cleanup. A local backup alone or a restore
that uses a key copied from the backup environment is not a successful off-host
disaster recovery rehearsal.
