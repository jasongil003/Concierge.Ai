# Full Secret Leak Investigation — Concierge.Ai

**Date:** 2026-10-17
**Repository:** https://github.com/jasongil003/Concierge.Ai (public, no forks)
**Commit audited:** `ad32e5a8115d7b9646856117982ff072f5585af4` (origin/main and local HEAD, identical at audit time)
**Scanner:** Gitleaks 8.24.3 (darwin-arm64 release binary; tarball SHA-256 verified against the official v8.24.3 checksums file)
**Mode:** Read-only audit. No credentials were displayed, no history was rewritten, no remote refs were modified, no security control was weakened.

---

## 1. Executive summary

The CI `secret-scan` job has been red on every run since 2026-10-14 because three Gitleaks findings — all pointing at the **same genuine credential** — remain in reachable Git history. The credential is a real execution-environment token (`BROWSER_USE_ACCESS_VERIFYING_IDENTITY`, 60-character high-entropy value) that was copied from the developer host into a QA harness subprocess environment, captured by pytest failure output, and committed to `audit/evidence/security-2026-10-12/recovery-harness-before.txt` in commit `0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9` on 2026-10-13.

Current source is clean. The fix for the propagation bug is in place and covered by passing regression tests. What is **not** done: (a) provider-side revocation/rotation of the credential, (b) removal of the historical blob from Git history, (c) hardening of the offline cleanup pipeline, which was found during this audit to silently lose commits under a specific ref-collision condition.

The GitHub Actions failure is not a scanner malfunction and must not be "fixed" by ignoring or deleting the failing step. It is the security control correctly reporting an unresolved historical exposure.

## 2. Scan coverage and exclusions

Covered:

- 978 tracked files in the current worktree (Gitleaks `--no-git`, which also walked untracked/ignored local artifacts: `.env`, `logs/`, `state/` text, `playwright-report/`, `test-results/`).
- 329 tracked binary artifacts (screenshots, Playwright traces, videos, PDFs) swept with `strings` + provider/credential regexes: zero matches.
- Complete reachable Git history: 340 commits across 25 local branches, 28 remote-tracking branches, 0 tags (`--log-opts="--all --text"`).
- All 36 remote PR head refs (`refs/pull/*/head`): every SHA already contained in the 340-commit set; no unseen PR content.
- 19 local `refs/codex/turn-diffs/*` tree refs (not scanned by Gitleaks; see F-09) — inspected manually.
- Full object store: 3,019 blobs content-scanned for the known leaked value (exactly 1 blob contains it).
- Secondary clones: `Concierge copy.Ai` (fully contained in main refs), `DevSwarmProjects/Concierge.Ai` (empty repo, 1 empty-tree commit), Codex worktrees (share the main repository's object store; refs covered).
- Forks: none (GitHub API reports `forks_count: 0`).
- Targeted manual pattern sweeps: provider key prefixes (`sk-`, `AIza`, `AKIA`, `ghp_`, JWTs, private keys), credential-bearing URLs, `DATABASE_URL`/`REDIS_URL` literals, deployment scripts, Docker/Compose files, docs.

Excluded / UNVERIFIED (access or evidence missing):

- GitHub Actions job logs and the `gitleaks-results.sarif` artifact require authentication; no `gh` CLI or token was available. The failing step was identified by exact local reproduction with the identical tool version (see §3).
- Visual content of tracked screenshots/videos (OCR not performed; byte-level sweep found nothing).
- GitHub-side secret scanning / push-protection configuration and provider-side revocation status (owner action required).
- GitHub PR diff rendering for PR #53 (expected to render as "binary" due to the `-diff` attribute; raw blob access by commit SHA remains possible until history is rewritten).

## 3. Why the GitHub Actions secret-scan keeps failing

Failing run: [#38981396265](https://github.com/jasongil003/Concierge.Ai/actions/runs/38981396265) — push to `main` at `06969e3`, `secret-scan` job exit code 1, all other jobs green. The same failure repeated on the newest run (`ad32e5a8`, `secret-scan: failure` while the run was still in progress).

Timeline, verified from Git history and the Actions API:

1. `0b0ff26` (2026-10-13) committed the secret-bearing evidence file and, in the same commit, added `.gitattributes` with `-diff` on that path.
2. The file was redacted in the working tree on 2026-10-13 (`9a9f498` / `1f0755d`), but the historical blob remains reachable.
3. CI succeeded through 2026-10-13T23:06Z because the default `gitleaks/gitleaks-action` scan respects the `-diff` attribute: Git renders the file as binary and Gitleaks sees no text (locally reproduced: `--log-opts="--all"` = **0 findings**).
4. On 2026-10-14 (`58b3fdd`) the explicit CI step `gitleaks detect --source . --log-opts="--all --text"` was added to defeat that blindness. With `--text` the same scan reports **3 findings** (locally reproduced, byte-identical Gitleaks version).
5. Every CI run since 2026-10-14 has failed at that step. Last green run: 2026-10-13T23:06:46Z.

The three findings are fingerprints:

```
0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9:audit/evidence/security-2026-10-12/recovery-harness-before.txt:generic-api-key:10
0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9:audit/evidence/security-2026-10-12/recovery-harness-before.txt:generic-api-key:17
0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9:audit/evidence/security-2026-10-12/recovery-harness-before.txt:generic-api-key:24
```

All three match the same value of the environment variable `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` (one unique secret, three occurrences). The value was never added to `.gitleaksignore` in any commit — correctly so, because it is not synthetic.

## 4. Root-cause analysis (how the credential leaked)

1. **Programming mistake.** The historical `scripts/failure_recovery_smoke.py` built the child-app environment as `{**os.environ, ...}`, copying every host environment variable — including the developer's `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` — into the disposable API subprocess, the pytest process, and every captured fixture.
2. **Capture.** When the harness test asserted, pytest printed the captured environment dicts into the failure transcript, including the secret value (lines 10, 17, 24).
3. **Persistence.** That transcript was saved as audit evidence and committed verbatim in `0b0ff26`.
4. **Aggravator.** `.gitattributes … -diff` hid the content from default Git diffs and from the default Gitleaks action scan, delaying detection.
5. **Current correction (verified).** The harness now builds an explicit environment allow-list (`PATH`, temp dirs, synthetic credentials from `secrets.token_urlsafe`). Regression tests enforce it and were executed during this audit:
   - `tests/test_failure_recovery_harness.py` — 3 passed, including `test_recovery_children_do_not_receive_host_credentials` which plants a synthetic sentinel (`CONCIERGE_SYNTHETIC_HOST_SECRET_SENTINEL`) and asserts it never reaches any child environment.
   - `tests/e2e/server-environment.spec.js` asserts the Playwright server environment excludes `BROWSER_USE_ACCESS_VERIFYING_IDENTITY`.
   - `playwright.config.js` uses `createTestServerEnvironment()` (constructed allow-list env), not `process.env` passthrough.

## 5. Findings

| ID | Severity | File / Location | Source Commit | Secret Type | Real / Synthetic | Current / Historical | Root Cause | Remediation |
|---|---|---|---|---|---|---|---|---|
| F-01 | HIGH (escalate to CRITICAL if owner confirms it is still active) | `audit/evidence/security-2026-10-12/recovery-harness-before.txt` lines 10/17/24; blob `69e8678d65ca…` (only value-bearing blob in the object store) | `0b0ff26` (2026-10-13) | Provider/API credential — `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` (60-char, base64-like, entropy 5.14) | **Genuine** execution-environment credential; validity/revocation **unverified** | **Historical only** — current file is a redaction placeholder; value exists solely in the pre-redaction blob, reachable from `main` and 20+ branch refs | Host env copied via `**os.environ` into harness; pytest capture committed as evidence | (1) Owner: revoke/rotate at provider and confirm; (2) sanitize history via the validated pipeline (§6); (3) keep existing code fix + regression tests |
| F-02 | HIGH (process/visibility) | `.github/workflows/ci.yml` `secret-scan` job | job failing since 2026-10-14 | N/A | N/A | Current | CI correctly reports unresolved F-01; `--text` history scan finds 3 findings every run | Do **not** silence. Resolve F-01 (revocation + history rewrite), then both CI scans go green legitimately |
| F-03 | MEDIUM | `.gitattributes` (`recovery-harness-before.txt -diff`) | `0b0ff26` | N/A | N/A | Current | Binary-marker attribute suppressed the secret from the default Gitleaks action scan (locally proven: 0 findings without `--text`, 3 with) | After history rewrite the path disappears; remove the stale attribute line. Until then, the mandatory `--text` CI step must stay |
| F-04 | MEDIUM (remediation-tooling defect, found in this audit) | `scripts/prepare_secret_history_cleanup.sh` + git-filter-repo 2.47.0 | N/A | N/A | N/A | Current tooling | During non-destructive validation, a local branch `codex/ecc-closeout-20261019` (stale tip `7185e18`) shadowed `refs/remotes/origin/codex/ecc-closeout-20261019` (newer tip `f4287c2`). git-filter-repo's remote-to-local ref conversion dropped the collision loser; **5 real commits were silently lost** from the sanitized mirror while the script's path-verification still reported PASS | Add a pre-flight check that refuses same-name local/remote refs with divergent tips (or normalize refs first, e.g. from a fresh full clone as the runbook already recommends, with explicit handling of local-only branches); add a post-rewrite preservation check (every source ref tip must map to exactly one rewritten tip; compare ref counts and per-ref commit counts); re-run validation before any publish |
| F-05 | LOW | local `.env` (gitignored, untracked) line 5, `CREDENTIAL_ENCRYPTION_SECRET` | N/A (never committed) | App encryption secret (local dev) | Local development credential | Current, local only — not reachable by CI or clones | Developer convenience file; Gitleaks `--no-git` flags it | If this value was ever reused outside local dev, rotate it; otherwise leave. Optional: move local secrets to an unscanned OS keychain |
| F-06 | LOW (assurance) | `.gitleaksignore` (10 fingerprints) | various | Synthetic/placeholder exceptions | **All synthetic** — individually verified: empty `.env.example` key, Groq-style masked test strings, runtime-generated harness values, empty local-demo assignments, and a CI heredoc placeholder equal to the trivial pattern `0123456789abcdef` repeated twice (same placeholder reused for two different variables, confined to 64 historical commits of `ci.yml`, never outside that file) | Current | Exact-fingerprint allow-listing of reviewed false positives | Keep. No entry conceals a real credential. After a history rewrite, run the remap helper (validated: 10 remapped, 0 unreachable, 0 new exceptions → both scans clean) |
| F-07 | MEDIUM | `scripts/master_audit_http_sample.py` (`environment = {**os.environ, …}`) | current | N/A | N/A | Current | Same env-inheritance pattern that caused F-01 still exists in this audit-sampling script; its subprocesses (and anything they log) can receive host secrets | Rebuild with an explicit allow-list env like the remediated harness; add a sentinel regression test in the same style as `test_failure_recovery_harness.py` |
| F-08 | LOW | `app/backup.py` `_postgres_environment` (`os.environ.copy()` + `PGPASSWORD`) | current | N/A | N/A | Current | Full host environment is passed to `pg_dump`; password correctly kept out of argv; no evidence of persistence to disk or logs | Prefer a filtered environment (PATH + the `PG*` variables it sets). Defense-in-depth only |
| F-09 | LOW (local exposure + scanner blind spot) | `refs/codex/turn-diffs/*` (19 local tree refs); 1 tree contains the exact secret blob | N/A (local refs, never pushed: `git ls-remote origin refs/codex/*` = empty) | Same credential as F-01 | Genuine (same blob) | Local only | Codex turn-diff snapshots hold full trees; Gitleaks Git mode does not scan tree-only refs (detection gap) | Delete the local tree refs now (`git update-ref -d` loop); the cleanup script already drops them in the mirror — keep that behavior; consider adding a tree-ref sweep to local audit practice |
| F-10 | INFO (UNVERIFIED) | GitHub-side surfaces | — | — | — | — | Job logs, the SARIF artifact, PR #53 diff rendering, GitHub secret-scanning/push-protection status, and provider-side key status could not be inspected without credentials | Owner: check provider dashboard for the credential's status; enable GitHub secret scanning + push protection if available; after rewrite, verify `git ls-remote origin 'refs/pull/*'` no longer references pre-rewrite SHAs |
| F-11 | INFO (verified non-issue) | `/api/admin/system/diagnostics` | current | N/A | N/A | Current | Sanitized fields only; gated by `enforce_admin_security` middleware (`app/main.py:478`) with 403 tests | None |

No other genuine credentials, tokens, private keys, connection strings with embedded passwords, or signing secrets were found in current source or in any of the 340 reachable commits.

## 6. Historical Git exposure assessment

- **Reachability:** the secret blob is reachable from `origin/main` and most branch refs. Fetching the public repository exposes it to anyone who knows the (published, indexed) commit SHA.
- **Uniqueness:** exactly one blob in the entire 3,019-blob object store contains the value; no copies under other paths; zero unreachable copies.
- **GitHub surfaces:** raw blob and commit URLs by SHA work on public repos regardless of `.gitattributes`. PR/commit web diffs are expected to show "binary" because of `-diff`, but this is convenience masking, not removal.
- **Cleanup pipeline validation (non-destructive, performed in a temp mirror):**
  - `prepare_secret_history_cleanup.sh` completed with PASS; source repository status and refs verified unchanged.
  - Post-rewrite: the sensitive path is absent from all reachable objects; the secret value is absent from 0/0 blobs (zero hits across the full sanitized object store).
  - Post-rewrite Gitleaks before remap: 10 findings — exactly the known synthetic set under new commit SHAs (expected; every commit SHA changes because filter-repo rewrote all 335 processed commits).
  - `remap_approved_gitleaks_fingerprints.py`: 10 remapped, 0 unreachable, 0 new exceptions created; file diff contains only SHA substitutions.
  - After remap: both CI scans (`--no-git` and `--all --text`) report **zero findings**.
  - **Defect found:** the 5-commit silent loss described in F-04. The script's own verification does not detect it.

## 7. Existing protections verified

- Explicit-allow-list harness environment (`scripts/failure_recovery_smoke.py`), sentinel regression test — 3/3 passed during this audit.
- Playwright server environment allow-list (`tests/e2e/server_environment.js` + spec assertion).
- CI: full-history checkout (`fetch-depth: 0`), pinned Gitleaks 8.24.3 with SHA-256 verification, mandatory `--text` history scan, `gitleaks/gitleaks-action` (v3) as a second layer.
- `.gitleaksignore`: 10 exact fingerprints, all verified synthetic; no pattern-based or path-based suppressions.
- `.dockerignore` excludes `.env`; Dockerfile never copies it; Compose fails fast on missing production secrets (`${VAR:?…}`); production settings validation rejects default/weak secrets (`app/config.py`).
- CI generates per-run random credentials with `::add-mask::`; no long-lived secrets in workflows (only `${{ secrets.RELEASE_TAG_PUBLIC_KEY }}` reference in `release.yml`).
- Admin diagnostics endpoint sanitized and auth-gated.

## 8. Remaining gaps

1. Credential not yet revoked/rotated (owner, provider-side evidence required).
2. Historical blob still in public Git history.
3. Cleanup tooling can silently drop commits (F-04) — must be hardened and re-validated before use.
4. `master_audit_http_sample.py` still inherits full host env (F-07).
5. GitHub PR refs (`refs/pull/*`) may retain pre-rewrite commits after a force-push — must be verified after any rewrite; GitHub-side secret scanning status unknown (F-10).
6. Stale local branches in the working clone shadow remote branches — clean up before any sanitize run (same trigger as F-04).

## 9. Remediation plan

Ordered; steps 1–2 require the owner and block everything else.

1. **Credential revocation (owner, immediate).** Verify `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` in the provider (Browser Use) dashboard; revoke/rotate; record evidence. If it is still active, classify F-01 as CRITICAL and assume the token is public.
2. **Freeze reintroduction (now, no owner needed).** The code fix and regression tests already prevent the original leak path. Also apply F-07 (`master_audit_http_sample.py` allow-list env + sentinel test) and F-09 (delete local `refs/codex/turn-diffs/*`).
3. **Harden the cleanup pipeline (F-04).**
   - Add a pre-flight to `prepare_secret_history_cleanup.sh`: fail if any `refs/heads/X` and `refs/remotes/origin/X` (or any same-suffix ref pair) have different tips.
   - Add a post-rewrite preservation gate: every pre-rewrite ref must map to exactly one post-rewrite ref (use `filter-repo/ref-map`), and per-ref commit counts must match modulo the removed path.
   - Prefer running from a fresh full clone per runbook step 1; explicitly handle the four local-only branches (all tips are reachable from `origin/main` today, but the script must not assume that).
4. **History sanitization (owner-authorized maintenance window).**
   - Run the hardened pipeline: sanitized mirror → remap `.gitleaksignore` (validated: 10 remapped) → both Gitleaks scans must be zero → commit remapped ignore file on the rewritten branch.
   - Publish rewritten refs with expected-SHA safeguards; force-push all branches; re-clone collaborators; rerun CI.
   - After publish: `git ls-remote origin 'refs/pull/*'` — confirm no pre-rewrite SHAs remain fetchable; ask GitHub Support to expire cached pre-rewrite objects if old SHAs still resolve.
   - Expect residual exposure of the old blob by SHA until GitHub's GC; revocation (step 1) is the real control.
5. **Post-rewrite hygiene.** Remove the stale `.gitattributes -diff` line (path no longer exists); confirm CI `secret-scan` is green because history is clean, not because any scan was changed.
6. **Regression tests to add.**
   - Sentinel env-propagation test for `scripts/master_audit_http_sample.py` (mirror `test_recovery_children_do_not_receive_host_credentials`).
   - CI guard: fail the `secret-scan` job if `.gitleaksignore` gains any entry that is not in an approved, reviewed allow-list file (optional, prevents silent exception growth).
   - Cleanup-pipeline self-test: synthetic fixture repo with a local/remote ref collision must make the prepare script exit non-zero.
7. **Verification commands and acceptance conditions.**
   - `gitleaks detect --no-git --source . --redact --no-banner` → 0 findings.
   - `gitleaks detect --source . --redact --no-banner --log-opts="--all --text"` → 0 findings.
   - `git log --all --oneline -- audit/evidence/security-2026-10-12/recovery-harness-before.txt` → empty on the sanitized repo.
   - `git rev-list --objects --all | grep -F " audit/evidence/security-2026-10-12/recovery-harness-before.txt"` → no matches.
   - Content check: no blob in the object store contains the known value (scripted; this audit's method).
   - Provider dashboard shows the old credential revoked.
   - CI `secret-scan` green on the next push to `main`.
8. **Risks and dependencies.**
   - History rewrite changes every commit SHA after the filter point (all 335 processed commits changed in validation) → all open refs, local clones, and the 10 fingerprints need remapping; collaborators must re-clone.
   - GitHub PR refs and caches may retain old objects (F-10) — residual, time-bounded, mitigated by revocation.
   - Owner authorization and a write-freeze window are hard prerequisites; this audit performed neither.

## 10. Final security verdict

**FAIL — remediable.** One genuine credential is exposed in public Git history with unknown revocation status; current source is clean; the propagation bug is fixed and tested; the CI failure is the control working as designed. The failure clears only after owner-side revocation and a history rewrite executed with the hardened, re-validated cleanup pipeline. No security scan may be weakened, and no finding may be ignored, to obtain a green CI result.
