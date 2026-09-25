# 28 — Docker runtime verification

Local status: **FIXED — VERIFICATION PENDING**.

Docker CLI 29.7.2 is installed. `docker build -t concierge-ai:remediation-baseline .` was attempted, but Docker Desktop's Linux engine pipe was absent, so no local image/container claim is made.

CI now builds the production image and runs `scripts/docker_smoke.py`. The job verifies UID is nonzero, Docker health reaches `healthy`, readiness and protected detailed health, admin login, database creation/write, trusted host binding, guest session, service request, KB persistence, XLSX generation, AI configuration persistence, and state survival after container removal/recreation with the same volume. Logs are uploaded to the job output on failure.

The production compose file now sets production environment, secure cookies, body-property selection off, debug off, `/state` database/uploads, non-root runtime, healthcheck, and persistent volume. `docker-compose.dev.yml` is the explicit developer override.

Residual risk: this CI workflow must complete successfully before the Docker finding can become **FIXED AND VERIFIED**. Restart-policy behavior and image vulnerability scanning remain pending.
