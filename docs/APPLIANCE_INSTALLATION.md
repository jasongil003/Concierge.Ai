# Concierge.AI Appliance Installation

This guide describes the managed on-prem installation path. One bootstrap
command detects the operating system and hardware, downloads the latest stable
GitHub Release, verifies its SHA-256 digest, then dispatches to the native host
service manager. It never follows `main` and it does not seed a hotel or demo
property.

## Support status

The repository now contains appliance installers, service definitions, backup
and recovery jobs, stable-release updates, and platform-aware checks. The
mandatory real reboot acceptance run has **not** been executed on a clean Ubuntu
server or a Mac mini in this development environment. Therefore neither target
is yet verified for production support. Do not treat static checks or a passing
application health endpoint as a substitute for the reboot test below.

Checks completed in this checkout on 2026-10-06: backend `pytest -q -rs`
reported 938 passed, 17 skipped, 0 failed, and 2 dependency deprecation
warnings. The Playwright suite reported 260 passed, 35 skipped, and 1 failed:
the mobile guest restaurant-details toggle had a transient visibility/state
mismatch (`tests/e2e/guest.spec.js:754`). An immediate isolated rerun of that
test passed (1 passed); the full-suite failure remains recorded. Linux and
macOS installer Bash syntax and ShellCheck checks passed, all macOS LaunchDaemon
property lists passed `plutil -lint`, deployment Python compiled, Bandit passed,
and Docker Compose configuration parsed. Backend skips are PostgreSQL and
Redis integration cases plus the `systemd-analyze` service check. The local
Docker daemon is unavailable, so container runtime smoke, image vulnerability
scanning, SBOM generation, and containerized Nginx validation did not run.
`npm audit` could not reach the npm registry because registry DNS resolution
failed. `pip-audit`, Gitleaks, Trivy, and actionlint are not installed locally;
a local scan for common credential patterns found no matches. Hosted Linux CI
and hosted CI security jobs have not run for this change. These checks do not
count as a real reboot acceptance test.

The installer supports Ubuntu Server 24.04 LTS and 26.04 LTS on amd64 and arm64,
and Apple Silicon Macs running macOS Sequoia 15, Tahoe 26, or Golden Gate 27.
Intel macOS and Windows/WSL are not production targets. macOS support uses native
Python, a loopback proxy, and machine LaunchDaemons; it does not require Docker
Desktop, Homebrew, an interactive user session, or a logged-in graphical desktop.

## Ubuntu Installation

Start from a clean, updated Ubuntu Server 24.04 or 26.04 LTS host with at least
8 GiB free disk space and network access to GitHub. From the local console or an
SSH session, run:

```bash
curl --fail --silent --show-error --location \
  https://github.com/jasongil003/Concierge.Ai/releases/latest/download/concierge-install.sh \
  | sudo bash
```

The common installer detects the architecture, CPU, RAM, free disk, network,
GPU availability, and whether local AI is advisable. It installs Ubuntu's
Docker Engine and Compose packages, creates the locked `concierge` system user,
generates production secrets, and installs the selected stable release under
`/opt/concierge`. It prompts for the hotel's canonical hostname, SG5 processor
URL, trusted administrator source CIDRs, and a new administrator password.
Password input is hidden and confirmed; it is saved only in the protected host
configuration and is not printed by the installer.

Concierge runs in a single Docker Compose project. SQLite and uploaded files
persist in the `concierge-state` Docker volume; verified backup archives live in
`/var/backups/concierge`. The host listener is bound to `127.0.0.1:8080`; the
application container has no published host port. No property data is created
until the administrator completes onboarding.

Allow outbound access to Ubuntu package mirrors, GitHub Releases, Docker Hub,
and PyPI so the host packages, application image, proxy image, and Python
dependencies can be installed and updated.

## Mac mini Installation

Use an Apple Silicon Mac mini with a currently supported macOS release and at
least 8 GiB free disk space. Run the same bootstrap command:

```bash
curl --fail --silent --show-error --location \
  https://github.com/jasongil003/Concierge.Ai/releases/latest/download/concierge-install.sh \
  | sudo bash
```

The installer verifies and installs the signed
[Python.org macOS package](https://www.python.org/downloads/macos/) for Python
3.14, creates a locked `_concierge` service account, installs the application
and its virtual environment under `/opt/concierge`, and registers system LaunchDaemons in
`/Library/LaunchDaemons`. Application state and backups live under
`/Library/Application Support/Concierge.AI`; service logs live under
`/Library/Logs/Concierge.AI`. Concierge listens at `127.0.0.1:8080`, with its
application backend separately bound to `127.0.0.1:8081`.

Allow outbound access to GitHub Releases, Python.org, and PyPI during install
and maintenance so the signed Python runtime and application dependencies can
be installed.

The Mac service is native and machine-scoped so it can start before any user
signs in. Docker Desktop's documented startup option starts when a user signs
in, so this appliance does not use it. [Apple documents LaunchDaemons as
system-level startup jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html);
[Docker documents its desktop startup behavior as sign-in based](https://docs.docker.com/desktop/settings-and-maintenance/settings/).

## Startup on Boot

Both host integrations own startup and shutdown:

- Ubuntu enables `concierge.service` and the health, backup, and maintenance
  systemd timers. Docker starts with the system, and Concierge waits for network
  readiness.
- macOS installs server and loopback-proxy LaunchDaemons with `RunAtLoad` in the
  system domain. Health, backup, and maintenance jobs are also machine-level
  LaunchDaemons.

The installer starts Concierge immediately, waits for `/health/live` and
`/health/ready`, then checks `/admin/login` over localhost. `sudo concierge
status`, `sudo concierge health`, and `curl http://127.0.0.1:8080/health/ready`
are available for routine checks.

The localhost HTTP endpoint is intentionally limited to loopback. For hotel
network access, place a trusted TLS reverse proxy in front of it. Configure
that proxy to replace forwarded-client headers using the actual connection,
and set the exact proxy addresses in the Concierge trusted-proxy and Admin
CIDR settings. Do not expose port 8080 or the Mac backend port 8081 directly to
untrusted interfaces.

## Local AI on Apple Silicon

Local AI is disabled at initial installation. Concierge can operate without
Ollama; configure a supported hosted provider or use the hotel's non-AI flows.
On an Apple Silicon Mac with at least 8 GiB unified memory and 10 GiB free disk,
an administrator can opt in:

```bash
sudo concierge local-ai enable
sudo concierge local-ai status
```

Enable downloads the current Ollama macOS release asset, checks the GitHub
SHA-256 digest and Apple code signature, and starts Ollama as a LaunchDaemon
under `_concierge`, following
[Ollama's macOS deployment guidance](https://github.com/ollama/ollama/blob/main/docs/macos.mdx).
It pulls only `qwen3:4b`, stores model data in the system Application Support
directory, and verifies the local health endpoint before turning on local
inference in Concierge. Model suitability still depends on measured latency and
memory pressure.

Disable inference while retaining the optional runtime and its model cache with
`sudo concierge local-ai disable`. Remove Ollama and its cached models with
`sudo concierge local-ai uninstall`.

## Self-Recovery

Both platforms use the shared `deploy/common/ops.py` recovery policy and JSONL
event format. Health checks move through `NORMAL`, `DEGRADED`, `RECOVERY`, and
`CRITICAL`. The supervisor allows at most three restarts in a 15-minute window,
records each decision, and stops retrying at the ceiling. It never restores or
rewrites a database automatically. Inspect recovery events at
`/var/lib/concierge/recovery-events.jsonl` on Ubuntu or
`/Library/Application Support/Concierge.AI/recovery-events.jsonl` on macOS.

## Backup

Both systems call the same `app.backup` create and verify implementation and
write the same ZIP format. Ubuntu schedules a daily systemd timer; macOS uses a
daily LaunchDaemon calendar interval. Backups older than 30 days are removed
during maintenance. The installer also creates and verifies a backup before an
application update. Backup files should be copied to a separate protected
system as part of the hotel's disaster-recovery plan; the local copy alone is
not an off-host backup. Provider credentials remain encrypted in the database.
Keep `CREDENTIAL_ENCRYPTION_SECRET` in an independent, access-controlled
password manager or secrets vault. The key is deliberately absent from the
backup archive. A restore drill must recover both the backup and that key from
their separate protected locations; never store the key beside the backup.

Create and verify a backup on demand with:

```bash
sudo concierge backup
```

## Updates

Start troubleshooting with `concierge doctor`; it reports the active runtime,
release identity, listener owner, service state, and readiness separately from
liveness. `concierge status` gives a concise summary. Both commands are
read-only. The unauthenticated `GET /health/version` returns only `status` and
the semantic application `version`. For detailed build, database, and platform
diagnostics, sign in as a Platform Admin and use
`GET /api/admin/system/diagnostics`; global `/health/details` also requires
Platform Admin permission.

The shared command checks the latest stable GitHub Release metadata, downloads
the versioned source archive, verifies SHA-256, and rejects unexpected archive
paths. It verifies a fresh backup before changing the active release, runs the
application migration/import check, restarts services, and waits for healthy
readiness. A schema preflight checks candidate migration support and the prior
release's declared compatibility range before service changes. It warns and
blocks by default when migration would make rollback unsafe. An explicit
`--allow-incompatible-rollback` requires a verified backup; if the candidate
then fails after an incompatible migration, the prior pointer is restored but
the prior service is not started and no database downgrade is attempted. The
command reports operator recovery as required. Compatible failures restore the
prior pointer, start the prior release, and report whether readiness passed.
The current updater switches the `current` pointer before migration and health
validation; install/update work is protected by a process lock at
`/opt/concierge/.deployment.lock`.

```bash
sudo concierge update
```

The schema preflight belongs to the installed updater. An appliance running an
older updater does not gain these checks until that updater is replaced, so
validate this first transition on a disposable clone of the exact installed
release and schema before updating production. Do not infer first-hop rollback
safety from the candidate code alone.

The repository must publish a stable `vMAJOR.MINOR.PATCH` GitHub Release with
the generated appliance assets before the bootstrap installer or update command
can run. Development commits and `main` are never auto-installed.

The active deployment manifest is stored at `deployment.json` in the appliance
state directory. It contains version, commit, build date, deployment mode,
schema revision/compatibility range, and install/update timestamps only.
Verified backups carry sanitized application identity and file checksums.

## Fresh Install, Update, and Recovery Acceptance

Run the following checklist on a disposable clean target for **Ubuntu Server
24.04/26.04 amd64 and arm64**, then separately on an **Apple Silicon Mac mini**.
Do not use a production appliance, its database, its release repository, or its
credentials for a simulated failure. Intel macOS and Windows/WSL are unsupported.

1. Install from the stable release using the platform command above. Record OS,
   hardware, release version, and the install output. Complete the initial
   administrator password setup; confirm a first property can be created in
   Admin and persists after signing out and back in.
2. Check `sudo concierge doctor`, then run:

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:8080/health/live
   curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
   curl --fail --silent --show-error http://127.0.0.1:8080/health/version
   ```

   Confirm `/health/version` contains only `status` and `version`. Confirm
   detailed release and schema identity in Platform Admin diagnostics and the
   local deployment manifest. Do not attach credentials or full environment
   output to the evidence.
3. Create an on-demand backup with `sudo concierge backup`. Copy it to the
   designated protected off-host backup store. Separately retrieve the
   encryption key from escrow and verify that a restore into a new, empty
   disposable state path recovers the property and a known record. Confirm the
   source database still has the same record after validation.
4. On a staging appliance pointed at a **separate acceptance-only GitHub
   repository** with a stable, signed test release, run
   `sudo CONCIERGE_REPOSITORY=owner/concierge-acceptance concierge update`.
   Record the old/new release identities, schema assessment, backup
   verification, and final doctor output. Never publish a simulated failure to
   the production release repository.
5. For rollback acceptance, publish a staging-only signed candidate with a
   valid archive/checksum that deliberately fails application startup before
   schema migration. Run the update against that staging repository, and
   verify that the previous release pointer is restored, the previous service
   starts healthy, the database has not been downgraded, and the verified
   backup remains available. Capture the command's exact recovery state.
6. Run `sudo concierge boot-test prepare`, reboot without manually starting
   Concierge or Docker, then run `sudo concierge boot-test verify`. Confirm the
   boot ID changed and the pre-reboot property count/configuration digest
   matches. Repeat the health checks and `sudo concierge doctor`.
7. Save the sanitized health responses, backup verification result, update and
   rollback output, doctor report, `boot-test.json`, and host details with the
   release acceptance record.

The simulated failure requires a disposable appliance and a separate
acceptance release channel; it must not be attempted against production data.
The test-only release should fail before migration so the rollback validates
the compatible path. The incompatible-schema path is intentionally fail-closed
and requires operator recovery; do not induce that state on a production host.
Use the full [production acceptance procedure](PRODUCTION_ACCEPTANCE.md),
including the off-host [disaster recovery rehearsal](DISASTER_RECOVERY_REHEARSAL.md),
as the signed evidence record for each supported OS and architecture.

## Boot Test

Run this acceptance procedure on **each supported platform**, using a clean
installation and at least one property created and saved through Admin. It
records the current machine boot identifier and a digest of the property
configuration, then requires an actual reboot before it can pass:

```bash
sudo concierge boot-test prepare
```

Reboot the machine. Do not start Docker or Ollama manually, launch Concierge,
keep a Terminal command running, or sign into the graphical desktop where
avoidable. Wait for the machine services to initialize, then run:

```bash
sudo concierge boot-test verify
```

Verification checks that the boot identifier changed, the platform runtime,
proxy, Concierge, live and ready health endpoints, and local Admin endpoint are
available, and the property count/configuration digest still match. The saved
record is `boot-test.json` in the platform state directory. Capture that record
and the host OS/hardware details as release evidence. **Production support for a
target remains incomplete until this succeeds on that target.**

## Platform Differences

| Area | Ubuntu Server | Apple Silicon Mac mini |
| --- | --- | --- |
| Application runtime | Docker Engine / Compose from Ubuntu packages | Native Python 3.14 virtual environment |
| Service manager | systemd | system LaunchDaemons (`launchd`) |
| Application state | `/var/lib/concierge`, persistent Docker volume | `/Library/Application Support/Concierge.AI` |
| Local endpoint | `127.0.0.1:8080` through Nginx | `127.0.0.1:8080` through native loopback proxy |
| Optional local AI | Host Ollama endpoint; Concierge does not require it | Managed Ollama LaunchDaemon, explicitly enabled |
| Platform updates | Ubuntu unattended security updates; pinned application release command | Python.org signed package maintenance; pinned application release command |

Both targets use the same application code, SQLite database behavior, health
endpoints, backup format, update command, and bounded recovery policy. Service
installation and host runtime setup stay isolated under `deploy/linux/` and
`deploy/macos/`.
