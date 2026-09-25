# 30 — Final production readiness

## Acceptance gates

- [x] backend tests pass: 126 passed
- [x] functional desktop/mobile browser suite: all 157 applicable scenarios pass; 11 project-specific skips
- [x] admin auth backend/browser coverage retained
- [x] stored-XSS desktop/mobile targeted regression passes
- [x] tenant isolation suite passes
- [x] SSRF/outbound network suite passes
- [x] production boot rejects unsafe defaults
- [ ] local Docker image/runtime/health/persistence — daemon unavailable; exact CI gate added
- [x] backup restores database, uploads, requests, configuration, and encrypted credential
- [x] provider fallback and server-side usage limits verified with deterministic adapters
- [x] AI/tool permissions remain below server RBAC; diagnostic tools are read-only and permission checked
- [x] prompt-injection content cannot grant a privileged operation in tested paths
- [x] npm audit: 0 vulnerabilities
- [x] Python dependency audit reviewed; patched pins remove the 29 findings reported against the previous environment
- [x] secret values are filtered from security/provider audit metadata

## Commercial deployment blockers

1. Obtain a green Docker runtime smoke and image security scan.
2. Provision production secrets, TLS termination, property host mappings, live guest-auth integration, and off-host backup retention.
3. Complete measured capacity testing and establish the supported appliance concurrency envelope.
4. Route admin DNS/SSL diagnostics through a dedicated restricted network policy.
5. Decide/reset-token delivery hardening and remove bearer tokens from query strings where the email workflow permits.
6. Pin the base image by digest and define an update cadence.

The repository is materially stronger and P0/P1 controls are implemented, but commercial deployment should remain blocked until the pending Docker, capacity, and operator provisioning gates have evidence.
