# Credential and Git history remediation runbook

Prepared 2026-10-17. These instructions do not grant authorization. **Do not run any clone/ref mutation, commit, rewrite, deletion or publication below until the owner expressly approves that operation.** Never execute this procedure in the live checkout. The preparation tool never pushes. Its actual interface remains two positional arguments; the fingerprint tool also takes two positional arguments.

## Credential gate and private evidence

The owner reported “Revoked; private evidence available” in this chat. This is owner confirmation, not independent provider verification. Keep the private ticket reference, provider account/workspace, non-secret key identity, owner, revocation timestamp/timezone, provider confirmation, rejected-authentication result, replacement/deployment checks and log review in a restricted incident ticket/vault. Do not put that evidence or any credential value in this public repository.

1. Identify `BROWSER_USE_ACCESS_VERIFYING_IDENTITY` by account scope and non-secret metadata. The application identifier alone does not establish which Browser Use product issued it. In the owning provider account, confirm the exact credential type before using the corresponding official management procedure.
2. Use [Browser Use Cloud account settings](https://cloud.browser-use.com/settings) for Cloud API keys. [Browser Use's official Cloud documentation](https://github.com/browser-use/browser-use/blob/main/CLOUD.md) identifies its web app as the API-key management surface. For a different identity credential, obtain the issuer's procedure; do not assume Cloud API-key authentication applies.
3. Confirm revocation with the issuer and a controlled authentication rejection in a private session, without putting the old value in argv, output or saved shell history. Never send it to a different endpoint to test it.
4. Replace only required credentials, update authorized deployments/private stores securely, restart affected consumers, and verify them. Check that no application depends on the old credential. Inspect available access logs from 2026-10-13 through revocation for unexplained activity.
5. Independently review private confirmation before permitting any history rewrite. Record only the non-secret ticket reference in a future public closeout if appropriate.

## Safety, expected results and stop conditions

Before maintenance: notify collaborators, establish a write freeze/window, inspect branch/tag protection, coordinate CI and deployment checkouts, and approve an explicit branch/tag publication inventory. No collaborator messages have been sent by this agent. Retain an access-controlled, offline source snapshot until recovery is complete; it remains contaminated. Never attach it to a public issue or artifact.

Stop on divergent local/origin tips, shallow sources, unsupported object refs, changed remote snapshots, missing mappings, missing/extra refs, changed mapped tips/types/parent relationships, commit-set differences, any removed/collapsed commit, nonzero scanner exits, unexpected fingerprint counts, or unexpected staged files. Do not weaken checks to continue.

The tool retains empty commits and degenerate merges (`--prune-empty never --prune-degenerate never`). This avoids automatically treating path-only commit loss as acceptable. Every count reduction fails and needs individual owner review of each old/mapped commit, parents and path-only effects, followed by a separately reviewed procedure. Identical counts alone are insufficient: reachable sets and parent topology must also match.

Rollback means stopping publication, preserving private maps/inventories, correcting the disposable preparation and rebuilding from the frozen source. Do not restore contaminated public history as a routine rollback. After publication, application rollback must use sanitized commits and verified backups. Re-signing annotated tags/commits, if required, changes objects and requires another explicit approval/mapping review.

## 1. Approved source snapshot and read-only remote baseline

Run in Bash on a secure workstation **after explicit approval for Git operations**. `TOOLS` must point to the reviewed checkout containing this patch, including `scripts/history_preservation.py`; the source mirror need not already contain these tools. Do not use unreviewed historical tool versions.

```bash
set -euo pipefail
umask 077
TOOLS='/absolute/path/to/reviewed/Concierge.Ai'
REMOTE_URL='https://github.com/jasongil003/Concierge.Ai.git'
CLEANUP_WORKDIR="$(mktemp -d /tmp/concierge-history-cleanup.XXXXXX)"
SOURCE="$CLEANUP_WORKDIR/source.git"
MIRROR="$CLEANUP_WORKDIR/sanitized.git"
REWRITE="$CLEANUP_WORKDIR/rewritten"
EXPECTED_REMOTE="$CLEANUP_WORKDIR/expected-remote.tsv"
REMOTE_NOW="$CLEANUP_WORKDIR/remote-now.tsv"
EXPECTED_AFTER="$CLEANUP_WORKDIR/expected-after.tsv"

# Save all advertised branches, tags (including peeled tags) and PR refs privately.
git -C "$TOOLS" ls-remote origin 'refs/heads/*' 'refs/tags/*' 'refs/pull/*' \
  > "$CLEANUP_WORKDIR/before-all-refs.tsv"
git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$EXPECTED_REMOTE"
git clone --mirror "$REMOTE_URL" "$SOURCE"
test "$(git -C "$SOURCE" rev-parse --is-shallow-repository)" = false
git -C "$SOURCE" for-each-ref --format='%(objectname)%09%(refname)' refs/heads refs/tags \
  | LC_ALL=C sort -k2,2 > "$CLEANUP_WORKDIR/source-branches-tags.tsv"
diff -u "$EXPECTED_REMOTE" "$CLEANUP_WORKDIR/source-branches-tags.tsv"
python3 "$TOOLS/scripts/history_preservation.py" preflight "$SOURCE"
python3 "$TOOLS/scripts/history_preservation.py" snapshot "$SOURCE" \
  "$CLEANUP_WORKDIR/source-inventory.json"
git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$REMOTE_NOW"
diff -u "$EXPECTED_REMOTE" "$REMOTE_NOW"
```

Expected: full mirror; no divergent same-name tips; remote baseline unchanged. Compare every source branch/tag object ID against `expected-remote.tsv` as well. A mirror may contain PR refs; those must be validated offline but are never publishable destinations. Preserve the source mirror offline and do not fetch into it during preparation.

## 2. Hardened preparation, then disposable rewritten checkout

```bash
bash "$TOOLS/scripts/prepare_secret_history_cleanup.sh" "$SOURCE" "$MIRROR"
cat "$MIRROR/preservation-report.txt"
test -s "$MIRROR/filter-repo/ref-map"
test -s "$MIRROR/filter-repo/commit-map"
git clone --no-local "$MIRROR" "$REWRITE"
git -C "$REWRITE" switch main
```

Expected: `source-inventory.json` (full refs/types/tips/counts/parents/symbolic relationships), `source-ref-manifest.tsv`, `source-ref-commits.tsv`, filter maps and a sanitized preservation report. Optional `ref-exceptions.tsv` names only local tree snapshots omitted from the disposable mirror with expected-OID deletion safeguards. Unknown non-commit refs fail. Origin tracking names map explicitly to local branch names; preflight prevents either competing tip being silently discarded. Each intended destination must exist and its mapped commit set and parent topology must match. Removed-path verification must pass. An incomplete output mirror is removed on failure; preserve the original isolated source and capture only sanitized failure messages privately.

No real rewrite was performed while preparing this patch. Unit fixtures validate failure modes without creating commits or refs. Run the entire gate against actual filter maps after approval; earlier offline results do not certify this changed tool.

## 3. Remap exactly the ten approved synthetic fingerprints

```bash
python3 "$TOOLS/scripts/remap_approved_gitleaks_fingerprints.py" \
  "$MIRROR/filter-repo/commit-map" "$REWRITE/.gitleaksignore" \
  > "$CLEANUP_WORKDIR/fingerprint-remap.txt"
cat "$CLEANUP_WORKDIR/fingerprint-remap.txt"
python3 - "$CLEANUP_WORKDIR/fingerprint-remap.txt" "$REWRITE/.gitleaksignore" <<'PY'
from pathlib import Path
import re, sys
report = Path(sys.argv[1]).read_text()
assert '10 remapped, 0 unreachable, 0 unchanged.' in report, 'Unexpected remap totals; STOP'
rows = [line for line in Path(sys.argv[2]).read_text().splitlines() if re.fullmatch(r'[0-9a-f]{40}:.+', line)]
assert len(rows) == 10, 'Expected exactly ten approved fingerprints; STOP'
PY
git -C "$REWRITE" diff --check
git -C "$REWRITE" diff -- .gitleaksignore
```

Stop if any fingerprint suffix changed, a new exception appeared, or totals differ. Do not remove or expand the approved list. Do not remove `.gitattributes -diff` yet: the owner requires that cleanup only after approved publication and reachability verification.

## 4. Both history scan modes and current source

Use Gitleaks **8.24.3**, pinned in `.github/workflows/ci.yml`. Do not copy private `.env`, state or local logs into this clean checkout. Preserve the explicit text scan unchanged.

```bash
cd "$REWRITE"
gitleaks version
gitleaks detect --no-git --source . --redact --no-banner
gitleaks detect --source . --redact --no-banner --log-opts="--all --text"
# Default Git diff interpretation, over all sanitized refs, including mirrored PR refs.
gitleaks detect --source "$MIRROR" --redact --no-banner \
  --gitleaks-ignore-path "$REWRITE/.gitleaksignore" --log-opts='--all'
gitleaks detect --source "$MIRROR" --redact --no-banner \
  --gitleaks-ignore-path "$REWRITE/.gitleaksignore" --log-opts='--all --text'
```

Expected: zero findings and zero exit status in each. Default-diff success alone cannot clear the incident while `-diff` remains.

The configured Action is pinned to `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e` (v3). Its [actual scan implementation](https://github.com/gitleaks/gitleaks-action/blob/e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e/src/gitleaks.js) adds event-specific ranges, not `--no-git`. Reproduce that Action's argument set for the actual proposed event separately:

```bash
# Set SCAN_BASE and SCAN_HEAD to the reviewed actual event's commit IDs.
# For push when the Action resolves identical base/head:
gitleaks detect --redact -v --exit-code=2 --report-format=sarif \
  --report-path="$CLEANUP_WORKDIR/default-action.sarif" --log-level=debug \
  --log-opts=-1
# For PRs or pushes with differing base/head, run this alternative:
gitleaks detect --redact -v --exit-code=2 --report-format=sarif \
  --report-path="$CLEANUP_WORKDIR/default-action.sarif" --log-level=debug \
  --log-opts="--no-merges --first-parent ${SCAN_BASE}^..${SCAN_HEAD}"
```

Choose the event's applicable command; do not invent the base/head IDs or claim an offline scan reproduced a future GitHub event. Keep redacted SARIF private. If a force-push event refers to an old object absent locally, stop and inspect the event/Action behavior; never bypass the explicit full-history scan.

## 5. Separately approved remap commit

Only after the scans pass and the owner separately authorizes this commit:

```bash
git -C "$REWRITE" status --short
# Expected sole edit: .gitleaksignore
git -C "$REWRITE" add -- .gitleaksignore
git -C "$REWRITE" diff --cached --check
git -C "$REWRITE" diff --cached -- .gitleaksignore
git -C "$REWRITE" commit -m 'security: remap approved synthetic fingerprints after history cleanup'
```

This new `main` tip is a documented addition after preservation validation. Record its parent and new OID, verify its parent equals the mapped source main tip, and verify its only changed path is `.gitleaksignore`. Do not pretend this new tip still equals filter-repo's original ref-map entry. The mirror and checkout are separate: synchronize only the approved `main` destination into the mirror and record the resulting OID under separate authorization:

```bash
git -C "$REWRITE" push origin 'refs/heads/main:refs/heads/main'
```

Here `origin` is the private sanitized mirror, not GitHub. Verify it before executing. Repeat all scans from step 4 and the applicable default Action command after this commit. Each branch must use its remapped approved configuration when CI runs there; prepare separately reviewed per-branch commits as needed, document each parent/OID and rerun scans. Do not publish branches whose ignore file still uses old SHAs and then declare their CI verified.

## 6. Lease-protected, explicit publication

Get separate owner approval for the exact branch/tag list. The following selects every inventoried branch/tag only if that is the approved list. An owner-approved subset must be prepared explicitly and justified; non-published contaminated refs prevent full incident closeout.

```bash
git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$REMOTE_NOW"
diff -u "$EXPECTED_REMOTE" "$REMOTE_NOW"
declare -a LEASE_ARGS=()
declare -a REFSPECS=()
: > "$EXPECTED_AFTER"
while IFS=$'\t' read -r EXPECTED_SHA REF; do
  case "$REF" in refs/heads/*|refs/tags/*) ;; *) exit 1 ;; esac
  git -C "$MIRROR" show-ref --verify --quiet "$REF"
  NEW_SHA="$(git -C "$MIRROR" rev-parse --verify "$REF")"
  LEASE_ARGS+=("--force-with-lease=$REF:$EXPECTED_SHA")
  REFSPECS+=("$REF:$REF")
  printf '%s\t%s\n' "$NEW_SHA" "$REF" >> "$EXPECTED_AFTER"
done < "$EXPECTED_REMOTE"
LC_ALL=C sort -k2,2 -o "$EXPECTED_AFTER" "$EXPECTED_AFTER"
git -C "$MIRROR" push --dry-run --atomic \
  "${LEASE_ARGS[@]}" "$REMOTE_URL" "${REFSPECS[@]}"
# STOP for explicit owner publication approval of the dry-run and all OIDs.
git -C "$MIRROR" push --atomic \
  "${LEASE_ARGS[@]}" "$REMOTE_URL" "${REFSPECS[@]}"
git ls-remote --refs "$REMOTE_URL" 'refs/heads/*' 'refs/tags/*' \
  | LC_ALL=C sort -k2,2 > "$REMOTE_NOW"
diff -u "$EXPECTED_AFTER" "$REMOTE_NOW"
```

Each lease uses its captured prepublication old object ID. Recheck the full remote snapshot immediately before publishing; any change requires stopping and rebuilding. Never use blind mirror publication, unchecked force, unconditional tag overwrite, or deletion of protected/GitHub-managed refs. If atomic publication is unsupported or protections reject it, stop for an explicitly reviewed alternative.

## 7. GitHub PR refs and caches

```bash
git ls-remote "$REMOTE_URL" 'refs/pull/*' > "$CLEANUP_WORKDIR/pull-refs-after.tsv"
git -C "$MIRROR" fetch --no-tags "$REMOTE_URL" \
  '+refs/pull/*/head:refs/audit/pull/*/head' \
  '+refs/pull/*/merge:refs/audit/pull/*/merge'
COMPROMISED_BLOB="$(git -C "$SOURCE" rev-parse --verify \
  '0b0ff26af9e2cb175888bf88ae2e4abca95fd2c9:audit/evidence/security-2026-10-12/recovery-harness-before.txt')"
python3 - "$MIRROR" "$MIRROR/filter-repo/commit-map" "$COMPROMISED_BLOB" <<'PY'
from pathlib import Path
import subprocess, sys
repo, mapping, compromised_blob = sys.argv[1:]
# Unchanged old==new commits are legitimate shared ancestry. Only replaced or
# removed old commits are contaminated-history candidates.
old = {a for a, b in (line.split() for line in Path(mapping).read_text().splitlines()[1:]) if a != b}
def git(*args):
    return subprocess.check_output(['git', '-C', repo, *args], text=True).splitlines()
refs = git('for-each-ref', '--format=%(refname)', 'refs/audit/pull')
for ref in refs:
    retained = old.intersection(git('rev-list', ref))
    assert not retained, f'STOP: {ref} reaches {len(retained)} replaced/removed source commits'
    objects = {line.split()[0] for line in git('rev-list', '--objects', ref)}
    assert compromised_blob not in objects, f'STOP: {ref} reaches the compromised blob'
print(f'PASS: {len(refs)} PR histories reach no replaced/removed source commits')
PY
```

Compare PR inventories before/after. A tip change is not proof of non-reachability. Also verify absence of the known compromised blob by object ID across each fetched PR's reachable objects without displaying file contents. Even a clean reachable set does not prove GitHub cached objects are purged. Follow [GitHub's sensitive-data-removal procedure](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository), including Support where applicable. Support decides eligibility; it does not guarantee removal for a credential already mitigated by rotation. Never manipulate GitHub-managed PR refs directly.

## 8. Attribute cleanup and collaborators, after verified publication

Only after intended sanitized refs are published, the known blob is unreachable through them, and the owner approves a further commit: remove only the stale `-diff` line and associated comment for `audit/evidence/security-2026-10-12/recovery-harness-before.txt` from `.gitattributes`. Retain the evidence whitespace rule. Rerun both scanner modes and publish this ordinary reviewed cleanup separately. No replacement exclusion is permitted.

Require collaborators to re-clone, refresh CI/deployment checkouts, and prevent stale clones pushing old history. Reapply only reviewed changes to sanitized branches; never merge contaminated ancestry. Preserve recovery backups privately. No irreversible GC until all recovery and verification gates are complete.

## 9. Local tree refs: separate explicit deletion approval

A read-only inventory on 2026-10-17 found **21** local review tree refs (the earlier report had 19); one reaches the known compromised blob. Snapshot counts may grow as Codex captures work. Re-inventory at maintenance time. The private inventory is `/tmp/concierge-local-tree-refs.json` for this session; it includes types/OIDs/path flags, no contents. No local ref was deleted.

Before any deletion, compare with remote advertised refs and establish the snapshots were never published. Do not infer this merely from their namespace. Then, only with separate owner approval:

```bash
git -C "$TOOLS" for-each-ref --format='%(refname) %(objectname)' \
  refs/codex/turn-diffs > "$CLEANUP_WORKDIR/local-tree-refs-before.tsv"
# Review every row, object type, reachability, and never-published evidence first.
while read -r REF EXPECTED_OID; do
  case "$REF" in refs/codex/turn-diffs/*) ;; *) exit 1 ;; esac
  git -C "$TOOLS" update-ref -d "$REF" "$EXPECTED_OID"
done < "$CLEANUP_WORKDIR/local-tree-refs-before.tsv"
```

Verify no remaining local ref reaches the compromised blob, by object IDs and tree traversal only. Keep snapshots out of publication. Do not run GC as part of the loop.

## Final milestone ledger

Use PASS, FAIL, BLOCKED or NOT VERIFIED individually for: source isolation, historical incident, owner revocation confirmation, independent revocation evidence, preparation tooling, real ref/commit preservation, ten-fingerprint remap, default Action scan, explicit text scan, publication, GitHub branches/tags, PR reachability/caches, attribute cleanup, local ref cleanup, collaborator recovery and CI. Incident closure requires evidence for every applicable gate; source tests alone cannot close the historical incident.
