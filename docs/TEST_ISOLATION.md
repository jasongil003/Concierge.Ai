# Test state isolation

Pytest is an explicit test profile. `tests/conftest.py` sets `APP_ENVIRONMENT=test`, `CONCIERGE_TESTING=1`, and a fresh `STATE_DIRECTORY`, `DB_PATH`, and `UPLOAD_ROOT` before importing the application. Each pytest process, including each parallel worker, allocates its own system-temporary directory. The directory is removed at normal process exit.

Application startup rejects test-mode paths unless the database, state directory, and uploads are all under the system temporary directory and under the same isolated state root. It also rejects names containing `prod`, `production`, or `live`. Test-mode PostgreSQL and Redis connections are allowed only on loopback; use disposable local services and synthetic data. Development keeps the documented `state/concierge.db` default, and production validation is unchanged.

Playwright creates a unique temporary state root for each run, sets the same explicit test markers, uses its own SQLite database and uploads directory, and never reuses a server already listening on the test port. The default server wrapper forwards shutdown signals and removes only the generated root directly beneath the system temporary directory. If `PLAYWRIGHT_SERVER_COMMAND` overrides the wrapper, that custom server command is responsible for cleaning its own isolated state.

## Persistent database safeguard

Pytest records the path, size, nanosecond modification time, and SHA-256 of `state/concierge.db` before test imports, including SQLite `-wal`, `-shm`, and `-journal` sidecars. It compares the same metadata at session end and fails the suite if any value changes. The safeguard reports before/after evidence and never deletes, restores, or overwrites the persistent database. A hash mismatch is a test isolation failure; preserve the changed file for investigation.

The full suite can be run as usual:

```bash
python -m pytest
```

The pytest header prints the baseline SHA-256. The final `Persistent/default SQLite database changed during tests` section indicates failure and identifies changed files. Do not restore a database automatically.

When launching the app manually for an isolated test, configure all three paths together before importing `app.main`:

```bash
test_state="$(mktemp -d "${TMPDIR:-/tmp}/concierge-test.XXXXXX")"
export APP_ENVIRONMENT=test CONCIERGE_TESTING=1
export STATE_DIRECTORY="$test_state"
export DB_PATH="$test_state/concierge.db"
export UPLOAD_ROOT="$test_state/uploads"
```

Remove only that newly created `test_state` directory after the process has exited. If test startup refuses a path, correct the test configuration; never point a test run at `state/concierge.db` or a hotel environment.
