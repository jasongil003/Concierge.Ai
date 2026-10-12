# ECC Phase 3 remediation backlog

| Priority | Item | Evidence required to close | State |
| --- | --- | --- | --- |
| P0 | Keep guest mutations behind server authorization and explicit signed confirmation. | Existing invalid, expired, replayed, cross-session, and cross-property confirmation tests pass. | Covered locally; retain in CI |
| P1 | Python 3.12 guest expiry/revocation concurrency matrix and PostgreSQL/Redis integration. | Run the security and distributed-store suites on disposable supported services. | Blocked: local interpreter is Python 3.11; services are unavailable |
| P1 | Hard memory-ceiling acceptance for PDF parsing across supported OSes. | Capture OS-enforced or supervised peak RSS, kill/reap, cleanup, and recovery on each supported host. | Fixed-unverified; local macOS sampled RSS exceeded the 96 MiB soft threshold before termination |
| P1 | Deployment/recovery acceptance. | Clean install, additive upgrade, backup/restore, key recovery, proxy/TLS, restart and rollback on a disposable target. | Blocked: target environment unavailable |
| P1 | `ECC-HIST-001`: reversible transcript encryption-key rotation. | Design a dual-key read/write window, backed-up re-encryption job, rollback, and key-recovery tests on a disposable database; retain plaintext compatibility only through normal retention. | Open; no key rotation or bulk rewrite was run |
| P2 | Authoritative restaurant reservation integration. | Approved provider with property-scoped availability IDs, current slot validation, explicit confirmation, idempotency, and verified booking response. | Not implemented; no reservation slots are fabricated |
| P2 | Live AI quality benchmark. | Authorized test provider, all 100 synthetic cases scored per the rubric and saved per case. | Not run; no provider credential or local Ollama service is configured |
| P2 | Provider and target performance acceptance (`ECC-PERF-001`). | Record cold browser load, first-token/full provider latency, encrypted-history behavior with realistic synthetic turns, client memory, query plans, and bounded concurrency on the exact target. | Local in-process route medians/p95 are recorded; provider and target measures are blocked |
| P2 | Reverse-proxy streaming acceptance. | Verify SSE buffering disabled, idle timeout, cancellation propagation, and retry behavior on the target proxy. | Blocked: deployment proxy unavailable |
| P3 | Independent accessibility audit on target assistive technologies. | axe or equivalent WCAG 2.2 AA scan, screen reader/keyboard review, Safari and physical device results. | Partial browser/emulation checks only |
| P3 | External supply-chain and secret scans. | CI or a connected host runs npm/pip audits, Gitleaks, and Trivy against this exact commit. | Blocked locally by unavailable tools/network |

Do not enable Intelligent UI for a real property or treat the worktree as a production release until the remaining target-specific evidence is recorded. See the [release acceptance checklist](../intelligent-ui/RELEASE_ACCEPTANCE_CHECKLIST.md).
