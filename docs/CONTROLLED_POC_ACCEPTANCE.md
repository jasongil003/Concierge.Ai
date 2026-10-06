# Controlled POC appliance acceptance

Use this checklist for a disposable, isolated POC appliance before admitting
hotel guests or connecting hotel systems. Record the Concierge commit and
release, OS and hardware versions, operator, date, test property, evidence
locations, and PASS / FAIL / NOT RUN for each item. Use synthetic property,
guest, and credential data and non-production provider accounts. Never put
secrets, guest data, full environment files, or unredacted logs in the evidence
bundle.

This checklist is prepared; it has not been executed on a target appliance or
hotel network. External infrastructure checks below are **POC ENVIRONMENT
ACCEPTANCE REQUIRED**, not code vulnerabilities.

## Common setup and stop conditions

- [ ] Start from a clean disposable appliance and record the tested release
  SHA-256 and deployment configuration.
- [ ] Restrict the appliance to the POC network; keep a tested console or
  recovery path available.
- [ ] Use a unique test-only `CREDENTIAL_ENCRYPTION_SECRET`, admin credential,
  metrics token, AI credential, and disposable database. Store the credential
  secret separately from backups.
- [ ] Record health, sanitized diagnostics, service logs, CPU, memory, disk,
  database, Redis, and queue measurements before each scenario.
- [ ] Stop a test on any tenant/property isolation failure, unexpected guest
  access to admin data, sustained error rate above 1%, p95 latency above the
  approved objective, request timeout, worker failure, database/Redis
  instability, or resource exhaustion. Preserve sanitized evidence and
  investigate before continuing.

## Ubuntu appliance

- [ ] Clean supported Ubuntu installation; record OS and architecture.
- [ ] Reboot; verify automatic service startup and clean shutdown behavior.
- [ ] Verify TLS certificate chain, hostname, trusted reverse-proxy headers,
  and the configured admin CIDR restriction.
- [ ] Verify `/health/live`, `/health/ready`, and `/health/version`; confirm
  public health output contains no secrets or diagnostics.
- [ ] Sign in as the initial administrator, rotate bootstrap credentials, and
  confirm ordinary staff and guest roles cannot access platform diagnostics.
- [ ] Create a synthetic property and verify tenant-scoped admin operations.
- [ ] Open the guest landing page, create a guest session, and exercise the
  guest request flow, QR/NFC entry URL, and session resume.
- [ ] Configure a non-production AI provider; verify a successful response,
  provider failure handling, and credential redaction.
- [ ] If selected for the POC, verify PostgreSQL startup and migrations, Redis
  rate limiting, Redis outage behavior, and recovery after Redis returns.
- [ ] Create an application backup, verify its checksum, and confirm the
  credential-encryption secret is absent from the archive.
- [ ] Apply a valid signed update; verify health, guest/admin flows, and data
  persistence across update and reboot.
- [ ] Stage an intentionally invalid candidate update in the disposable test
  environment; verify it is rejected or rolled back and the prior release,
  data, and service remain usable.
- [ ] Restore a verified backup into a separate clean target and verify
  database rows, uploads, encrypted provider credentials, health, and guest
  and admin flows. Confirm the source appliance remains unchanged.

## macOS appliance

Run the equivalent installation, reboot, automatic startup, TLS/proxy,
health, admin, property, guest, AI, persistence, update, failed-update
rollback, backup, and clean-target restore checks above if macOS remains a
supported POC platform.

- [ ] Verify the packaged service starts on reboot and uses the intended
  unprivileged runtime identity and protected environment-file permissions.
- [ ] Exercise the real PDF worker with a bounded, synthetic document set.
  Record worker RSS, configured memory ceiling, timeout, kill/reap behavior,
  and application health before and after. Do not use sensitive documents.
- [ ] Confirm the same backup and independent key-escrow rules used for
  Ubuntu.

## Hotel network and integrations

These checks depend on the target property's configuration and remain
**POC ENVIRONMENT ACCEPTANCE REQUIRED** until run in that environment.

- [ ] Resolve the production POC hostname through hotel DNS from guest and
  trusted admin networks; confirm the intended split-horizon behavior.
- [ ] Validate public hostname, certificate SANs, expiry, full TLS chain, and
  renewal process from each supported client network.
- [ ] Confirm only the approved reverse proxy can reach the application and
  that forwarded client IP headers are trusted only from that proxy.
- [ ] Verify admin access is denied outside the approved admin CIDRs while
  guest pages remain available on the guest network.
- [ ] Test guest-network detection, captive-portal behavior, and recovery after
  a guest joins hotel Wi-Fi.
- [ ] Scan a synthetic QR code and exercise the NFC entry URL; confirm both
  resolve to the intended property and cannot select another tenant.
- [ ] Verify property host/domain mapping, aliases, redirects, and unknown-host
  rejection.
- [ ] Validate ANTlabs gateway authentication and accounting with a test
  gateway or vendor sandbox. Verify timeout, invalid assertion, replay, and
  gateway-outage behavior.
- [ ] If applicable, validate PMS authentication, property/room mapping,
  guest-session lifecycle, timeout, duplicate event, and outage/recovery with
  a vendor sandbox. Do not use live guest records.

## PostgreSQL, Redis, and disaster recovery

- [ ] Run PostgreSQL application startup and Alembic migration against a new
  disposable database; record exact revision and result.
- [ ] Verify a consistent backup and restore it to an empty, separate target;
  record source and target counts without exposing row contents.
- [ ] Verify Redis-backed guest rate limits across API workers, then stop Redis
  and verify the documented fail-safe behavior; restart Redis and confirm
  recovery without resetting tenant boundaries.
- [ ] Complete the off-host rehearsal in
  [DISASTER_RECOVERY_REHEARSAL.md](DISASTER_RECOVERY_REHEARSAL.md), including
  separate retrieval of the credential-encryption secret and successful
  decryption of a synthetic saved integration credential.
- [ ] Verify the source database and uploads remain unchanged by restore
  testing; clean up disposable target data through the approved process.

## Staged capacity smoke

Run the documented controlled profile only against a disposable test property
with the deterministic mock AI service. The injector should run separately
from the API and database for representative results. Record hardware, image
digests, app commit, database/Redis versions, injector location, workload, and
all stage output. A laptop/shared-host run is diagnostic only.

- [ ] Confirm baseline readiness, CPU, memory, database pool capacity, Redis
  readiness, queue depth, and worker error counters.
- [ ] Run 100 concurrent clients for the configured stage; continue only if
  the stop conditions remain clear and the service returns to baseline.
- [ ] Run 500 concurrent clients only after the 100-client stage is healthy;
  pause and review resource and error measurements before continuing.
- [ ] Run 1,000 concurrent clients only after the 500-client stage is healthy
  and the target has the required dedicated capacity.
- [ ] For every stage record users, duration, requests/sec, request latency
  p50/p95/p99, errors and timeouts, API CPU/RSS, memory growth, PostgreSQL
  connections/pool use, Redis readiness/errors/rate-limit behavior, active
  requests, queue depth, and AI provider queue wait.
- [ ] Record the first degraded stage and stop there. Do not extrapolate to
  30,000 users or production capacity from this smoke test.

## Acceptance record

| Field | Result |
| --- | --- |
| Release commit and artifact SHA-256 | |
| Appliance OS, architecture, CPU, RAM, disk | |
| Database and Redis versions/configuration | |
| Hotel network, proxy, DNS, TLS, gateway/PMS test environment | |
| Operator, reviewer, and date | |
| Failed or not-run checks with reason | |
| Sanitized evidence location | |
| Final POC decision and approver | |
