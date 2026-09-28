# Release checks for `main`

The GitHub Actions workflow defines these checks:

| Workflow job | Gate |
| --- | --- |
| `backend-tests` | Backend pytest suite, compile check, Python dependency audit |
| `dependency-security` | npm install and high severity dependency audit |
| `static-security` | Bandit application scan |
| `secret-scan` | Gitleaks repository-history scan |
| `browser-tests` | Desktop and mobile Chromium Playwright suite, including visual snapshots |
| `postgres-redis-integration` | Alembic repeatability, SQLite migration, PostgreSQL, Redis, backup/restore, distributed AI bulkhead, 10-user deterministic smoke |
| `docker-runtime-smoke` | Production image build/config validation, Trivy High/Critical scan, non-root/write/persistence smoke |

Configure repository rules for `main` to require every job above before merge,
require branches to be current with `main`, and block force pushes and direct
pushes. GitHub branch-protection settings are external to this repository; this
document and the workflow do not claim those settings are enabled. Do not
enable automatic merge while any required job is running or failing.

CI-generated passwords, encryption keys, and metrics tokens are per-run test
values written to the runner environment. No production secrets belong in the
workflow or repository. Keep image scanning enabled for the exact image built
by the Docker smoke job.
