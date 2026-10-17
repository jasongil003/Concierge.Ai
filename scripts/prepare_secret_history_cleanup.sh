#!/usr/bin/env bash
# Prepare a sanitized Git mirror. Does not push, rotate credentials, or modify the source checkout.
set -euo pipefail
umask 077

SENSITIVE_PATH="audit/evidence/security-2026-10-12/recovery-harness-before.txt"
EXPECTED_REPO="jasongil003/Concierge.Ai"

usage() {
  printf 'Usage: %s <local-repository-path> <new-output-directory>\n' "$0" >&2
  printf 'Requires git and git-filter-repo; creates a separate sanitized mirror, NEVER pushes.\n' >&2
  exit 2
}
[[ $# -eq 2 ]] || usage
command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v git-filter-repo >/dev/null || { echo "git-filter-repo is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required for preservation verification" >&2; exit 1; }

source_repo="$(cd "$1" && pwd -P)"
target="$2"
case "$target" in
  /*) ;;
  *) target="$PWD/$target" ;;
esac
target_name="$(basename "$target")"
target_parent="$(dirname "$target")"
[[ "$target_name" != "." && "$target_name" != ".." ]] ||
  { echo "Output must name a new directory; refusing." >&2; exit 1; }
[[ -d "$target_parent" ]] ||
  { echo "Output parent directory must already exist; refusing." >&2; exit 1; }
target_parent="$(cd "$target_parent" && pwd -P)"
target="$target_parent/$target_name"
[[ ! -e "$target" && ! -L "$target" ]] ||
  { echo "Output already exists; refusing overwrite." >&2; exit 1; }
if [[ "$source_repo" == "/" || "$target" == "$source_repo" || "$target" == "$source_repo/"* ]]; then
  echo "Output must be outside the source checkout; refusing." >&2
  exit 1
fi
git -C "$source_repo" rev-parse --is-inside-work-tree >/dev/null ||
  { echo "Source is not a Git worktree" >&2; exit 1; }
remote_url="$(git -C "$source_repo" config --get remote.origin.url || true)"
case "$remote_url" in
  *github.com:jasongil003/Concierge.Ai|*github.com:jasongil003/Concierge.Ai.git|*github.com/jasongil003/Concierge.Ai|*github.com/jasongil003/Concierge.Ai.git) ;;
  *) echo "Unexpected source remote (expected $EXPECTED_REPO); refusing." >&2; exit 1 ;;
esac

# A fresh full clone should have matching local and origin-tracking tips for
# every branch that exists in both namespaces. Refuse ambiguous snapshots
# before cloning, since filter-repo can discard one side of a collision.
while IFS= read -r local_ref; do
  branch="${local_ref#refs/heads/}"
  remote_ref="refs/remotes/origin/$branch"
  if git -C "$source_repo" show-ref --verify --quiet "$remote_ref"; then
    local_tip="$(git -C "$source_repo" rev-parse --verify "$local_ref^{commit}")"
    remote_tip="$(git -C "$source_repo" rev-parse --verify "$remote_ref^{commit}")"
    if [[ "$local_tip" != "$remote_tip" ]]; then
      printf 'Local and origin-tracking refs disagree for %s; refresh/reconcile the source clone and retry.\n' "$branch" >&2
      exit 1
    fi
  fi
done < <(git -C "$source_repo" for-each-ref --format='%(refname)' refs/heads)

target_created=1
cleanup_target_on_failure() {
  local exit_status=$?
  trap - EXIT
  if [[ "$exit_status" -ne 0 && "$target_created" -eq 1 && -e "$target" ]]; then
    if ! rm -rf "$target"; then
      printf 'Could not remove incomplete mirror; inspect it locally: %s\n' "$target" >&2
    fi
  fi
  exit "$exit_status"
}
trap cleanup_target_on_failure EXIT

echo "Creating a separate full mirror, including local refs. Source remains untouched."
git clone --mirror --no-local "$source_repo" "$target"
source_ref_manifest="$target/source-ref-manifest.tsv"
source_commit_manifest="$target/source-ref-commits.tsv"
: > "$source_ref_manifest"
: > "$source_commit_manifest"
# Codex keeps local review snapshots as tree refs. git-filter-repo cannot
# rewrite non-commit refs, and a mirror of this checkout otherwise retains the
# credential-bearing path through them. Drop only these local snapshots in the
# disposable mirror; commit and annotated-tag refs are snapshotted for the
# preservation gate, and every other non-commit ref is rejected for review.
while read -r ref kind symref; do
  if [[ -n "$symref" ]]; then
    continue
  elif [[ "$kind" == commit || "$kind" == tag ]]; then
    tip="$(git -C "$target" rev-parse --verify "$ref")"
    if ! peeled_tip="$(git -C "$target" rev-parse --verify "$ref^{commit}" 2>/dev/null)"; then
      printf 'Ref does not resolve to a commit; refusing: %s\n' "$ref" >&2
      exit 1
    fi
    source_count="$(git -C "$target" rev-list --count "$peeled_tip")"
    printf '%s\t%s\t%s\t%s\t%s\n' "$ref" "$kind" "$tip" "$peeled_tip" "$source_count" >> "$source_ref_manifest"
    git -C "$target" rev-list "$peeled_tip" | while IFS= read -r commit; do
      printf '%s\t%s\n' "$ref" "$commit" >> "$source_commit_manifest"
    done
  elif [[ "$kind" == tree && "$ref" == refs/codex/turn-diffs/* ]]; then
    git -C "$target" update-ref -d "$ref"
  else
    echo "Unexpected non-commit mirror ref; refusing." >&2
    exit 1
  fi
done < <(git -C "$target" for-each-ref --format='%(refname) %(objecttype) %(symref)')
echo "Removing the known credential-bearing evidence path from all mirrored history."
git -C "$target" filter-repo --force --path "$SENSITIVE_PATH" --invert-paths

# Validate every snapshotted ref against filter-repo's maps, then compare each
# rewritten ref's commit count with the unique surviving mapped commits from
# that ref. Path-only commits may map to null or collapse onto a mapped parent;
# any other unexplained loss fails closed.
python3 - "$target" "$source_ref_manifest" "$source_commit_manifest" <<'PY'
from pathlib import Path
import re
import subprocess
import sys

repo = Path(sys.argv[1])
ref_manifest = Path(sys.argv[2])
commit_manifest = Path(sys.argv[3])
metadata = repo / "filter-repo"
null_sha = "0" * 40
sha_pattern = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    raise SystemExit(f"FAILED: {message}. Do not publish this mirror.")


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        fail(f"git {' '.join(arguments)} could not be verified")
    return result.stdout.strip()


def read_map(path: Path, expected_header: list[str], row_size: int) -> list[list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        fail(f"missing filter-repo map {path.name}")
    if not lines or lines[0].split() != expected_header:
        fail(f"unexpected {path.name} header")
    rows = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != row_size:
            fail(f"malformed {path.name} row")
        rows.append(fields)
    return rows


commit_map = {}
for old, new in read_map(metadata / "commit-map", ["old", "new"], 2):
    if not sha_pattern.fullmatch(old) or not sha_pattern.fullmatch(new):
        fail("invalid hash in commit-map")
    commit_map[old] = new

ref_map = {}
for old, new, ref in read_map(metadata / "ref-map", ["old", "new", "ref"], 3):
    if not sha_pattern.fullmatch(old) or not sha_pattern.fullmatch(new):
        fail("invalid hash in ref-map")
    ref_map[ref] = (old, new)

source_refs = []
for line in ref_manifest.read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if len(fields) != 5:
        fail("malformed source ref manifest")
    ref, object_type, old_tip, old_commit_tip, old_count = fields
    if not sha_pattern.fullmatch(old_tip) or not sha_pattern.fullmatch(old_commit_tip):
        fail(f"invalid source hash for {ref}")
    try:
        old_count_value = int(old_count)
    except ValueError:
        fail(f"invalid source commit count for {ref}")
    source_refs.append((ref, object_type, old_tip, old_commit_tip, old_count_value))

commits_by_ref = {}
for line in commit_manifest.read_text(encoding="utf-8").splitlines():
    fields = line.split("\t")
    if len(fields) != 2 or not sha_pattern.fullmatch(fields[1]):
        fail("malformed source commit manifest")
    commits_by_ref.setdefault(fields[0], []).append(fields[1])

for ref, _object_type, old_tip, old_commit_tip, old_count in source_refs:
    mapped_ref = ref_map.get(ref)
    if mapped_ref is None:
        fail(f"ref-map omitted source ref {ref}")
    mapped_old_tip, mapped_new_tip = mapped_ref
    if mapped_old_tip != old_tip:
        fail(f"ref-map source tip does not match {ref}")
    if mapped_new_tip == null_sha:
        fail(f"filter-repo removed source ref {ref}")

    actual_tip = git("rev-parse", "--verify", ref)
    if actual_tip != mapped_new_tip:
        fail(f"rewritten ref tip does not match ref-map for {ref}")

    mapped_commit_tip = commit_map.get(old_commit_tip)
    if mapped_commit_tip in (None, null_sha):
        fail(f"commit-map removed the source commit tip for {ref}")
    actual_commit_tip = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if actual_commit_tip != mapped_commit_tip:
        fail(f"rewritten commit tip does not match commit-map for {ref}")

    mapped_history = set()
    source_history = commits_by_ref.get(ref, [])
    if len(source_history) != old_count:
        fail(f"source commit count changed while recording {ref}")
    for old_commit in source_history:
        new_commit = commit_map.get(old_commit)
        if new_commit is None:
            fail(f"commit-map omitted a source commit reachable from {ref}")
        if new_commit != null_sha:
            mapped_history.add(new_commit)
    rewritten_count = int(git("rev-list", "--count", ref))
    if rewritten_count != len(mapped_history):
        fail(
            f"per-ref commit count mismatch for {ref}: source={old_count}, "
            f"mapped-survivors={len(mapped_history)}, rewritten={rewritten_count}"
        )
    print(
        f"PASS: {ref} tip preserved through ref-map; commits source={old_count}, "
        f"mapped survivors={len(mapped_history)}, rewritten={rewritten_count}"
    )

print(f"PASS: ref-map and per-ref commit preservation verified for {len(source_refs)} refs.")
PY

set +e
git -C "$target" rev-list --objects --all | grep -F " $SENSITIVE_PATH" >/dev/null
scan_status=("${PIPESTATUS[@]}")
set -e
if [[ "${scan_status[0]}" -ne 0 ]]; then
  echo "FAILED: could not inspect reachable objects. Do not publish this mirror." >&2
  exit 1
elif [[ "${scan_status[1]}" -eq 0 ]]; then
  echo "FAILED: sensitive path is still reachable. Do not publish this mirror." >&2
  exit 1
elif [[ "${scan_status[1]}" -ne 1 ]]; then
  echo "FAILED: path verification could not complete. Do not publish this mirror." >&2
  exit 1
fi
echo "PASS: sensitive path no longer appears in reachable objects by path."
echo "IMPORTANT: Do NOT push this mirror until the credential issuer confirms revocation."
echo "IMPORTANT: This mirror includes only refs present in the source checkout; verify they match the current remote."
echo "IMPORTANT: Verify all other refs, forks, mirrors, PR refs and collaborator clones."
echo "IMPORTANT: Run Gitleaks 8.24.3 with --all --text on the sanitized mirror before any push."
echo "IMPORTANT: Reassess SHA-scoped synthetic test exceptions after rewritten commit IDs; do not suppress a real finding."
echo "IMPORTANT: A history rewrite requires an approved force-push maintenance window and re-cloning."
echo "Sanitized mirror: $target"
target_created=0
