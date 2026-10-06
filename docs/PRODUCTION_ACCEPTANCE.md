# Supported-platform production acceptance

This is a hands-on acceptance procedure. Record the operator, date, release,
OS build, hardware architecture, and evidence for every run. **No clean-host
install, reboot, update/rollback, or off-host restore is certified by this
document alone.** The current repository audit has not run the appliance flow
on a physical Ubuntu host or an Apple Silicon Mac mini.

Run Ubuntu acceptance independently on each supported Ubuntu Server LTS and
architecture combination: 24.04 amd64, 24.04 arm64, 26.04 amd64, and 26.04
arm64. Run macOS acceptance on an Apple Silicon Mac mini for each macOS release
the product claims to support. Use disposable hosts and an acceptance-only
release repository for destructive or intentionally failing scenarios.

## Ubuntu Server

1. Prepare a clean Ubuntu Server host. Record `lsb_release -a`, `uname -m`,
   available disk (`df -h /`), and the host hardware. Confirm the required
   outbound access to Ubuntu package mirrors, GitHub Releases, Docker Hub, and
   PyPI. Do not copy production credentials or data to this host.
2. Install from the published stable release:

   ```bash
   curl --fail --silent --show-error --location \
     https://github.com/jasongil003/Concierge.Ai/releases/latest/download/concierge-install.sh \
     | sudo bash
   ```

   Complete the prompts with acceptance-only DNS, SG5 processor, administrator
   network CIDRs, and a unique administrator password. Confirm the installer
   created the root-owned application under `/opt/concierge`, the systemd unit,
   persistent state volume, and a protected configuration file. Do not record
   secret values in acceptance evidence.
3. Complete first-run setup. Create a property and at least one known record in
   Admin, sign out and back in, and confirm that the property and record remain.
   Run `sudo concierge doctor`. Check the liveness, readiness, and minimal
   public version endpoints:

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:8080/health/live
   curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
   curl --fail --silent --show-error http://127.0.0.1:8080/health/version
   ```

   Confirm the version response has exactly `status` and `version`. Sign in as
   Platform Admin and confirm `GET /api/admin/system/diagnostics` reports
   sanitized dependency status. Confirm non-platform roles cannot open global
   `/health/details`. Record the doctor output and sanitized API results.
4. Verify automatic startup and data persistence. Run
   `sudo concierge boot-test prepare`, record the saved boot-test state, and
   reboot with `sudo systemctl reboot`. Do not manually start Docker or
   Concierge. Reconnect after startup, run `sudo concierge boot-test verify`,
   `sudo concierge doctor`, and repeat the three health requests. Confirm the
   boot ID changed, services recovered automatically, and the property and
   known record remain.
5. Create and verify a local backup with `sudo concierge backup`. Record its
   sanitized path, checksum, and verification result. Complete the separate
   [off-host disaster recovery rehearsal](DISASTER_RECOVERY_REHEARSAL.md) on a
   clean environment before marking recovery acceptance complete.
6. On a staging appliance using a separate acceptance repository, install a
   valid, signed stable release and run:

   ```bash
   sudo env CONCIERGE_REPOSITORY=owner/concierge-acceptance concierge update
   ```

   Record current and candidate release identities, schema assessment,
   verified pre-update backup, and post-update doctor/health results. Confirm
   the database schema is within the candidate's declared migration range and
   that no downgrade is attempted.
7. Test rollback with a second signed acceptance-only candidate whose app
   startup intentionally fails before migration. Run the same update command.
   Confirm the previous release pointer is restored, the prior service reaches
   healthy readiness, the database is unchanged, and the pre-update backup
   remains verifiable. Save the exact recovery state and command output. Never
   publish or run this candidate against production data or the production
   release repository.
8. Run `sudo concierge boot-test prepare`, reboot a second time, then run
   `sudo concierge boot-test verify`, `sudo concierge doctor`, and the health
   checks again. Confirm data persistence across the update and second reboot.
   Save sanitized outputs, deployment manifest, boot-test records, backup
   verification, and the acceptance-only rollback evidence.

## macOS on Apple Silicon

1. Prepare a clean, disposable Apple Silicon Mac mini on a supported macOS
   release. Record `sw_vers`, `uname -m`, free disk (`df -h /`), and hardware.
   Confirm outbound access to GitHub Releases, Python.org, and PyPI. Do not use
   a logged-in graphical session to start the services or copy production data
   and credentials to the host.
2. Install from the published stable release using the same bootstrap command:

   ```bash
   curl --fail --silent --show-error --location \
     https://github.com/jasongil003/Concierge.Ai/releases/latest/download/concierge-install.sh \
     | sudo bash
   ```

   Complete the acceptance-only prompts. Confirm the Python.org package
   signature is accepted, the locked `_concierge` account and virtualenv are
   installed under `/opt/concierge`, and the server/proxy LaunchDaemons are
   registered. Keep configuration values out of recorded output.
3. Complete first-run setup and create a property with a known record. Run
   `sudo concierge doctor`, then check:

   ```bash
   curl --fail --silent --show-error http://127.0.0.1:8080/health/live
   curl --fail --silent --show-error http://127.0.0.1:8080/health/ready
   curl --fail --silent --show-error http://127.0.0.1:8080/health/version
   ```

   Confirm the public version response contains only `status` and `version`.
   Using a Platform Admin session, validate sanitized
   `/api/admin/system/diagnostics`; validate global health details are denied
   to all property roles and guests.
4. Validate the macOS PDF RSS guard with the approved, non-production
   memory-expansion PDF fixture from the QA evidence bundle. Upload it through
   Knowledge Management on a disposable property while monitoring the worker
   process RSS. Confirm the worker is terminated at the configured
   `KNOWLEDGE_PDF_MEMORY_LIMIT_BYTES` ceiling, the request returns the
   controlled memory-limit message, Concierge remains healthy, and no worker
   remains. Also upload a small valid text PDF and confirm extraction succeeds.
   Record the configured limit and sanitized outcomes, not document contents.
5. Run `sudo concierge boot-test prepare`, reboot with
   `sudo shutdown -r now`, and do not sign in or start services manually.
   Reconnect after boot, run `sudo concierge boot-test verify` and
   `sudo concierge doctor`, repeat the health checks, and confirm the property
   and known record remain.
6. Run `sudo concierge backup`; record the checksum and verification result.
   Complete the separate off-host disaster recovery rehearsal before marking
   recovery acceptance complete.
7. On the disposable machine, validate a compatible signed candidate update
   from the acceptance-only release repository. Record the schema assessment,
   pre-update backup verification, and post-update health. Then update to a
   separately signed candidate designed to fail app startup before migration.
   Confirm the prior release pointer and service recover, the database was not
   downgraded or altered, and the verified backup remains available. Never run
   this intentional failure against production data or releases.
8. Run `sudo concierge boot-test prepare`, reboot again, verify with
   `sudo concierge boot-test verify`, and check doctor, health, and persistence.
   Store the sanitized diagnostics, PDF worker observations, backup result,
   release/schema evidence, rollback result, and both boot-test records.

## Acceptance result

For each target combination, mark each step PASS, FAIL, or NOT RUN and attach
sanitized evidence. A target is not production-accepted until install, startup,
reboot recovery, backup, compatible update, intentional pre-migration rollback,
second reboot, persistence, and clean-environment disaster recovery all pass.
Unit tests and static validation do not substitute for this host-level run.
