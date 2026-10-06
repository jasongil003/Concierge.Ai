# Release checks for `main`

## Required CI jobs

The `CI` workflow runs these seven checks for every pull request targeting
`main`:

| Required status check | What it covers |
| --- | --- |
| `backend-tests` | Full pytest suite, Python compilation, and Python dependency audit |
| `dependency-security` | npm install and high severity npm audit |
| `static-security` | Bandit application scan |
| `secret-scan` | Gitleaks scan of repository history |
| `browser-tests` | Playwright desktop Chromium and mobile Chrome functional and visual suite |
| `postgres-redis-integration` | Repeatable Alembic migrations, existing SQLite data migration, PostgreSQL and Redis checks, fresh PostgreSQL app startup, and deterministic 10-user smoke |
| `docker-runtime-smoke` | Production image build/config validation, Trivy scan, non-root/write/health/persistence checks |

These job names must be selected as separate required checks. The workflow has
no path filters or PR-only job conditions that intentionally skip a required
check. A required check from an older commit does not satisfy the latest
commit's requirement.

## Exact GitHub repository rule for `main`

Configure this in **Repository Settings → Rules → Rulesets** (or create an
equivalent branch protection rule under **Settings → Branches**):

1. Create an active branch ruleset targeting the exact branch `main`.
2. Leave the bypass list empty. Apply the rules to administrators as well.
3. Enable **Require a pull request before merging**. Do not allow direct pushes
   or a pull-request bypass.
4. Enable **Require status checks to pass before merging** and add each of the
   seven job names listed above as its own required check.
5. Enable **Require branches to be up to date before merging** (strict status
   checks against the latest `main`).
6. Enable **Block force pushes** and keep **Allow deletions** disabled.
7. Do not enable a merge queue unless the workflow is also configured to run
   on GitHub's `merge_group` event and its required checks have been verified.

GitHub blocks a merge while any required check is pending, failed, or
cancelled. Re-run a failed or cancelled check on the latest commit and wait for
all seven checks to succeed before merging. GitHub may treat skipped or neutral
checks as acceptable, so preserve the workflow's unconditional PR job runs and
do not add path filters that can skip a required job. See GitHub's documentation
for [protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets),
and [status checks](https://docs.github.com/en/pull-requests/reference/status-checks).

Repository settings are stored by GitHub and cannot be enabled by this file or
by the CI workflow. Confirm the ruleset in GitHub after an administrator saves
it; this repository does not claim the rule is currently enabled.

## CI credential handling

CI-generated bootstrap passwords, encryption keys, and metrics tokens are
one-run test values written to the runner environment. No production secrets
belong in the workflow or repository. Keep image scanning enabled for the exact
image built by the Docker smoke job.

## Stable appliance release integrity

The appliance updater consumes the versioned tarball from a stable
`vMAJOR.MINOR.PATCH` GitHub Release only. It checks release metadata and
SHA-256 before unpacking; metadata binds the artifact name, commit, UTC build
timestamp, and schema compatibility range. The packaging workflow checks that
the tag resolves to the checked-out commit, creates the archive from that tag
with deterministic gzip metadata, and does not use `--clobber`. Do not replace
an already published version's assets or reuse a release tag.

Before publishing any production release, configure these repository
settings:

- `RELEASE_TAG_PUBLIC_KEY` as a GitHub Actions secret containing the trusted
  ASCII-armored public GPG key. Store only the public key in GitHub; keep its
  private signing key offline or in the approved signing service.
- `RELEASE_TAG_SIGNER_FINGERPRINT` as a repository Actions variable containing
  the exact 40- or 64-character fingerprint for that public key.

Both values are mandatory. The release workflow fails closed when either is
missing, when the fingerprint is malformed, when the tag is not signed by that
key, or when the tag does not point to the checked-out release commit. A
production release cannot be published until the approved signer is configured.
Never trust `main` as the appliance update input. Keep release creation and
asset replacement permissions limited to release operators and preserve the
immutable tag-to-commit and artifact-to-checksum record.
