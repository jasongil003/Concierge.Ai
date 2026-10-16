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

Use an Apple Silicon Mac mini