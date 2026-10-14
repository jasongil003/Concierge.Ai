# Security findings

**Audit target:** `d5d006e89c38c0d901256d545679fee753175ef8`  
**Date:** 2026-10-14 (Asia/Manila)  
**Scope:** source review, current unit/regression tests, Playwright coverage, and limited static checks. This is not a hotel deployment certification.

## Findings and disposition

| ID | Severity / status | Evidence | Action |
|---|---|---|---|
| SEC-H01 — historical execution credential | **High exposure; unresolved outside this workspace** | `audit/MASTER_SECURITY_REMEDIATION_REVIEW_2026-10-13.md` records a real execution-environment credential in reachable history, with three historical detections. This audit did not print or revalidate the value. | Issuer must invalidate it. An authorized repository owner must sanitize all affected history and verify all refs/forks/caches. Current-tree redaction is not equivalent to history cleanup. Release blocker. |
| SEC-H02 — guest location privacy lifecycle | **High pilot risk; incomplete requirement** | Prior release review identifies consent/retention/checkout/opt-out/deletion as incomplete for property-scoped location observations. AP association provides coarse zone signals, not exact coordinates (`docs/ANTLABS_INTEGRATION.md`). | Approve privacy policy, implement the whole lifecycle, and add negative/expiry/export/isolation tests before a hotel pilot. |
| SEC-M01 — required CI checks on main | **Medium governance risk; needs remote recheck** | Read-only repository metadata recorded in the 2026-10-13 security review showed branch protection and required checks disabled. GitHub metadata could not be fetched in this audit. | Repository administrator must verify and enforce rules. No settings were changed. |
| SEC-M02 — Bandit SQL construction alerts | **Medium scanner severity; reviewed as non-exploitable fixed fragments** | `bandit -q -r app -ll` reports two B608 alerts at `app/properties.py:595` and `app/properties.py:771`. Both SQL column names are drawn from the class's fixed `COLUMNS` tuple; data values are passed as bound parameters at lines 752 and 772. Scan had zero High findings. | Keep parameter binding and regression coverage. Alerts were not suppressed. Revisit if SQL identifiers become request-controlled. |
| SEC-M03 — source install and local-demo boundaries | **Fixed in audited commit; regression verified** | `app/config.py:235-272` rejects a known local-demo encryption secret and `demo-*` bootstrap usernames in production/staging. `scripts/seed_local_demo.py:23-39,514-520` accepts only the expected HTTP loopback origin. `tests/test_security_remediation.py` and `tests/test_local_demo_isolation.py` pass. | Keep tests. This does not approve any real deployment profile. |
| SEC-M04 — property-media symlink escape | **Fixed in audited commit; regression verified** | `app/main.py:1479-1518` rejects symlinked property/media directories and verifies resolved file scope. `tests/test_local_demo_isolation.py` verifies cross-property symlink rejection and a valid hash-named response. | Keep the property-scope regression. No authorized hotel image rights were evaluated. |

## Tested boundaries

- Full backend suite: **1,180 passed, 18 skipped, 0 failed**. The skipped PostgreSQL, Redis, Linux memory-limit and systemd-analysis checks are listed in `TEST_EXECUTION_RESULTS.md`.
- Admin authentication, RBAC and property/department isolation, guest expiry/revocation, CSRF/origin and host policy, upload validation, outbound URL validation, publication permissions, and XSS regressions are in the current test set.
- Playwright stored-XSS regression passed. All nine responsive matrix checks passed after the missing-favicon fix; the complete E2E run before that fix had only those nine identical favicon 404 failures.
- `npm audit --offline --json`: zero advisories in the lockfile's 3 dependency entries.
- `pip-audit` did not complete: it could not upgrade its temporary audit tooling because package-network access was unavailable. No clean Python advisory result is claimed for this run.
- `bandit -q -r app -ll`: 2 B608 Medium alerts described above, 0 High alerts; additional parser and `# nosec`-use warnings were emitted.

## Not established

No exhaustive Git-history scan was available in this run; the historical credential finding remains a blocker. No production database, live gateway, provider, hotel network, or real guest data was accessed. Local test passes do not establish complete protection against unknown payloads or deployment mistakes. Property-specific location retention, external-provider privacy policy, TLS/proxy/CIDR configuration, and real device/session behavior still require acceptance.
