# 14 — Monitoring & Observability

## In product
- observability.py request telemetry + diagnostics registry: /api/admin diagnostics exposes check_dns/check_ssl/... (admin-only).
- SecurityAuditLogger records admin actions with outcome codes.
- Webhook delivery attempts logged.
- Logs: uvicorn access log on stdout (docker). No structured JSON, no metric export, no alerting.

## Gaps
1. No Prometheus/OpenTelemetry metrics endpoint. Recommend exposing /metrics (prometheus-client) with: chat_total{provider,outcome}, ai_latency_histogram, rate_limit_rejections, webhook failures, admin_login_failures, sqlite_ops.
2. No alert rules/1st-class log shipping. Recommend journald→loki or filebeat in compose.
3. /health now in HEALTHCHECK (12) but returns only static ok; extend to include DB reachability (SELECT 1) + AI provider up/down (non-blocking) so compose auto-restart triggers on degraded-but-alive states. (DEP-009)
4. Showdog for guardrails: add structured log emission from PrivacyGuard/ActionGuard hits with outcome reason (blocked/refused) for SIEM correlation; today these are ad-hoc.

## Recommended alert set
- provider fallback fired
- provider spend near limit (once limits enforcement lands, 09)
- repeated auth failures per username
- webhook delivery failure after retries
- rate-limit saturation
- container restarts