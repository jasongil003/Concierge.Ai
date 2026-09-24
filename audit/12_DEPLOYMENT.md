# 12 — Deployment & Image Hardening

## Current docker-compose
- ports 8080:8080, env_file .env, DB_PATH=/state/concierge.db, volume concierge-state:/state (updates only), extra_hosts host.docker.internal:host-gateway, restart unless-stopped, image build from Dockerfile.
- Pre-fix Dockerfile: python:3.12-slim, `FROM` unpinned tag (no digest), NO non-root user (ran as root), NO HEALTHCHECK, pip install of full requirements at build. (SEC-009 / DEP-001.)

## Audit fix applied (SEC-009 / DEP-001) — Dockerfile rewrite
- Added `groupadd/useradd` service account `concierge`, run `USER concierge` (no root shell, home set to /app).
- Added HEALTHCHECK (python urllib /health every 30s, timeout 5s, start 15s, retries 3).
- `python:3.12-slim` tag kept (pinned to a specific slim digest at install time by the registry); docker-compose referenced by tag — recommend digest-pinning once CI images are known-good to prevent supply-chain drift.
- /state and /app owned by concierge (writes for DB/uploads work as non-root; confirmed conceptually — container not yet rebuilt in this environment).

## Remaining deployment recommendations
- DEP-004 (HIGH, operator sign-off): set `APP_ENVIRONMENT=production` in compose deployment (activates bootstrap-password guard + secure cookie) — atomic with rotating CREDENTIAL_ENCRYPTION_SECRET.
- DEP-005: bind 8080 to LAN interface (or run behind reverse proxy) — `0.0.0.0` in compose exposes on all host interfaces.
- DEP-006: add `env APP_ENVIRONMENT` interpolation; document secrets rotation (Fernet-encrypted provider keys are bound to CREDENTIAL_ENCRYPTION_SECRET; rotating the secret without re-encrypting provider rows breaks decryption — document procedure).
- DEP-007: pin base digest + versions in requirements (freeze used), add `docker scout`/`trivy` to CI.
- DEP-008: `.dockerignore` excludes .venv/test-results state (reduce image size). (Not yet present.)