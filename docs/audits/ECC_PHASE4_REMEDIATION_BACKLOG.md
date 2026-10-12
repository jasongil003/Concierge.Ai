# ECC Phase 4 remediation backlog

| Priority | Finding / work | Required evidence to close | Status |
| --- | --- | --- | --- |
| P0 | `ECC-HIST-001`: transcript key ring and safe rotation | Isolated synthetic migration, mixed-key reads, interrupted resume, write failure atomicity, rollback to legacy formats, and escrow recovery fixture pass. Keep the actual off-host escrow and PostgreSQL rehearsal separate. | **Implementation FIXED-VERIFIED; target recovery remains open** |
| P1 | `FILE-DOS-01`: platform-specific PDF resource enforcement | Run on each target OS; prove configured OS limit, observed RSS, timeout/CPU behavior, worker termination/reaping, temporary cleanup, and parent health with bounded synthetic PDFs. | **FIXED-UNVERIFIED** |
| P1 | `ECC-OPS-001`: install, upgrade, backup, restore, and rollback | Disposable target install/upgrade; checksum-verified backup; restore into an empty environment; recover encryption keys from off-host escrow; TLS/proxy health; legacy rollback. | **BLOCKED** |
| P1 | `ECC-PERF-001`: performance and capacity | Pilot owner defines SLOs; capture sufficient-sample p50/p95/p99 for browser, DB, provider, streaming, concurrency, resource use, errors, and recovery on representative hardware. | **BLOCKED** |
| P1 | Live AI validation | Explicitly authorize a synthetic provider test credential/data transfer; run and preserve the 100-case per-case report, latency, property isolation, injection, and unauthorized action outcomes. | **NOT RUN pending authorization** |
| P1 | PostgreSQL/Redis acceptance | Run disposable service migration/isolation/concurrency/expiry/rate-limit/bulkhead/restart/backup/restore tests; no shared or production endpoint. | **BLOCKED: local services unavailable** |
| P1 | SSE reverse-proxy acceptance | Test candidate behind target proxy with live/fake provider evidence distinguished, event ordering, first-event latency, cancellation, idle timeout, interruption, concurrency, and fallback. | **BLOCKED: no proxy/target** |
| P2 | Accessibility and real-device readiness | Automated accessibility audit plus physical iOS/Android/Safari/captive-browser and screen-reader checks at required viewport sizes; record WCAG 2.2 AA issues. | **Partially covered by existing browser evidence; devices not tested** |
| P2 | Dependency/secret/container scans | Obtain successful CI-equivalent npm/pip audits, Gitleaks scan, and Trivy image scan from a network-enabled runner with exact candidate SHA. | **Partially blocked by network/tool availability** |
| P2 | GitHub/CI current status | Restore GitHub DNS/network access and query live `main`, workflow run, and CI jobs; current review uses local tracking refs only. | **BLOCKED by DNS/network** |
| P2 | `ECC-UI-006`: mobile recommendation detail label | Retain the initial sanitized failure evidence and monitor future browser runs; four targeted reruns and the complete retry-enabled suite passed without recurrence. | **NOT REPRODUCIBLE; monitor** |

Do not promote operational findings based only on local unit or browser tests. See the runbooks in `docs/intelligent-ui/` for reproducible staging acceptance steps.
