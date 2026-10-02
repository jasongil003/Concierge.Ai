# Remediation report: PROD-001 and PROD-002

Date: 2026-10-02
Repository: `jasongil003/Concierge.Ai`
Branch: `fix/ecc-high-security-findings`
Base: `main`

## Baseline and synchronization

- GitHub `main` SHA: `3ccdac1ddc70be43b929c8190018e6e8bfde694d`
- Starting local SHA: `d305b0d34f35e93b7535f39b111b90482fd90030`
- Starting branch/status: `codex/production-readiness-qa`, tracked worktree clean, with three untracked audit reports preserved and excluded from this remediation.
- Fetched `origin/main` and created this branch at the live `main` SHA. The local base tree matched `main`.
- Both findings reproduced on that source before changes: the disabled first provider appeared in `resolve_connections`, and `/api/hotel` serialized hostile values from `ai_settings`.

## PROD-001

**Root cause:** `resolve_connections` retained candidate index zero even when its connection was disabled. That connection then entered `concierge_chat` and its adapter received guest prompt data.

**Files changed:** `app/ai_providers.py`; `tests/test_ai_providers.py`.

**Fix:** Routing first builds the eligible provider set from enabled connections and removes cloud providers in local-only mode, then applies the configured routing order to that set. The singular `resolve_connection` helper now returns the first routed enabled connection or `None`. A disabled default is not reactivated. An enabled fallback is used only when the configured routing mode includes that administrator-configured fallback. If no enabled candidate remains, the service raises its existing no-provider error and `/api/chat` returns its contact-concierge fallback.

**Tests added:**

- Candidate filtering and selection in `fixed`, `automatic`, `privacy_first`, and `cloud_first` modes.
- Adapter-spy assertions that disabled default and later candidates receive zero requests, including prompt, knowledge, live context, and conversation-history sentinels.
- Explicitly configured fallback behavior when the default is disabled and when a disabled fallback follows a failing enabled primary.
- All-disabled guest chat returns contact fallback with zero adapter calls.
- Local-only mode calls the enabled local adapter and never a configured cloud adapter.
- Property A/B provider routing isolation. Existing enabled-default routing/fallback test continues to verify enabled providers can be used.

**Verification:** The new tests failed on the vulnerable baseline and passed after the fix. Disabled adapters have empty recorded request lists. Full backend suite and browser coverage passed; totals are below.

## PROD-002

**Root cause:** `PropertyRecord.public_profile` returned the arbitrary persisted `ai_settings` mapping as `ai`; `/api/hotel` also supplied a default `ai` object when absent.

**Files changed:** `app/properties.py`; `app/main.py`; `tests/test_properties.py`.

**Fix:** The guest serializer no longer includes `ai_settings`, and `/api/hotel` no longer reconstructs an `ai` object. Repository search found no guest frontend consumer of `profile.ai`, so the object is omitted entirely rather than exposing a partial configuration schema.

**Public fields retained:** No AI configuration fields. Other guest profile fields are unchanged; the `/api/hotel` test confirms each property's own name and host-bound profile are still returned.

**Private fields excluded:** Every raw `ai_settings` field, including keys, tokens, client secrets, nested values, private endpoints, unknown provider settings, and arbitrary custom configuration.

**Tests added:** Hostile settings are persisted for two isolated properties, then each host requests `/api/hotel`. The tests assert no sentinel appears anywhere in either serialized response and that neither response contains an `ai` object.

**Verification:** Both property responses passed the hostile sentinel assertions. Browser guest rendering passed after removing the field; no checked-in guest client reads it.

## Verification summary

| Check | Result |
|---|---|
| TDD reproduction on vulnerable source | Expected regression failures reproduced both findings |
| Focused AI, property, security, guardrail, and guest API tests | 181 passed |
| Full backend suite (`.venv/bin/python -m pytest -q`) | 812 passed, 16 skipped, 0 failed |
| Playwright functional suite (`npx playwright test --grep-invert @visual`) | 253 passed, 35 skipped, 0 failed |
| Final focused browser smoke after the last routing change (guest home/chat/name and admin visual builder save/publish) | 8 passed, 2 skipped |
| Application compile (`python -m compileall -q app`) | Passed |
| Bandit (`bandit -q -r app -x app/static --severity-level medium --confidence-level medium`) | Passed (exit 0); informational existing `nosec`/B608 messages only |
| CI workflow YAML parse | Passed |
| Linux/macOS deployment shell syntax and ShellCheck | Passed |
| macOS plist parse and deployment Python compile | Passed |
| Docker Compose configuration | Passed |
| `git diff --check` | Passed |
| Conflict-marker search (`git grep -n -E '^(<<<<<<<|=======|>>>>>>>)'`) | No matches |
| Current `main` GitHub Actions run | All 10 jobs passed on `3ccdac1ddc70be43b929c8190018e6e8bfde694d` ([run](https://github.com/jasongil003/Concierge.Ai/actions/runs/36952236506)) |

The backend and Playwright suites reported two existing Starlette/httpx deprecation warnings. Playwright also emitted expected skips for platform/viewport-specific cases. No post-fix tests failed. Dependency manifests were unchanged; the current-main hosted dependency-security and Python dependency-security jobs both passed.

## ECC review passes

**ECC security-review:** PASS for the scoped guest-content and guest-serialization paths. The independent review traced all `concierge_chat` callers through enabled-only routing, checked local-only and explicit fallback handling, and searched guest serializers and frontend consumers. Confidence reported: 0.96 for provider routing and 0.94 for guest serialization.

**ECC code-review (`source-command-review-pr`):** PASS for the scoped diff, approximately 98% confidence. The read-only specialist review found no blocking correctness, compatibility, or regression-test issues.

**Separate follow-up caveat:** Both reviews reproduced a pre-existing authenticated-admin property serializer disclosure: `_property_admin_payload` includes raw legacy `ai_settings` for a principal with `properties.edit`, including `content-manager` users without `ai.view`. This is not a guest response, was not introduced by this diff, and was not changed because this remediation is limited to PROD-001 and the guest-facing PROD-002 path. Track and triage it separately; this report does not claim all admin AI-settings serialization is permission-filtered.

## Diff and remaining audit findings

- Source files: `app/ai_providers.py`, `app/main.py`, `app/properties.py`.
- Regression tests: `tests/test_ai_providers.py`, `tests/test_properties.py`.
- This report: `audit/REMEDIATION_PROD_001_002_2026-10-02.md`.
- No CI, deployment, dependency, or application asset files changed.
- No generated application assets were removed. The three prior untracked audit outputs remain in the local workspace and are excluded from the remediation commit. A Playwright-updated control inventory was restored to its original tracked content.
- Remaining original audit findings: PROD-003 through PROD-011 (Medium/Low) were not changed.
- Remaining Critical: none in the original audit findings.
- Remaining High: PROD-001 and PROD-002 are addressed by this change. The separate authenticated-admin serializer caveat above is untriaged and has no severity assigned in this scoped report.
