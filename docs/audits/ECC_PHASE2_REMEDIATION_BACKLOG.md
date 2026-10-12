# ECC Phase 2 remediation backlog

| Priority | Item | Exit evidence | State |
| --- | --- | --- | --- |
| P0 | Keep server-side action confirmation independent from model output. | Invalid, expired, replayed, cross-session, and cross-property action tokens are rejected; no state change from stream events. | Locally covered; retain in CI. |
| P1 | Guest expiry/revocation concurrency matrix. | Repeat sliding renewal, cookie/database agreement, revoke-after-auth, concurrent requests on Python 3.12 and PostgreSQL. | SQLite/local verification; external matrix blocked. |
| P1 | Historical transcript encryption migration. | Backed-up, reversible staged migration with key recovery; no record loss. | Existing historical plaintext remains readable until normal retention; migration not run. |
| P2 | Live model-quality benchmark. | Configure approved test provider and record per-case rubric scores for 100 scenarios without real guest data. | Blocked: provider credentials absent; dataset stays `not_run`. |
| P2 | Typed booking/service forms. | Real backend exposes authoritative IDs, availability and validation; explicit confirm; idempotent and property-scoped tests. | Open: no reservation-slot integration; no slots are fabricated. |
| P2 | Map route from verified origin. | Property supplies a guest-authorized origin (e.g. verified location) and route graph; browser shows accessible route and offline fallback. | Open: current map shows stored floor plan and guest-visible markers only. |
| P3 | Operational release acceptance. | Clean install, upgrade, backup/restore, TLS/proxy, restart, rollback, secret recovery on disposable target. | Blocked: target environment unavailable. |
| P3 | File-processing resource acceptance. | Synthetic high-expansion fixture, RSS ceiling, kill/reap, cleanup, service health on each supported OS. | Fixed-unverified pending target OS run. |
| P4 | Accessibility and device acceptance. | WCAG audit, axe/screen reader, Safari and physical iOS/Android/captive-browser evidence. | Partial local browser checks; external checks blocked. |

Retain the versioned protocol and feature gate while these items remain open. Do not enable a property for real guests based only on this local prototype evidence.
