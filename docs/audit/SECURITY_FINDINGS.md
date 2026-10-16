# Security findings

**Starting HEAD:** `e4bbd7493fe9d90a513d8224749b54c9e25ddc90`
**Implementation and tested commit:** `a30f95eb8db2ff05151c3473e453f9f38d0dec2d`
**Earlier audit code baseline:** `d5d006e89c38c0d901256d545679fee753175ef8`
**Date:** 2026-10-14 (Asia/Manila)
**Scope:** source review, current unit/regression tests, Playwright coverage, and limited static checks. This is not a hotel deployment certification.

## Findings and disposition

| ID | Severity / status | Evidence | Action |
|---|---|---|---|
| SEC-H01 — historical execution credential | **High exposure; unresolved outside this workspace** | `audit/MASTER_SECURITY_REMEDIATION_REVIEW_2026-10-13.md` records a real execution-environment credential in reachable history, with three historical detections. This audit did not print or revalidate the value; its issuer/audience could not be identified from the sanitized evidence. | The issuing owner must invalidate it. An authorized repository owner must sanitize all affected history and verify all refs/forks/caches. Current-tree redaction is not equivalent to history cleanup. Release blocker. |
| SEC-H02 — guest location privacy lifecycle | **High pilot risk; incomplete requirement** | Prior release review identifies consent/retention/checkout/opt-out/deletion as incomplete for property-scoped location observations. AP association provides coarse zone signals, not exact coordinates (`docs/ANTLABS_INTEGRATION.md`). | Approve privacy policy, implement the whole lifecycle, and add negative/expiry/export/isolation tests before a hotel pilot. |
| SEC-M01 — required CI checks on main | **Medium governance risk; needs remote recheck** | Read-only repository metadata recorded in the 2026-10-13 security review showed branch protection and required checks disabled. GitHub metadata could not be fetched in this audit. | Repository administrator must verify and enforce rules. No settings were changed. |
| SEC-M02 — Bandit SQL construction alerts | **Medium scanner severity; reviewed as non-exploitable fixed fragments** | `bandit -q -r app -ll` reports two B608 alerts at `app/properties.py:595` and `app/properties.py:771`. Both SQL column names are drawn from the class's fixed `COLUMNS` tuple; data values are passed as bound parameters at lines 752 and 772. Scan had zero High findings. | Keep parameter binding and regression coverage. Alerts were not suppressed. Revisit if SQL identifiers become request-controlled. |
| SEC-M03 — source install and local-demo boundaries | **Fixed in audited commit; regression verified** | `app/config.py:235-272` rejects a known local-demo encryption secret and `demo-*` bootstrap usernames in production/staging. `scripts/seed_local_demo.py:23-39,514-520` accepts only the expected HTTP loopback origin. `tests/test_security_remediation.py` and `tests/test_local_demo_isolation.py` pass. | Keep tests. This does not approve any real deployment profile. |
| SEC-M04 — property-media symlink escape | **Fixed in audited commit; regression verified** | `app/main.py:1479-1518` rejects symlinked property/media directories and verifies resolved file scope. `tests/test_local_demo_isolation.py` verifies cross-property symlink rejection and a valid hash-named response. | Keep the property-scope regression. No authorized hotel image rights were evaluated. |

## Historical reference scope

The prior review identifies commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9` as containing three historical detections. The current local `git branch -a --contains` result includes these refs:

- Local branches: `codex/guest-concierge-premium-2026-10-13`, `codex/master-product-audit-2026-10-12`, `codex/security-remediation-2026-10-13`, `fix/ecc-high-rbac-boundaries`, `fix/intelligent-ui-v2-phase4-hardening`, and `main`.
- Cached remote-tracking refs: `origin/codex/security-remediation-2026-10-13` and `origin/main`; `origin/HEAD` aliases `origin/main`.

The sanitized review does not identify the issuing service, audience, or current validity. These are the local refs observed to contain the reported commit, not an exhaustive statement about remote forks, clones, caches, or the live GitHub repository. Remote freshness could not be checked because DNS resolution failed. No secret value is reproduced here.

## Tested boundaries

- Full backend suite: **1,182 passed, 18 skipped, 0 failed**. The skipped PostgreSQL, Redis, Linux memory-limit and systemd-analysis checks are listed in `TEST_EXECUTION_RESULTS.md`.
- Admin authentication, RBAC and property/department isolation, guest expiry/revocation, CSRF/origin and host policy, upload validation, outbound URL validation, publication permissions, and XSS regressions are in the current test set.
- Full Playwright run: **334 passed, 38 skipped, 0 failed**; stored-XSS regression passed and all nine Chromium responsive matrix checks passed. Response-level investigation traced the earlier nine errors to a synthetic hotel-image 404 left in shared test data; test teardown now removes those records. The guest shell also has an explicit, tested favicon link.
- `npm audit --offline --json`: zero advisories in the lockfile's 3 dependency entries.
- `pip-audit` did not complete: it could not upgrade its temporary audit tooling because package-network access was unavailable. No clean Python advisory result is claimed for this run.
- `bandit -q -r app -ll`: 2 B608 Medium alerts described above, 0 High alerts; additional parser and `# nosec`-use warnings were emitted.

## Not established

No exhaustive Git-history scan was available in this run; Gitleaks, TruffleHog, and detect-secrets were not installed. A limited non-revealing scan for common token formats in the previously disclosed artifact did not identify the issuer and does not close the finding. No production database, live gateway, provider, hotel network, or real guest data was accessed. Local test passes do not establish complete protection against unknown payloads or deployment mistakes. Property-specific location retention, external-provider privacy policy, TLS/proxy/CIDR configuration, and real device/session behavior still require acceptance.

## Follow-up review at `6bc9fbba880389c08d8fc011383fc2274e632665`

Gitleaks 8.24.3 with a default history diff returned zero findings, but a fresh all-reachable-ref scan with `--log-opts="--all --text"` returned the three historical `generic-api-key` detections recorded in `audit/MASTER_SECURITY_REMEDIATION_REVIEW_2026-10-13.md`: `audit/evidence/security-2026-10-12/recovery-harness-before.txt`, commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`, lines 10, 17, and 24. The transcript's non-diffable attribute caused the default scan to miss them. The prior statement that a targeted scan did not reproduce the report does not close this finding. The credential value remains omitted; issuer-side invalidation and authorized history cleanup are unresolved.

The current-worktree scan returned one additional generic-key pattern in ignored, untracked `.env:5`; its variable name is `CREDENTIAL_ENCRYPTION_SECRET`. No value was printed or classified as production configuration. CI now includes a redacted forced-text scan across reachable history and is expected to fail until the historical exposure is addressed. No credential rotation, history rewrite, or remote setting change was performed. See `SECURITY_REMEDIATION.md` for the current scan and remediation record.

## 2026-10-16 remote status refresh

The fetched `main` baseline is `7185e18df2ae3b8f100804b7c3618a3909a831b6`. Draft PR #59 run [#240](https://github.com/jasongil003/Concierge.Ai/actions/runs/38747435895) and draft PR #60 run [#245](https://github.com/jasongil003/Concierge.Ai/actions/runs/38753064200) both have failed `secret-scan` jobs. The latest available job metadata shows its regular history action succeeded and its later redacted current-worktree scan failed; the forced-text step is sequenced after that and therefore is not evidence from these runs. The previously captured forced-text all-reachable-ref scan still reports the three historical detections documented above. No secret values or raw job logs were inspected or reproduced in this update.

The accessible active ruleset `23912203` only rejects deletion and non-fast-forward updates. The GitHub branch-protection API returned 403, and required status checks could not be configured through the available connector. Gitleaks is not installed locally. No suppression, credential rotation, history rewrite, force push, or branch protection change was performed. The historical exposure and required-check gap remain release blockers.
