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

Checks completed in this checkout: `pytest -q` reported 896 passed and 17
skipped, with 2 warnings; installer shell syntax and ShellCheck passed; all
macOS LaunchDaemon property lists passed `plutil -lint`; deployment Python
files compiled; Bandit passed; Docker Compose configuration parsed; and the
CI-mode Playwright browser suite reported 257 passed and 35 skipped. Dependency
vulnerability audits could not complete because package-registry access was
unavailable. Docker runtime and `systemd-analyze` host checks are unavailable
on this Mac. Hosted CI jobs have not run for this change yet. These checks do
not count as a real reboot acceptance test.

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
not an off-host backup.

Create and verify a backup on demand with:

```bash
sudo concierge backup
```

## Updates

Start troubleshooting with `concierge doctor`; it reports the active runtime,
release identity, listener owner, service state, and readiness separately from
liveness. `concierge status` gives a concise summary. Both commands are
read-only. The app also exposes `GET /health/version` with sanitized build and
schema identity.

The shared command checks the latest stable GitHub Release metadata, downloads
the versioned source archive, verifies SHA-256, and rejects unexpected archive
paths. It verifies a fresh backup before changing the active release, runs the
application migration/import check, restarts services, and waits for healthy
readiness. It restores the previous application release if installation,
migration, or health checks fail; it retains the verified backup and does not
roll a database backward automatically. After pointer rollback it validates
the previous release. If that release cannot read the migrated schema, the
command reports that readiness also failed and keeps the backup for an
operator-led recovery. The current updater switches the `current` pointer
before migration and health validation; it does not promote a candidate only
after readiness passes. Install/update work is protected by a process lock at
`/opt/concierge/.deployment.lock`.

```bash
sudo concierge update
```

The repository must publish a stable `vMAJOR.MINOR.PATCH` GitHub Release with
the generated appliance assets before the bootstrap installer or update command
can run. Development commits and `main` are never auto-installed.

The active deployment manifest is stored at `deployment.json` in the appliance
state directory. It contains version, commit, deployment mode, schema revision,
and install/update timestamps only. Verified backups carry equivalent
application identity and checksums.

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
