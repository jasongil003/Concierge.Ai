# Production Security Checklist

Use this checklist before routing any public traffic to a production Concierge.AI deployment. Code-level items marked **Verified in repository** were checked during this audit. Items requiring the operator or infrastructure team remain unchecked until verified in the live environment.

## Application secrets and accounts

- [ ] Set a unique random `ADMIN_BOOTSTRAP_PASSWORD` of at least 12 characters; do not reuse the former `ChangeMe123!` value.
- [ ] Confirm every existing administrator account has a unique rotated password. The bootstrap variable does not rotate an already-created account.
- [ ] Generate a unique random `CREDENTIAL_ENCRYPTION_SECRET` of at least 32 characters and back it up securely. Keep it stable for existing encrypted provider credentials; rotation requires a credential migration plan.
- [ ] Set a unique random `METRICS_TOKEN` of at least 32 characters.
- [ ] Keep `APP_DEBUG=false`, `ALLOW_BODY_PROPERTY_SELECTION=false`, `ALLOW_DEMO_SETTINGS=false`, and `ADMIN_COOKIE_SECURE=true`.
- [ ] Set `ANTLABS_MODE` to the real integration mode; never use `mock` in production.
- [ ] Protect the `.env` file and backups with host-level access controls. Do not commit it or copy real credentials into audit logs.

## Hostnames, TLS, and reverse proxy

- [ ] Use a canonical DNS hostname for the application. Set `CANONICAL_HOSTS` to exact hostnames only; do not include the public IP, wildcard names, ports, or URL schemes.
- [ ] Set `PUBLIC_BASE_URL` to the public HTTPS origin for password-reset links.
- [ ] Install and externally verify a valid TLS certificate at the trusted reverse proxy; verify hostname, chain, renewal, redirects, and HSTS behavior.
- [ ] Terminate HTTPS at the trusted proxy and keep the Compose HTTP listener bound to loopback (`127.0.0.1:8080`). Do not publish the API or proxy listener directly to the Internet.
- [ ] Configure the trusted TLS proxy to overwrite `X-Forwarded-For` and set `X-Forwarded-Proto` from the actual connection.
- [ ] Set `FORWARDED_ALLOW_IPS` to exact proxy socket addresses. Never use `*`.
- [ ] Verify the address chain seen by the app with controlled requests from an allowed and denied network; spoofed forwarding headers must not change either result.
- [ ] Verify direct `https://PUBLIC-IP/admin` fails the canonical Host check. Serve administrator access only by canonical hostname through the trusted TLS boundary.

## Administrator access and RBAC

- [ ] Set `ADMIN_ALLOWED_CIDRS` to only the VPN or management VLAN addresses that need access. Never use `0.0.0.0/0` or `::/0`.
- [ ] Review the saved Management Access policy in the deployed database as well as the environment value. A saved policy can override the environment default; a Super Admin can deliberately set a global range or disable the restriction after an explicit warning.
- [ ] Verify the public/guest VLAN is not included in admin CIDRs. Production code also excludes configured guest network CIDRs from management access.
- [ ] Test each deployed role against direct API routes, not only hidden UI controls. Verify cross-property access returns 403.
- [ ] Enable MFA or an upstream identity-aware access proxy if available; local password login remains the application authentication mechanism.
- [ ] Confirm failed-login, password-reset, and session-revocation audit events are retained and reviewed.
- [ ] Keep `/docs`, `/redoc`, and `/openapi.json` disabled in production/staging. **Verified in repository.**
- [ ] Verify `/metrics` and detailed health endpoints are unavailable from public and guest networks.

## ANTlabs and guest sessions

- [ ] Configure the actual SG5 built-in processor endpoint and POST method; production startup checks the endpoint shape, but it does not prove the live gateway integration.
- [ ] Configure the ANTlabs signing secret and exact gateway source CIDRs. Keep the secret out of UI exports and logs.
- [ ] Run a live signed assertion test to confirm the gateway signs the raw request body, timestamp, nonce, and property ID exactly as expected.
- [ ] Verify a captured gateway assertion cannot be replayed. **Atomic nonce replay rejection is verified in repository tests; live SG5 behavior remains unverified.**
- [ ] Validate whether the target SG5 can supply a stable, signed guest/device/session identifier on every request. The current Concierge session stores a verified gateway session identifier when the signed integration supplies one, but it does not infer ANTlabs authentication from the browser handoff.
- [x] Resolve GUEST-SESSION-01 in application code: session IDs alone are rejected; guest token and context credentials are hashed, expire, revoke, rotate on resume, and are set in HttpOnly cookies. Real SG5 binding remains deployment-dependent.
- [ ] Verify guest network ranges and admin network ranges do not overlap; keep the guest network isolated from management and database networks.

## Files and AI

- [ ] Keep per-file upload, per-property quota, ZIP entry/expanded-size, compression-ratio, image-pixel, and extracted-text limits appropriate for the deployment.
- [ ] Resolve FILE-DOS-01 by processing PDFs in a memory/CPU/time-limited worker and stopping extraction at the text budget.
- [ ] Review and approve uploaded knowledge before publication. Treat uploaded material as untrusted; do not use documents as policy or system instructions.
- [ ] Keep provider credentials in the encrypted provider store and rotate any credential whose encryption key may have been a former default.
- [ ] Configure `OLLAMA_BASE_URL` and `LOCAL_AI_ALLOWED_ENDPOINTS` only for operator-approved endpoints.
- [ ] Before enabling a live AI model, run a property-approved prompt-injection evaluation using synthetic content. Local tests verify guardrails and server-side tool permissions but do not guarantee model-level resistance.
- [ ] Confirm the assistant cannot change admin state without the existing permission check and explicit confirmation flow.

## Database, backups, and operations

- [ ] Keep the production database on a persistent volume with restrictive ownership and permissions; confirm the container runs as non-root. **Container user is verified in repository; runtime ownership still requires deployment validation.**
- [ ] Encrypt backup storage, restrict restore credentials, and test restore to a clean isolated environment. Backup/restore path and tenant tests pass locally.
- [ ] Keep a tested rollback and credential/key recovery procedure. Avoid copying production data into development or audit test environments.
- [ ] Confirm application, Nginx, host, database, and backup logs do not record passwords, reset tokens, session tokens, provider keys, guest personal data, or raw authorization headers.
- [ ] Configure monitoring and alerting for repeated admin login failures, rate limits, cross-property denials, failed gateway signatures, unusual upload volume, and provider endpoint failures.
- [ ] Preserve the single API worker/instance requirement for the SQLite Compose profile. Use Redis/shared rate limits and a supported server database before increasing replicas.
- [ ] Run `pip-audit`, `npm audit`, secret scanning, and an image scanner on every release. CI defines these checks; the current local dependency audits were blocked by unavailable package/advisory network access, and image scanning still needs a Docker runner.
- [ ] Build and run the exact production image in CI with Docker, then run Trivy or an equivalent image scanner before production deployment.
- [ ] Pin or otherwise monitor base-image versions and rebuild promptly when the Python, Nginx, or OS image receives security updates.

## Go/no-go

**Current result: NO-GO for public production exposure.** Guest session ID replay is fixed in this checkout. Validate PDF processing limits, supply and verify production networking/TLS/CIDR values, test the real ANTlabs gateway contract, complete current dependency and Docker/image scans, and verify backup/restore before opening `/admin` or guest traffic to the public Internet.
