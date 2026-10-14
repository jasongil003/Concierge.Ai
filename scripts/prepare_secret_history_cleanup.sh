#!/usr/bin/env bash
# Prepare a sanitized Git mirror. Does not push, rotate credentials, or modify the source checkout.
set -euo pipefail

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
[[ ! -e "$target" ]] || { echo "Output already exists; refusing overwrite: $target" >&2; exit 1; }
git -C "$source_repo" rev-parse --is-inside-work-tree >/dev/null ||
  { echo "Source is not a Git worktree" >&2; exit 1; }
remote_url="$(git -C "$source_repo" config --get remote.origin.url || true)"
case "$remote_url" in
  *github.com:jasongil003/Concierge.Ai|*github.com:jasongil003/Concierge.Ai.git|*github.com/jasongil003/Concierge.Ai|*github.com/jasongil003/Concierge.Ai.git) ;;
  *) echo "Unexpected source remote: $remote_url (expected $EXPECTED_REPO); refusing." >&2; exit 1 ;;
esac

echo "Creating a separate full mirror, including local refs. Source remains untouched."
git clone --mirror --no-local "$source_repo" "$target"
echo "Removing the known credential-bearing evidence path from all mirrored history."
git -C "$target" filter-repo --force --path "$SENSITIVE_PATH" --invert-paths

if git -C "$target" rev-list --objects --all | grep -F " $SENSITIVE_PATH" >/dev/null; then
  echo "FAILED: sensitive path is still reachable. Do not publish this mirror." >&2
  exit 1
fi
echo "PASS: sensitive path no longer appears in reachable objects by path."
echo "IMPORTANT: Do NOT push this mirror until the credential issuer confirms revocation."
echo "IMPORTANT: Verify all other refs, forks, mirrors, PR refs and collaborator clones."
echo "IMPORTANT: Run Gitleaks 8.24.3 with --all --text on the sanitized mirror before any push."
echo "IMPORTANT: A history rewrite requires an approved force-push maintenance window and re-cloning."
echo "Sanitized mirror: $target"
