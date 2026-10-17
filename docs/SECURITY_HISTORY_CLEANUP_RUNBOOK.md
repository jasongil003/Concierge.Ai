# Credential and Git history remediation runbook

Prepared from the verified audit facts dated 2026-10-17. This document does not authorize a history rewrite or a push. The preparation script is local-only and never pushes.

## Verified facts and assumptions

- The exposed credential is the Browser Use credential named `BROWSER_USE_ACCESS_VERIFYING_IDENTITY`. Its value must not be copied into this runbook, a ticket, a command transcript, or a commit.
- The leaked value is in the historical evidence file `audit/evidence/security-2026-10-12/recovery-harness-before.txt`. The full audit found it in one blob reachable from the repository's refs.
- The fixed recovery harness uses an explicit environment. The two additional subprocess environment leaks are covered by the code changes in this remediation: the HTTP sample and PostgreSQL backup tools.
- The existing ten `.gitleaksignore` entries were reviewed as synthetic. Preserve those entries only through the provided exact-fingerprint remap. Do not add exceptions for this real finding or change Gitleaks.
- The commands below assume the canonical remote is `https://github.com/jasongil003/Concierge.Ai.git`, `main` is the primary branch, and GitHub-pushable refs to publish are branches and tags. Review any other advertised user-managed ref before the window.
- GitHub pull refs are platform-managed. A successful branch push does not prove they stopped resolving old commits; the final check below tests both their advertised tips and their reachable commit histories.

## 1. Owner checklist: revoke and record the credential

1. Sign in to the Browser Use Cloud account that owns the key. Open [Browser Use Cloud API key settings](https://cloud.browser-use.com/settings?tab=api-keys), identify the key by its owner, label, creation time, and intended use, and revoke that key. Browser Use documents the account settings as the place to manage API keys and the `X-Browser-Use-API-Key` authentication header in its [API reference](https://docs.browser-use.com/cloud/api-reference).
2. Record the revocation time in UTC and the provider confirmation or audit-event ID. If the key remains in use, create a replacement after revocation, update only the required secret stores, and redeploy/restart the affected consumers. Do not reuse the exposed value.
3. Review Browser Use account activity from the earliest exposure through revocation for unrecognized use. Preserve provider log exports in a private incident record.
4. Record evidence in the organization's private incident/ticketing system, not in this public repository while its history is contaminated. Record: credential name, account/workspace, key label or non-secret identifier, revocation request/confirmation ID, UTC time, actor, activity-review result, dependent secret stores updated, and deployment verification. Attach only a redacted screenshot or provider event with the credential value and any usable prefix removed. Never record the full value.
5. Mark the credential-revocation gate complete only after the issuer confirms revocation. Do not publish rewritten refs before then.

## 2. Code remediation included in this change

- `scripts/master_audit_http_sample.py` now supplies the disposable app only `PATH`, temporary directories, explicit test/database settings, and generated test credentials. `tests/test_master_audit_http_sample.py` sets a synthetic host-secret sentinel and checks it is absent from every child environment.
- `app/backup.py` now supplies PostgreSQL tools only `PATH` plus libpq settings parsed from the requested database URL. `tests/test_backup_restore.py` checks a synthetic host-secret sentinel is not inherited.
- `scripts/prepare_secret_history_cleanup.sh` rejects mismatched local/origin-tracking branch tips before cloning. After filtering, it checks each snapshotted commit/tag ref against `filter-repo/ref-map`, checks its peeled commit tip against `commit-map`, and compares per-ref commit counts with the unique surviving mapped commits. It retains local `refs/codex/turn-diffs/*` tree-ref removal and the reachable-path check.

The code and test changes are prepared in the workspace but have not been committed. Get owner approval before creating a commit or PR, because that changes Git history. Do not include `audit/FULL_SECRET_LEAK_INVESTIGATION_2026-10-17.md` or any report/diff containing the credential in a commit.

## 3. Owner-approved maintenance-window sequence

Proceed only after the owner explicitly approves the history rewrite and force-push window, the credential issuer confirms revocation, collaborators are notified, and the code remediation above is present in the approved remote branch. Freeze repository writes for the duration. The steps below create a fresh full clone and a separate rewritten mirror.

### 3.1 Fresh full clone and expected remote snapshot

Run in Bash from a secure admin workstation. This creates private temporary files containing ref names and commit IDs; it does not copy secret values.

```bash
set -euo pipefail
umask 077

REMOTE_URL='https://github.com/jasongil003/Concierge.Ai.git'
CLEANUP_WORKDIR="$(mktemp -d /private/tmp/concierge-history-cleanup.XXXXXX)"
chmod 700 "$CLEANUP_WORKDIR"
SOURCE="$CLEANUP_WORKDIR/source"
MIRROR="$CLEANUP_WORKDIR/sanitized.git"
REWRITE="$CLEANUP_WORKDIR/rewritten-main"
EXPECTED_REMOTE="$CLEANUP_WORKDIR/expected-remote.tsv"
REMOTE_NOW="$CLEANUP_WORKDIR/remote-now.tsv"
EXPECTED_AFTER="$CLEANUP_WORKDIR/expected-after.tsv"

git clone --no-single-branch "$REMOTE_URL" "$SOURCE"
git -C "$SOURCE" fetch --prune origin \
  '+refs/heads/*:refs/remotes/origin/*' \
  '+refs/tags/*:refs/tags/*'
test "$(git -C "$SOURCE" rev-parse --is-shallow-repository)" = false

git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$EXPECTED_REMOTE"
```

The preparation script fails closed if a local branch and its same-name `origin` tracking ref have different tips. A mismatch means the source clone is not an unambiguous snapshot: stop, discard it, fetch a fresh clone, and investigate before retrying.

### 3.2 Prepare the sanitized mirror and a disposable `main` checkout

```bash
bash "$SOURCE/scripts/prepare_secret_history_cleanup.sh" "$SOURCE" "$MIRROR"
git --git-dir="$MIRROR" worktree add "$REWRITE" main
```

Apply this exact `.gitattributes` cleanup in the disposable rewritten checkout. Keep the evidence-wide whitespace rule; remove only the stale path-specific `-diff` rule and its comment:

```diff
 # Preserve captured terminal/browser evidence bytes, including emitted trailing spaces.
 audit/evidence/** -whitespace
-# Keep the original sensitive transcript path non-diffable; the readable,
-# redacted copy lives beside it and remains covered by the current-tree scan.
-audit/evidence/security-2026-10-12/recovery-harness-before.txt -diff
```

Then remap only the existing reviewed synthetic fingerprints, using the helper from the fresh source clone:

```bash
python3 "$SOURCE/scripts/remap_approved_gitleaks_fingerprints.py" \
  "$MIRROR/filter-repo/commit-map" "$REWRITE/.gitleaksignore"
```

The verified expected result for this repository is `10 remapped, 0 unreachable, 0 unchanged`. Stop for review if the counts differ. Review the rewritten checkout status and ensure only `.gitattributes` and `.gitleaksignore` changed:

```bash
git -C "$REWRITE" status --short
git -C "$REWRITE" diff --check
git -C "$REWRITE" diff -- .gitattributes .gitleaksignore
```

Commit those two reviewed files on the disposable rewritten `main` branch:

```bash
git -C "$REWRITE" add .gitattributes .gitleaksignore
git -C "$REWRITE" commit -m 'security: finalize sanitized history scan configuration'
```

### 3.3 Run both pinned Gitleaks scans

Use Gitleaks 8.24.3, matching CI. Both scans must exit successfully with zero findings. Do not change scanner configuration or add ignore entries to get a passing result.

```bash
gitleaks version
gitleaks detect --no-git --source "$REWRITE" --redact --no-banner
gitleaks detect --source "$REWRITE" --redact --no-banner \
  --log-opts='--all --text'
```

Stop on any finding or non-zero exit. The second command deliberately scans full history with text diffs, matching the explicit CI history scan. The `--text` option must remain in CI.

### 3.4 Recheck the remote snapshot, then publish with per-ref expected-SHA leases

First confirm that every branch/tag still has the exact expected pre-rewrite SHA. Any difference means a write happened during the freeze; stop and rebuild the rewrite from a fresh snapshot.

```bash
git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$REMOTE_NOW"
diff -u "$EXPECTED_REMOTE" "$REMOTE_NOW"
```

Build explicit refspecs for only the snapshotted branches and tags. Every destination gets its captured expected SHA as a lease. The dry run must succeed before the actual atomic push.

```bash
declare -a LEASE_ARGS=()
declare -a REFSPECS=()
: > "$EXPECTED_AFTER"

while IFS=$'\t' read -r EXPECTED_SHA REF; do
  case "$REF" in
    refs/heads/*)
      SOURCE_REF="$REF"
      if ! git --git-dir="$MIRROR" show-ref --verify --quiet "$SOURCE_REF"; then
        SOURCE_REF="refs/remotes/origin/${REF#refs/heads/}"
      fi
      ;;
    refs/tags/*)
      SOURCE_REF="$REF"
      ;;
    *)
      echo "Unexpected ref in expected remote snapshot: $REF" >&2
      exit 1
      ;;
  esac

  git --git-dir="$MIRROR" show-ref --verify --quiet "$SOURCE_REF"
  NEW_SHA="$(git --git-dir="$MIRROR" rev-parse --verify "$SOURCE_REF")"
  LEASE_ARGS+=("--force-with-lease=$REF:$EXPECTED_SHA")
  REFSPECS+=("$SOURCE_REF:$REF")
  printf '%s\t%s\n' "$NEW_SHA" "$REF" >> "$EXPECTED_AFTER"
done < "$EXPECTED_REMOTE"

LC_ALL=C sort -k2,2 -o "$EXPECTED_AFTER" "$EXPECTED_AFTER"
git --git-dir="$MIRROR" push --dry-run --atomic \
  "${LEASE_ARGS[@]}" "$REMOTE_URL" "${REFSPECS[@]}"
```

After explicit owner go-ahead at the maintenance window, run the same command without `--dry-run`:

```bash
git --git-dir="$MIRROR" push --atomic \
  "${LEASE_ARGS[@]}" "$REMOTE_URL" "${REFSPECS[@]}"
```

Verify every published branch and tag equals its rewritten tip:

```bash
git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$REMOTE_NOW"
diff -u "$EXPECTED_AFTER" "$REMOTE_NOW"
```

The commands intentionally do not use `git push --mirror`, `--force`, or an unscoped force push. If the atomic push or a lease rejects, stop and inspect the changed refs; do not retry with weaker safeguards.

### 3.5 Verify GitHub pull refs no longer expose pre-rewrite commits

Save all pre-rewrite commit IDs from the filter map, query the exact advertised pull refs, then fetch their head and merge histories into a temporary local namespace for an ancestry check:

```bash
OLD_COMMITS="$CLEANUP_WORKDIR/pre-rewrite-commits.txt"
PULL_REFS="$CLEANUP_WORKDIR/pull-refs.tsv"
awk 'NR > 1 { print $1 }' "$MIRROR/filter-repo/commit-map" \
  | LC_ALL=C sort -u > "$OLD_COMMITS"

git ls-remote "$REMOTE_URL" 'refs/pull/*' > "$PULL_REFS"
if [[ -s "$PULL_REFS" ]]; then
  git --git-dir="$MIRROR" fetch --no-tags "$REMOTE_URL" \
    '+refs/pull/*/head:refs/audit/pull/*/head' \
    '+refs/pull/*/merge:refs/audit/pull/*/merge'
fi

python3 - "$MIRROR" "$OLD_COMMITS" "$PULL_REFS" <<'PY'
from pathlib import Path
import subprocess
import sys

repo, old_commits_path, pull_refs_path = sys.argv[1:]
old_commits = set(Path(old_commits_path).read_text(encoding="utf-8").splitlines())
pull_refs = Path(pull_refs_path).read_text(encoding="utf-8").splitlines()
old_tips = {
    line.split()[0]
    for line in pull_refs
    if line.split() and line.split()[0] in old_commits
}
if old_tips:
    raise SystemExit(f"FAIL: {len(old_tips)} pull-ref tip(s) still equal pre-rewrite commits")

refs = subprocess.run(
    ["git", f"--git-dir={repo}", "for-each-ref", "--format=%(refname)", "refs/audit/pull"],
    check=True, capture_output=True, text=True,
).stdout.splitlines()
for ref in refs:
    reachable = set(subprocess.run(
        ["git", f"--git-dir={repo}", "rev-list", ref],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines())
    old_reachable = old_commits & reachable
    if old_reachable:
        raise SystemExit(f"FAIL: pull ref {ref} reaches {len(old_reachable)} pre-rewrite commit(s)")
print(f"PASS: {len(refs)} fetched pull ref(s) reach no pre-rewrite commits")
PY
```

If this check fails, record the affected pull-ref names and coordinate with the repository owner and GitHub Support. Do not claim cleanup complete while a PR ref still reaches a pre-rewrite commit.

## 4. Collaborator and local-reference cleanup

Have each collaborator make a new clone after publication. Keep any old clone offline for reference, and do not push its branches or merge its old history into the rewritten repository. Reapply only reviewed, uncommitted work by cherry-picking or patching it onto a new branch created from the rewritten `main`.

```bash
git clone --no-single-branch "$REMOTE_URL" /path/to/new/Concierge.Ai
git -C /path/to/new/Concierge.Ai switch main
git -C /path/to/new/Concierge.Ai status --short
```

In each existing local checkout that will be retained, remove only the never-pushed Codex tree refs. This is a local ref deletion; it does not contact or modify GitHub:

```bash
while IFS= read -r REF; do
  git -C /path/to/existing/Concierge.Ai update-ref -d "$REF"
done < <(git -C /path/to/existing/Concierge.Ai \
  for-each-ref --format='%(refname)' refs/codex/turn-diffs)
```

The stale `.gitattributes -diff` line is removed in the rewritten checkout before the clean scans and publication, as shown above. Keep the explicit CI `--all --text` scan and all ten reviewed synthetic ignore entries; the remap helper must not introduce new entries.

## 5. Completion checklist

- [ ] Browser Use confirms the exposed key is revoked; private revocation evidence is recorded without the key value.
- [ ] Dependent secret stores were rotated where needed and affected workloads restarted.
- [ ] A fresh, non-shallow clone was used; the hardened prepare script passed its branch-tip preflight and ref-map/per-ref preservation gate.
- [ ] The evidence path is absent from all reachable mirror objects by path verification.
- [ ] The remap result matches the reviewed ten synthetic fingerprints; no real finding was ignored.
- [ ] Both Gitleaks 8.24.3 scans returned zero findings, including the full-history `--all --text` scan.
- [ ] `.gitattributes` no longer hides the removed path from diffs; CI still includes `--text`.
- [ ] The owner approved the maintenance window; publication used explicit expected-SHA leases and an atomic push.
- [ ] Published branches and tags match their rewritten tips; every advertised/fetched `refs/pull/*` ref reaches no pre-rewrite commit.
- [ ] Collaborators recloned; old clones cannot push stale refs; local `refs/codex/turn-diffs/*` refs were removed where appropriate.
- [ ] All CI jobs, especially secret-scan, pass on the rewritten repository.

Do not mark the incident closed if any box remains unchecked. Do not rewrite shared history or force-push outside explicit owner authorization.
