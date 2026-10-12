# ECC Phase 6 Remediation Backlog

| Priority | Finding / gate | Required evidence to close | Current status |
| --- | --- | --- | --- |
| P1 | `DB-INT-001` PostgreSQL/Redis | Run `scripts/phase6/acceptance.sh start`, `test`, restart/outage checks, migration and synthetic backup/restore on Linux; attach sanitized logs and exact SHA. | **BLOCKED**: no Docker daemon or native services. |
| P1 | `ECC-OPS-001` install/recovery | Fresh Linux install, previous-release upgrade, health/restart/rollback, persistent data, backup and restore with independently recovered synthetic keys. | **BLOCKED**: no Linux target. |
| P1 | `ECC-HIST-001` key recovery | Put test keys in a separately controlled test escrow, interrupt/resume rotation, restore into a new disposable environment and verify transcripts. | Code path locally covered; operational recovery **BLOCKED**. |
| P1 | `AI-LIVE-001` | Obtain explicit provider/dataset authorization, configure provider/model and budget limits, run the existing 100-case benchmark, retain case-level safety/correctness/timing evidence. | **BLOCKED**: no authorized provider configured. |
| P1 | `ECC-UI-001` proxy/SSE | Run the actual Nginx deployment config, measure browser first-event/delta timing, cancellation, buffering, timeout, property isolation, and rollback. | Local endpoint tests only; proxy **BLOCKED**. |
| P1 | `FILE-DOS-01` Linux resource bounds | Bounded synthetic PDF run in Linux; verify `RLIMIT_AS`, CPU/wall limits, parent RSS supervision, worker reap/temp cleanup, then successful extraction. | **FIXED-UNVERIFIED** on Linux. |
| P2 | `ECC-PERF-001` capacity | Bounded load on representative target hardware with concurrency, duration, p50/p95/p99, failure rate, saturation, recovery, and explicit uncertainty. | **BLOCKED**; local ASGI sample is not capacity evidence. |
| P2 | Accessibility/device | Physical Safari/iOS, Android, tablet, QR/NFC/captive portal and assistive-technology check against WCAG 2.2 AA. | **BLOCKED**; browser emulation only. |
| P2 | Supply-chain checks | Re-run npm/pip audits and Gitleaks/Trivy with registry/network access and exact candidate source/image; inspect findings without threshold changes. | npm/pip audit **BLOCKED** by DNS; Gitleaks/Trivy unavailable. |
| P2 | GitHub status | Refresh `origin/main`, verify exact candidate commit and relevant Actions checks using authorized GitHub access. | **BLOCKED** by DNS from this host. |

No backlog item is closed solely because the SQLite or mocked unit suite passes.
