# 11 — Operations & Reliability

## Availability posture
- Single-process uvicorn, single SQLite file. Zero horizontal redundancy in current compose. This is acceptable for a single-property LAN appliance; it is NOT a HA topology.
- Graceful degradation: chat path has provider fallback (primary → legacy orchestrator → deterministic KB answers via fast-path). If AI unreachable but app healthy, /health still OK, guests get fast-path answers for curated intents and graceful "I could not confirm" responses otherwise.

## Findings
- OPS-021 (MED, pre-existing): mobile-chrome guest fast-path answers sometimes return a generic dining overview instead of the curated fast answer (breakfast → "6:30 AM"). Root cause: fast-path in main.py only triggers for the exact normalized intent/contact tuple; on mobile-chrome runs the deployed knowledge/department content set was different or context path exceeded depth. Action: (a) unit-test the fast-path decision table (add fixtures), (b) move curated intents to a single source of truth (property JSON), (c) either make fast-path resilient or treat mobile viewport as desktop for answer-picking bugs to not change answer text based on viewport. Not caused by audit changes (no fast-path code touched).
- OPS-020 (MED): rate limits are in-memory per-process; two uvicorn workers would double allowance. Recommend moving limit counters to SQLite/Redis-per-IP when scaling, and adding coarse per-IP chat gate at LB.
- DEP-002 (LOW): uvicorn single worker by default in Docker (uvicorn app.main:app). For QPS>200 consider workers=2 with a shared sessions store (session store is DB-backed, works multi-process; in-memory rate limits and Gate later need shared store).
- Observability: request telemetry exists (observability.py); recommend exporting metrics (fastapi instrumentation) — currently logs only.

## Monitoring recommendations
1. `/health` now wired to Docker HEALTHCHECK (see 12) → auto-restart on deadlock only (restart:unless-stopped). This fixes silent zombie instances.
2. Add log shipping (JSON logs) to a host journal/loki; alert on `fallback` and provider errors (today console + no alerting).
3. DB backups: enable SQLite `wal` + nightly `sqlite3 .backup` cron; document restore path. (DEP-003)