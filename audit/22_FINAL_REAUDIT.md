# 22 — FINAL RE-AUDIT (post-fix acceptance)

Run: post-fix, same harness as audit/02. Git working tree contains the three fixes + 3 regression files; no other product change.

## Acceptance checklist

| Gate | Result |
|---|---|
| pytest (WSL) | 96 passed / exit 0 |
| e2e xss-guard | PASS |
| e2e admin-auth | PASS (12) |
| audit_proof 27 checks | PASS except SEC-007 (documented LOW, no fix) |
| npm audit | 0 vulns |
| Dockerfile rewrite | ok (config-reviewed; CI build pending) |

## Answers to the audit questions (condensed)
1. Production-ready for a single-property on-prem LAN appliance upon completing the DEP-004 operator checklist. Not ready for unbounded internet/multi-brand deployment without SEC-005 pinning + SEC-004 host-binding + DEP-004.
2. Critical fixed; remaining findings are Medium/Low with clear owners.
3. Guest boundary solid for single-property; multi-brand needs host-binding enabled (SEC-004) before reaching it.
4. AI path: injection classifier fixed; provider spend governance (SEC-008) and untrusted-context tagging are the two important follow-ups.
5. Container: non-root + healthcheck fixed; digest pinning and CI/trivy recommended before release.
6. Reliability: app is not HA; healthy for single instance; backup/WAL (DEP-003) must be configured to be disaster-ready.
7. Observability: telemetry exists; metrics endpoint + alert rules recommended (14).
8. Data lifecycle: retention + forget-me + banner language (16/17) recommended before onboarding guest-facing consent program.

## Severity distribution
CRITICAL 1 (fixed) · MEDIUM 9 (2 fixed, 7 open/tracked) · LOW 8 (mostly tracked) · OPS/INFO 5.

## Sign-off conditions
- [ ] Operator executed DEP-004 part 1 (env production + secret rotation)
- [ ] Docker build green in CI with new healthcheck (smoke: `docker inspect --format '{{.State.Health.Status}}'`)
- [ ] Multi-brand: set ALLOW_BODY_PROPERTY_SELECTION=false + host map (SEC-004)
- [ ] Optional: webhook single-resolution (SEC-005) — required only when internet-facing
- [ ] Optional: metrics endpoint on /metrics (14)