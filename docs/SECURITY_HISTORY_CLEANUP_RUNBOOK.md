# Offline credential-history cleanup verification

This process does not revoke credentials or publish rewritten refs. The real exposed credential must first be revoked by its issuer. Owner authorization is required for any coordinated Git history rewrite.

1. Inventory all branches, tags, PR references, forks, mirrors, backups, collaborators and recorded SHAs. Use a fresh, full local clone; do not use production hosts.
2. Run the already-existing script from the source clone with a new output directory:

    bash scripts/prepare_secret_history_cleanup.sh . ../concierge-sanitized.git

   It rewrites a separate mirror and never pushes.
3. Create a disposable checkout of the sanitized mirror's desired main branch. From the original repository copy of the following helper, remap the existing exact synthetic-test fingerprints only:

    python3 scripts/remap_approved_gitleaks_fingerprints.py ../concierge-sanitized.git/filter-repo/commit-map .gitleaksignore

   Commit the changed ignore file to the disposable rewritten branch, not the original repo. This is not permission to ignore any real credential.
4. In that disposable checkout, run Gitleaks 8.24.3 with the same CI checks:

    gitleaks detect --no-git --source . --redact --no-banner
    gitleaks detect --source . --redact --no-banner --log-opts="--all --text"

   Both must report zero findings. Stop on any real or unreviewed finding; never suppress it to make CI green.
5. Check that the removed transcript path is absent from all reachable objects. Review mappings, ref coverage, rewritten tip contents, the CI workflow and the reintroduction risk.

Only after issuer revocation is confirmed and the repository owner approves the disruption: coordinate a maintenance window, preserve rollback, freeze writes, sanitize or retire affected refs/forks/caches, publish rewritten refs with expected-SHA safeguards, re-clone all collaborators, and rerun every CI job.

Do not alter the secret scanner to omit reachable history. Until these steps are completed, secret-scan is expected to fail.
