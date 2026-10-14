# Security remediation and verification

Date: 2026-10-14 (Asia/Manila)  
Reviewed commit: `6bc9fbba880389c08d8fc011383fc2274e632665`  
Scanner: Gitleaks 8.24.3 (release checksum verified), configured Bandit, pip-audit, and npm audit.

## Findings

| ID | Severity | Finding and evidence | Action/status |
|---|---|---|---|
| SEC-H01 | **High exposure — unresolved** | Gitleaks with all reachable refs and forced text diffs reports three `generic-api-key` detections in `audit/evidence/security-2026-10-12/recovery-harness-before.txt`, commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9`, lines 10, 17, and 24. The earlier sanitized investigation identifies this as a real browser identity execution credential; the environment-variable name is `BROWSER_USE_ACCESS_VERIFYING_IDENTITY`. The credential value is omitted. Its issuer, audience, permissions, and current validity are unknown. The reporting commit remains reachable from current local and cached remote refs, including `main`/`origin/main`. | Treat as potentially compromised; issuer owner must confirm invalidation/rotation. An authorized repository owner must plan history cleanup and verify all refs/forks/caches. No revocation is claimed; no rotation or history rewrite was performed. Release blocker. |
| SEC-H02 | **High pilot risk — incomplete** | Property-scoped AP/location observations lack a complete approved consent, opt-out, checkout, retention, export, and deletion policy with lifecycle regression evidence. | Obtain property/privacy approval, implement the full lifecycle, and verify deletion/expiry/isolation before hotel pilot. |
| SEC-H03 | **High CI detection gap — locally corrected, currently expected to fail** | The normal Gitleaks history command returned zero because `.gitattributes` marks the incident transcript non-diffable. Running Gitleaks with `--log-opts="--all --text"` surfaced all three historical hits. | Added a redacted all-reachable-history forced-text scan to `.github/workflows/ci.yml` and a regression assertion in `tests/test_supply_chain_controls.py`. The check must fail until the historical exposure is resolved; no suppression was added. |
| SEC-M01 | **Medium governance — blocked on access** | A read-only request to GitHub's branch-protection API returned HTTP 401 without authentication. A prior report said protection was disabled, but that is not fresh evidence. | Current branch protection and required checks remain unverified. No remote setting changed. |
| SEC-M02 | **Scanner suppressions — reviewed** | Reviewed all 46 `# nosec` directives in `app/`. They suppress B608 only and apply to fixed/allowlisted SQL identifiers, fixed predicates, or generated placeholder lists while record values are bound separately. | No broad rule suppression found. Added an explicit nearby rationale to the `PropertyStore.create_if_absent` suppression in `app/properties.py`. Bandit Medium/High scan reports 0 findings. |
| SEC-M03 | **Local configuration match — unclassified, not tracked** | Current-tree Gitleaks reports one redacted `generic-api-key` pattern at `.env:5`; the variable name is `CREDENTIAL_ENCRYPTION_SECRET`. `.env` is ignored and untracked. Its value and whether the file is for production were not printed or classified. | Do not copy this file into source or audit artifacts. The Gitleaks current-worktree command exits nonzero locally on this match; no `.gitleaksignore` exception was added. No tracked current-tree finding was returned. |

## Current references and credential handling

- In current application/test code, `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` appears only in `tests/e2e/server-environment.spec.js`, where the test asserts the variable is not passed into the isolated Playwright server. It is not referenced by current application configuration or harness setup.
- The historical artifact is still in reachable Git history. A normal Gitleaks history scan that respects Git's non-diffable attribute reports zero; the forced-text full-history scan reports the three copies. The forced scan is now added to CI so this cannot pass silently.
- The prior report says the exposed value matched the investigation process environment at that time, which supports treating it as genuine. The issuing system and current validity could not be determined from the repository.
- Rotation/revocation is required by the credential owner unless they provide evidence it was already invalidated. No evidence of revocation was available. No secret value was printed, included in these reports, or sent to a service.

## Other controls checked

- Backend auth/session/CSRF/origin, rate limiting, role ceilings, property/department/restaurant restrictions, cross-property access, XSS, SSRF/outbound-host validation, upload validation, traversal, media symlink containment, and publication boundaries passed their local regression coverage in the backend and browser suites.
- Bandit: **0 Medium/High findings**. All 46 B608 suppressions were reviewed individually; no `nosec` directive suppresses another rule or a whole file.
- `pip-audit -r requirements-dev.txt`: **no known vulnerabilities**.
- `npm audit --audit-level=high`: **0 vulnerabilities across 3 packages**.
- Gitleaks all reachable refs with `--all --text`: **3 historical findings** listed above. With the `.gitleaksignore` file disabled, the same three findings were returned; no extra historical findings appeared.
- Gitleaks current worktree: **1 match** in ignored `.env:5`; value not printed. The commit's tracked source has no returned current-tree match.
- GitHub branch protection: **BLOCKED** on API authentication (401); no configuration changed.

## Limits and required follow-up

This review did not access production data, live hotel systems, live AI provider credentials, or the issuing credential service. It did not rotate external credentials, alter production secrets, rewrite history, or modify GitHub settings. The historical credential is not resolved; the new CI step will correctly fail while it remains in reachable history. A repository owner must coordinate invalidation and an authorized history-cleanup plan, then verify all hosted refs and clones without publishing the value.

