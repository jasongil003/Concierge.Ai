# 27 — Backup and restore test

Status: **ENCRYPTION AND LOCAL RESTORE VERIFIED; OFF-HOST ACCEPTANCE BLOCKED**.

Commands:

```text
python -m app.backup create backup.zip.enc
python -m app.backup verify backup.zip.enc
python -m app.backup restore backup.zip.enc --replace
```

These commands read `CONCIERGE_BACKUP_ENCRYPTION_KEY` from the protected
environment. The value is a separately generated 32-byte key encoded as 64
hexadecimal characters. Keep it in approved off-host recovery escrow; never
put it in the backup, source control, or the same off-host backup directory.
Legacy plaintext ZIP archives are rejected unless `--allow-legacy-unencrypted`
is explicitly supplied for a trusted archive.

The create command uses SQLite's online backup API, runs `PRAGMA integrity_check`, includes the database and upload tree, records SHA-256 hashes in a versioned manifest, and atomically publishes the archive. Provider credentials remain encrypted inside the database. Verification rejects checksum failures, missing members, unsupported versions, unsafe paths, and corrupt SQLite snapshots. Restore stages files, requires an explicit replacement flag for existing targets, and refuses broad filesystem roots.

The focused backup/deployment/security set passed **155 tests** with **2 infrastructure-dependent skips**. It populates synthetic property, service request, AI provider credential, and uploaded knowledge data; creates and verifies the encrypted backup; restores into disposable state; reopens the stores; and checks records/files and SQLite integrity. Negative cases confirm wrong-key/tampered archives fail before restore targets are created, and plaintext legacy ZIPs require an explicit operator option. PostgreSQL uses the same envelope around its custom-format dump and uploads, but the PostgreSQL host integration was skipped because local PostgreSQL configuration/tooling was unavailable.

Remaining acceptance: off-host replication, independent recovery-key retrieval, and clean-host restore must be performed by the infrastructure owner with synthetic data. These operational steps are not marked live verified by local tests.
