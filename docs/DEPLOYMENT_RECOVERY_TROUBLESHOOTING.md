# Source deployment, WSL and recovery troubleshooting

Updated 2026-10-17. Preserve existing `.env`, encryption keys, database, uploads and administrator accounts. Run diagnostics before changing an installation. Never attach raw environment dumps, private configuration or subprocess output to public evidence.

## WSL installer appears frozen at port-check

From the source checkout, the read-only probe is:

```bash
.venv/bin/python deploy/source_service.py --root . --platform linux port-check
```

The shared probe uses a one-second timeout per IPv4/IPv6 connection candidate. A refused or timed-out connect is followed by an independent local bind check, with no socket reuse option. The probe closes every socket. An occupied bind blocks installation. A permission/network error that cannot establish availability produces an explicit indeterminate error and blocks source installation; appliance preflight treats it as busy. Unsupported local IPv6 may be skipped after IPv4 is checked. A successful check is a point-in-time result: another process can still claim the port before application startup.

On this macOS workstation the Linux-mode read-only command completed in 0.047 seconds with exit 0. Synthetic tests cover IPv4/IPv6, listeners, refused/timed-out probes, successful/conflicting binds, unsupported IPv6, socket closure and indeterminate failures. This is **not native WSL certification**. Do not edit `.wslconfig`, change networking modes or shut down WSL automatically.

When blocked, identify the owner using the platform's listener tools and deployment diagnostics. Do not kill a process merely because it owns port 8080. `deploy/common/preflight.py` shares the bounded probe; its foreign-uvicorn check is a `ps` inspection with a two-second subprocess timeout. There is no socket connect in that check.

## Deployment diagnosis selects the wrong database

The selected config file now takes precedence over the invoking shell for explicitly configured values. Previously a shell `DATABASE_URL=` could replace a PostgreSQL URL from the selected file and make doctor report SQLite. Conversely an explicitly blank URL selects SQLite and must not inherit a different shell database. Missing config keys may still use allowed environment fallbacks. Database URLs and provider credentials are never rendered by doctor.

```bash
.venv/bin/python deploy/source_service.py --root . --platform linux doctor
.venv/bin/python deploy/source_install.py validate --root . --python .venv/bin/python
```

Use `--platform macos` for the corresponding source service. Diagnose the actual deployment's config/root; an unrelated shell configuration does not describe its database.

## Safe upgrade and lock behavior

Before an approved upgrade, create and verify an encrypted application backup with the installation's existing private configuration and backup key:

```bash
.venv/bin/python -m app.backup create /private/backup/location/concierge.zip.enc
.venv/bin/python -m app.backup verify /private/backup/location/concierge.zip.enc
```

Keep the backup key securely and separately. These paths are operator placeholders. Do not put credentials in command arguments. Preserve the existing `.env`; do not delete state or reset administrators to make installation succeed. The source installer re-executes through `operation_lock.py`, which sets `CONCIERGE_OPERATION_LOCK_HELD=1`; the re-executed installer skips a second acquisition. This generic same-operation wrapper intentionally retains the caller's environment so installation-tool settings remain available. Application initialization and fallback-service children now use the explicit application/runtime allow-list and exclude unrelated host secrets and Python injection variables.

The real configuration/bootstrap/repeat-upgrade stages were exercised in a temporary source copy. Existing private config and administrator records were preserved, with no service commands. Service-definition tests verify user ownership and service behavior with mocks. Native Linux systemd verification remains a platform CI check; no host systemd/launchd changes were made here.

## PostgreSQL backup authentication and failure handling

`pg_dump` and `pg_restore` receive PATH, selected locale/platform settings, explicit libpq TLS/password-file/Kerberos settings and connection values parsed from the requested URL. Arbitrary `PGHOST`/`PGDATABASE`/host passwords are not inherited. URL settings override allow-listed defaults; `passfile` and `service` query options are supported. Default libpq password-file discovery remains available; explicit `PGPASSFILE` is preferred for deployments using password files. Protect password/key files with owner-only permissions. See [PostgreSQL's libpq environment reference](https://www.postgresql.org/docs/current/libpq-envars.html).

Database passwords are absent from argv. Failure output is withheld; timeout/missing-tool exceptions suppress child diagnostic chaining. Backup creation rejects missing/empty dumps. PostgreSQL restore first refuses a nonempty target and uses a single transaction with exit-on-error. A failed database transaction does not warrant wiping an existing installation.

To drill recovery, provision a new, isolated database and isolated upload directory, load its configuration privately, verify the archive, then use the existing CLI:

```bash
.venv/bin/python -m app.backup restore /private/backup/location/concierge.zip.enc
```

Do not use `--replace` against production as a test. The completed drill used a disposable local PostgreSQL 16.15 cluster initialized with UTF-8, migrated the schema, created an encrypted backup, restored into a separate clean database and verified records/uploads/source integrity. An initial SQL_ASCII fixture caused SQLAlchemy version detection to receive bytes; initializing the test cluster explicitly with UTF-8 resolved that fixture error. This did not require a product-code workaround.

## Verification limits

Backend/API tests cover Python 3.11–3.14; functional browser checks cover desktop/mobile Chromium. Real external AI/places/notification services, full PostgreSQL/Redis interruption recovery, native WSL, native Linux services, production image/Trivy/SBOM checks and deployed CI status require their corresponding infrastructure. Skipped tests do not establish those results. The historical credential incident remains separate; follow [the history maintenance runbook](SECURITY_HISTORY_CLEANUP_RUNBOOK.md) after explicit owner approval.
