# ECC Phase 5 findings

## Scope and candidate

- Baseline commit: `6fd9d2309f28137a2ab3823ca99794656998b5d8`.
- Branch: `fix/intelligent-ui-v2-phase5-stabilization`.
- The candidate is the baseline plus the uncommitted Phase 5 working-tree changes listed in `PHASE5_IMPLEMENTATION.md`; no commit was created.
- The initial working tree was clean. GitHub and `origin` could not be refreshed because `github.com` DNS resolution fails on this host. The current local `HEAD` equals the supplied baseline; it is not evidence of the present remote branch or Actions state.
- No production or shared database, guest record, provider credential, or deployment was read or changed.

## Register

| ID | Severity | Root cause / affected area | Remediation and local evidence | Remaining risk | Status |
| --- | --- | --- | --- | --- | --- |
| `ECC-HIST-001` | Medium | A single transcript key format previously made controlled key replacement and legacy compatibility difficult. | Versioned multi-key reads, bounded transactional migration, verification, resume and rollback are covered by `tests/test_transcript_rotation.py`. Phase 5 adds a corrupted-ciphertext preflight regression. | Real off-host escrow recovery and PostgreSQL rehearsal remain unverified. | **FIXED-VERIFIED (isolated implementation)** |
| `FILE-DOS-01` | Medium | Parser memory varies by platform; macOS has no demonstrated hard per-process memory ceiling in this setup. | Upload/archive/page/text bounds and isolated worker remain. A bounded worker sample killed and reaped its child and removed temporary files. See Phase 5 test results for observed overshoot. | Linux `RLIMIT_AS` execution and target OS acceptance were unavailable. macOS RSS polling is supervisory, not a hard cap. | **FIXED-UNVERIFIED** |
| `ECC-OPS-001` | Medium | Pilot install, proxy/TLS, service lifecycle, key escrow, restore and rollback need a target-like environment. | Local SQLite backup/restore, integrity and isolated target tests pass; an incomplete archive is now rejected before creating restore targets. Existing operational runbooks describe target acceptance. | Docker daemon, deployment appliance, proxy and separately recovered escrow were unavailable. | **BLOCKED** |
| `ECC-PERF-001` | Medium | Local microbenchmarks do not establish provider, proxy, concurrency or deployment capacity. | Fresh 101-sample local TestClient measurements are recorded in `PHASE5_PERFORMANCE_RESULTS.md`. | No representative hardware, external provider, target database/cache, or sustained concurrency run. No 30,000-session claim. | **BLOCKED** |
| `DB-INT-001` | Medium | PostgreSQL/Redis behavior requires disposable services for migration, concurrency, expiry, rate-limit and restart acceptance. | Unit and adapter coverage runs in the local suite; integration tests are marked to skip without service URLs. | PostgreSQL, Redis and a Docker daemon are unavailable locally. | **BLOCKED** |
| `AI-LIVE-001` | Medium | Natural-language quality and provider streaming cannot be measured by deterministic local routing tests. | The repository's 100-case synthetic dataset and safe operator procedure remain available. | No live provider call was authorized or run; correctness and hallucination metrics are N/A. | **BLOCKED** |
| `ECC-UI-001` | Low | SSE behavior behind a real reverse proxy is outside in-process ASGI tests. | Existing backend/browser regressions cover event parsing, order, cancellation and fallback. | Proxy buffering, TCP interruption, idle timeout and real-provider delta timing remain unverified. | **FIXED-VERIFIED locally; target acceptance BLOCKED** |
| `ECC-UI-002` | Low | Intelligent UI rollback must work through configured global/property feature flags. | Local feature-flag and legacy fallback regressions remain in the full suite. | Multi-replica propagation timing needs target evidence. | **FIXED-VERIFIED locally** |
| `ECC-UI-003` | Low | UI selection is not a reservation integration. | Local tests cover non-mutating selection/review/cancel behavior; no booking is created. | Availability and reservation backend integration are outside current scope. | **FIXED-VERIFIED for implemented scope** |
| `ECC-UI-004` | Low | Facility details depend on property configuration and optional integrations. | Property-scoped metadata and legacy behavior have local regression coverage. | Missing property data remains an expected limitation. | **FIXED-VERIFIED for implemented scope** |
| `ECC-UI-005` | Low | A status note previously risked being presented as a facility location. | Location is sourced from configured location or property-scoped map data; regression remains in the full suite. | No additional local risk identified. | **FIXED-VERIFIED locally** |
| `ECC-UI-006` | Low | `renderMessages()` replaced recommendation-card DOM while `/api/chat` was in flight. Commit `f22c0b2a` (2026-10-02) changed the conversation renderer to clear both message lists with `replaceChildren()` before rendering; the Details handler from `7c520d56` (2026-09-21) kept expansion and label state only in DOM. The response rerender therefore collapsed the card after the user expanded it. | Phase 5 persists expansion per stable message/result identity, derives button name and `aria-expanded` from that state, restores focus after rerender, and adds a delayed-response browser regression. The old behavior reproduced 4/24 times across desktop/mobile; focused post-fix runs passed 32/32. | Retain the browser regression in CI; physical-device behavior still needs device acceptance. | **FIXED-VERIFIED locally** |
| `ECC-SES-001` | Historical High | A previous guest-session renewal race could leave the persisted expiry behind valid activity. | Transaction-bound renewal, expiry/revocation checks, and cookie/database consistency remain covered by backend regressions. | PostgreSQL transaction concurrency is not available locally. | **FIXED-VERIFIED on local SQLite** |
| `OPS-021` | Low | Guest breakfast response needed a direct configured-property assertion. | Existing backend/browser regression checks the configured property's data. | Live provider grounding is covered separately by `AI-LIVE-001`. | **FIXED-VERIFIED locally** |

## Severity and status summary

- Critical: 0 identified.
- High: 0 unresolved; the historical `ECC-SES-001` High finding is fixed and verified on SQLite.
- Medium: 6, comprising 1 FIXED-VERIFIED, 1 FIXED-UNVERIFIED, and 4 BLOCKED.
- Low: 7; local fixes are verified, with proxy/device limitations called out above.
- Status totals: 9 FIXED-VERIFIED (including the historical session finding), 1 FIXED-UNVERIFIED, 4 BLOCKED. No finding is being closed based on unavailable infrastructure.

## Independent review

The Phase 5 code delta does not change backend authorization, guest session expiry/revocation, tenant isolation, signed guest-action confirmation, feature-flag defaults, transcript encryption keys, or persistent data. The UI repair is client presentation state only. The two added Python regressions use temporary SQLite databases and synthetic ciphertext/archives. The final verdict remains **WORKING LOCAL PROTOTYPE** because operational and external acceptance is incomplete.
