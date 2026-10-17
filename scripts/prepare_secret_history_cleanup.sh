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
# Codex keeps local review snapshots as tree refs. git-filter-repo cannot
# rewrite non-commit refs, and a mirror of this checkout otherwise retains the
# credential-bearing path through them. Drop only these local snapshots in the
# disposable mirror; reject every other non-commit ref for manual review.
while read -r ref kind; do
  if [[ "$kind" == commit ]]; then
    continue
  elif [[ "$kind" == tree && "$ref" == refs/codex/turn-diffs/* ]]; then
    git -C "$target" update-ref -d "$ref"
  else
    echo "Unexpected non-commit mirror ref; refusing." >&2
    exit 1
  fi
done < <(git -C "$target" for-each-ref --format='%(refname) %(objecttype)')
echo "Removing the known credential-bearing evidence path from all mirrored history."
git -C "$target" filter-repo --force --path "$SENSITIVE_PATH" --invert-paths

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
