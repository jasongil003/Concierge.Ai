# PostgreSQL and Redis acceptance

## Architecture

The repository supports SQLite and PostgreSQL through `app/database.py`. PostgreSQL uses SQLAlchemy with the psycopg 3 driver and bounded pool/timeouts. Redis is configured as an optional component (`REDIS_URL`); individual routes/stores must be checked before attributing a behavior to Redis. SQLite remains the local default. Phase 4 did not point at a shared database or cache.

## Environment result

**BLOCKED.** No PostgreSQL or Redis service binaries were available. Docker CLI was present but the Docker daemon/socket was unavailable. No disposable service container or instance could be started. SQLite unit tests are not evidence of PostgreSQL concurrency, Redis distribution, or restore acceptance.

## Reproducible staging/container acceptance

Use isolated disposable services and a separate synthetic application environment. Pin service image versions and store the source SHA and sanitized logs. Never use production URLs or shared credentials.

### PostgreSQL

1. Start an empty disposable PostgreSQL instance; configure a test-only `DATABASE_URL` and run repository migrations from the prior approved schema.
2. Run `pytest -q tests/test_postgres_sqlite_migration.py` and the PostgreSQL-marked migration/store tests.
3. Verify clean initialization, additive facility metadata migration, encrypted messages and turns, session expiry/revocation, property isolation, and concurrent transactions.
4. Create a synthetic backup with `pg_dump`, verify archive/listing and checksum, restore with `pg_restore` into a second empty database, and verify counts plus decrypted synthetic transcript reads.
5. Inject a failed additive migration into a disposable clone, verify transaction recovery and application startup, then destroy only the disposable services.

### Redis

1. Inspect route/store wiring and identify which rate limits, provider bulkheads, and expiry data actually use Redis in the candidate. Record local fallback semantics from code.
2. Start isolated Redis and exercise expiry, concurrent workers, rate limiting, provider slots, restart persistence/fallback, and failure recovery using synthetic sessions.
3. Verify a Redis outage does not bypass authorization or tenant scope; record whether each feature fails closed or uses its documented fallback.

Do not mark acceptance passed until service logs and test outputs from a disposable run are attached to the release evidence.
