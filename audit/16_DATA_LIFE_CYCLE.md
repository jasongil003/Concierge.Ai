# 16 — Data Life Cycle & Privacy

## What data exists
- Guest identity (device hashes, anonymous), stay/memory hints, chat transcripts, service requests (name/room/notes), uploads (documents), location analytics (MAC-derived counts), admin audit log, AI provider credentials & spend, webhook payloads (transient).

## Lifecycle today
- Sessions: TTL 30 min, auto-expire; memory persists per client_id (property-scoped). No explicit "delete my data" guest API (GDPR-style) — gap.
- Uploads: stored under uploads dir (root = DB_PATH/subdir); scrubbed for known PII? filename stored; content stored raw (uploaded doc for summarization). Size cap 1MB; MIME allow-list.
- Service requests: persist indefinitely for ops; fields include room#, guest name (free-text). No retention policy or expiry beyond UI audit.
- Chat transcripts: stored in session store; auto-pruned on session expiry or kept? (session store keeps transcribed history with TTL config (session_history_retention_minutes setting exists); check default and set a policy).
- Analytics: occupancy/time heatmaps per property; aggregated, not raw identifiers (location_analytics). Retention not configured.
- Credentials: Fernet-encrypted; rotation procedure documented (DEP-006).
- Reports: generated on demand, ephemeral files in report output dir; no automatic purge.

## Recommendations
1. Add guest `GET /api/guest/memory` + `DELETE /api/guest/memory` (property-scoped) for "forget me".
2. Define retention: sessions 30d, transcripts 90d, uploads 180d (config settings), analytics 12mo; schedule purge job.
3. Restrict reporting exports output dir to or require operator cleanup.
4. Privacy banner already on guest app (mentions Google Places + providers). Add explicit "no data leaves property except to configured AI providers" line to match Posture section.
5. Consent for AI-assisted transcription optional toggle in property settings.