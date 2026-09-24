# 27 — Backup and restore test

Status: **FIXED AND VERIFIED**.

Commands:

```text
python -m app.backup create backup.zip
python -m app.backup verify backup.zip
python -m app.backup restore backup.zip --replace
```

The create command uses SQLite's online backup API, runs `PRAGMA integrity_check`, includes the database and upload tree, records SHA-256 hashes in a versioned manifest, and atomically publishes the archive. Provider credentials remain encrypted inside the database. Verification rejects checksum failures, missing members, unsupported versions, unsafe paths, and corrupt SQLite snapshots. Restore stages files, requires an explicit replacement flag for existing targets, and refuses broad filesystem roots.

The integration test populated a property, service request, AI provider credential, and uploaded knowledge file; created and verified a backup; removed the live database/file; restored; reopened every store; decrypted the restored credential; verified the request/file; and reran SQLite integrity checking. Result: passed.

Residual risk: scheduling, retention, encryption of the entire archive at rest, and off-host replication are deployment responsibilities not implemented in this pass.
