# Deployment readiness

**Audit target:** `d5d006e89c38c0d901256d545679fee753175ef8`  
**Date:** 2026-10-14 (Asia/Manila)  
**Recommendation:** internal synthetic demo only until target-host, network, recovery and capacity checks are signed off.

| Area | Repository/test evidence | Status for target deployment |
|---|---|---|
| Ubuntu Server and Apple Silicon Mac mini | Platform-specific installer/service definitions in `deploy/linux/`, `deploy/macos/`, and `deploy/`; installer/config tests are in `tests/test_installation.py` and `tests/test_source_install.py`. | **PARTIAL.** No fresh clean-host install, upgrade, reboot, or rollback acceptance was run here. `systemd-analyze` was unavailable and its test skipped. |
| Docker production packaging | `Dockerfile`, Compose overlays, configuration and static isolation tests; 18 backend skips included service-dependent cases. | **IMPLEMENTED_NOT_VERIFIED** in this run. Earlier isolated container/runtime evidence is documented in `audit/MASTER_SECURITY_REVIEW.md`; it is historical and not re-executed against a current hosted CI image here. |
| PostgreSQL | Migration, query and backup integration tests are present. | **BLOCKED** in this run: 14 PostgreSQL integration/migration/backup test cases skipped because `DATABASE_URL` and/or `PG_DUMP_AVAILABLE` were not configured. No live customer database touched. |
| Redis | Rate-limit and distributed provider bulkhead integrations are present. | **BLOCKED** in this run: two service integration cases skipped because `REDIS_TEST_URL` was not configured. |
| Local AI/Ollama | Adapter and configuration support exists. | **IMPLEMENTED_NOT_VERIFIED.** No local model service or resource profile was provisioned. |
| HTTPS, canonical guest host, reverse proxy, management VLAN | Proxy/Nginx configuration and local security tests exist. | **BLOCKED** on real hotel hostnames, certificate, proxy trust chain, CIDRs and pre-auth allowlist. No production deployment configuration was changed. |
| Persistent storage and restart | Persistence/backup code and local tests exist. | Unit-level checks passed; actual target reboot and hardware failure recovery remain unverified. |
| Backup and restore | SQLite/PostgreSQL backup tooling and tests exist. | PostgreSQL backup/restore integration skipped in this run. Prior reports flag encrypted off-host backup and key recovery as incomplete; local checks do not close that requirement. |
| Progressive capacity (100, 1k, 5k, 10k, 30k) | Isolated load tooling and Compose overlays exist. | **BLOCKED.** No load run in this audit, no measured latency/throughput/resource profile, and no capacity claim. |

## Resource and safety limits

The backend suite used isolated temporary SQLite state and its persistent-database guard reported the workspace database unchanged. Playwright used its own temporary database and host environment allowlist. This audit did not start Docker workloads, change deployment files, touch production data, or run disruptive load tests.
