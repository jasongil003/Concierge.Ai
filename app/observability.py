from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time
from typing import Any, Callable


PERIODS: dict[str, tuple[int, int]] = {
    "1h": (3600, 300),
    "6h": (21600, 900),
    "24h": (86400, 3600),
    "7d": (604800, 21600),
    "30d": (2592000, 86400),
    "today": (86400, 3600),
    "yesterday": (86400, 3600),
}


def period_window(period: str, start_at: int | None = None, end_at: int | None = None) -> tuple[int, int, int]:
    now = int(time.time())
    if period == "custom":
        if start_at is None or end_at is None or start_at >= end_at:
            raise ValueError("Custom periods require a valid start and end time.")
        if end_at - start_at > 366 * 86400:
            raise ValueError("Custom periods cannot exceed 366 days.")
        span = end_at - start_at
        bucket = 300 if span <= 21600 else (3600 if span <= 172800 else (21600 if span <= 1209600 else 86400))
        return start_at, end_at, bucket
    if period in {"today", "yesterday"}:
        local = time.localtime(now)
        midnight = int(time.mktime((local.tm_year, local.tm_mon, local.tm_mday, 0, 0, 0, local.tm_wday, local.tm_yday, local.tm_isdst)))
        return (midnight, now, 3600) if period == "today" else (midnight - 86400, midnight, 3600)
    seconds, bucket = PERIODS.get(period, PERIODS["24h"])
    return now - seconds, now, bucket


@dataclass(frozen=True)
class DiagnosticContext:
    property_id: str
    role_slug: str
    department_id: str | None
    permissions: frozenset[str]
    request_id: str

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionError(f"Permission required: {permission}")


class ObservabilityStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.started_at = int(time.time())
        self._active_requests = 0
        self._request_lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS metric_samples (
                    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    property_id TEXT,
                    metric TEXT NOT NULL,
                    value REAL,
                    unit TEXT NOT NULL DEFAULT '',
                    availability TEXT NOT NULL DEFAULT 'available',
                    source TEXT NOT NULL DEFAULT 'application',
                    recorded_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_metric_samples_lookup
                    ON metric_samples(property_id, metric, recorded_at);
                CREATE TABLE IF NOT EXISTS operational_alerts (
                    alert_id TEXT PRIMARY KEY,
                    property_id TEXT,
                    component TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_operational_alerts_property
                    ON operational_alerts(property_id, active, last_seen_at DESC);
                CREATE TABLE IF NOT EXISTS diagnostic_actions (
                    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    property_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    result_summary TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )

    def request_started(self) -> int:
        with self._request_lock:
            self._active_requests += 1
            return self._active_requests

    def request_finished(self) -> int:
        with self._request_lock:
            self._active_requests = max(0, self._active_requests - 1)
            return self._active_requests

    @property
    def queue_depth(self) -> int:
        with self._request_lock:
            return max(0, self._active_requests - 1)

    def record(self, property_id: str | None, metric: str, value: float | int | None, unit: str = "", availability: str = "available", source: str = "application", recorded_at: int | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO metric_samples(property_id,metric,value,unit,availability,source,recorded_at) VALUES(?,?,?,?,?,?,?)",
                (property_id, metric, None if value is None else float(value), unit, availability, source, recorded_at or int(time.time())),
            )

    def record_request(self, property_id: str | None, latency_ms: float, status_code: int, queue_depth: int) -> None:
        now = int(time.time())
        self.record(property_id, "api_latency_ms", latency_ms, "ms", recorded_at=now)
        self.record(property_id, "http_requests", 1, "request", recorded_at=now)
        self.record(property_id, "http_errors", 1 if status_code >= 500 else 0, "error", recorded_at=now)
        self.record(property_id, "request_queue_depth", queue_depth, "request", recorded_at=now)

    def collect_system(self, property_id: str | None = None) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        try:
            import psutil  # type: ignore

            network = psutil.net_io_counters()
            disk = psutil.disk_usage(str(self.path.parent.resolve()))
            memory = psutil.virtual_memory()
            values = {
                "cpu_utilization": (psutil.cpu_percent(interval=None), "%"),
                "memory_utilization": (memory.percent, "%"),
                "disk_utilization": (disk.percent, "%"),
                "network_rx_bytes": (network.bytes_recv, "bytes"),
                "network_tx_bytes": (network.bytes_sent, "bytes"),
            }
            for metric, (value, unit) in values.items():
                self.record(property_id, metric, value, unit, source="host")
                result[metric] = {"value": value, "unit": unit, "availability": "available"}
        except (ImportError, OSError):
            disk = shutil.disk_usage(str(self.path.parent.resolve()))
            disk_percent = round((disk.used / max(1, disk.total)) * 100, 2)
            self.record(property_id, "disk_utilization", disk_percent, "%", source="stdlib")
            result["disk_utilization"] = {"value": disk_percent, "unit": "%", "availability": "available"}
            for metric in ("cpu_utilization", "memory_utilization", "network_rx_bytes", "network_tx_bytes"):
                self.record(property_id, metric, None, availability="unavailable", source="host")
                result[metric] = {"value": None, "unit": "", "availability": "unavailable"}
        result["application_uptime_seconds"] = {"value": int(time.time()) - self.started_at, "unit": "seconds", "availability": "available"}
        self.record(property_id, "application_uptime_seconds", result["application_uptime_seconds"]["value"], "seconds")
        return result

    def database_health(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            with self._connect() as db:
                db.execute("SELECT 1").fetchone()
                size = self.path.stat().st_size if self.path.exists() else 0
            latency = round((time.perf_counter() - started) * 1000, 2)
            self.record(None, "database_latency_ms", latency, "ms", source="sqlite")
            return {"state": "healthy" if latency < 250 else "warning", "latency_ms": latency, "size_bytes": size, "evidence": f"SQLite probe completed in {latency} ms."}
        except sqlite3.Error as exc:
            self.record(None, "database_latency_ms", None, "ms", "unavailable", "sqlite")
            return {"state": "critical", "latency_ms": None, "size_bytes": None, "evidence": f"Database probe failed: {exc.__class__.__name__}."}

    def history(self, property_id: str | None, metric: str, period: str, start_at: int | None = None, end_at: int | None = None) -> list[dict[str, Any]]:
        cutoff, period_end, bucket = period_window(period, start_at, end_at)
        with self._connect() as db:
            rows = db.execute(
                """SELECT (recorded_at / ?) * ? AS bucket_at, AVG(value) AS average,
                SUM(CASE WHEN value IS NOT NULL THEN 1 ELSE 0 END) AS samples,
                MAX(unit) AS unit, MIN(availability) AS availability
                FROM metric_samples
                WHERE metric=? AND recorded_at>=? AND recorded_at<=? AND (property_id=? OR (? IS NULL AND property_id IS NULL))
                GROUP BY bucket_at ORDER BY bucket_at""",
                (bucket, bucket, metric, cutoff, period_end, property_id, property_id),
            ).fetchall()
        return [
            {"timestamp": int(row["bucket_at"]), "value": None if row["average"] is None else round(float(row["average"]), 2), "samples": int(row["samples"]), "unit": row["unit"], "availability": row["availability"]}
            for row in rows
        ]

    def _table_exists(self, db: sqlite3.Connection, table: str) -> bool:
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    def property_analytics(self, property_id: str, period: str, department_id: str | None = None, start_at: int | None = None, end_at: int | None = None) -> dict[str, Any]:
        start, end, bucket = period_window(period, start_at, end_at)
        seconds = end - start
        previous_start = start - seconds
        with self._connect() as db:
            department_name = None
            if department_id:
                if not self._table_exists(db, "departments"):
                    raise ValueError("Department scope is not available for this property.")
                row = db.execute("SELECT name FROM departments WHERE property_id=? AND department_id=?", (property_id, department_id)).fetchone()
                if row is None:
                    raise ValueError("Department scope is not valid for this property.")
                department_name = row["name"]
            department_sql = " AND department=?" if department_name else ""
            department_params: tuple[Any, ...] = (department_name,) if department_name else ()
            # Property-wide activity cannot be safely attributed to one department; return no such data.
            sessions = db.execute("SELECT COUNT(*) FROM sessions WHERE property_id=? AND created_at>=? AND created_at<=?", (property_id, start, end)).fetchone()[0] if not department_id and self._table_exists(db, "sessions") else 0
            conversations = db.execute("SELECT COUNT(DISTINCT session_id) FROM conversation_messages WHERE property_id=? AND created_at>=? AND created_at<=?", (property_id, start, end)).fetchone()[0] if not department_id and self._table_exists(db, "conversation_messages") else 0
            requests = db.execute(f"SELECT COUNT(*) FROM service_requests WHERE property_id=? AND created_at>=? AND created_at<=?{department_sql}", (property_id, start, end, *department_params)).fetchone()[0] if self._table_exists(db, "service_requests") else 0  # nosec B608
            previous_requests = db.execute(f"SELECT COUNT(*) FROM service_requests WHERE property_id=? AND created_at>=? AND created_at<?{department_sql}", (property_id, previous_start, start, *department_params)).fetchone()[0] if self._table_exists(db, "service_requests") else 0  # nosec B608
            request_rows = db.execute(f"SELECT * FROM service_requests WHERE property_id=? AND created_at>=? AND created_at<=?{department_sql} ORDER BY created_at", (property_id, start, end, *department_params)).fetchall() if self._table_exists(db, "service_requests") else []  # nosec B608
            ai_row = db.execute("SELECT COUNT(*) total,SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) errors,AVG(latency_ms) latency,SUM(total_tokens) tokens FROM ai_usage WHERE property_id=? AND created_at>=? AND created_at<=?", (property_id, start, end)).fetchone() if not department_id and self._table_exists(db, "ai_usage") else None
            ai_time_rows = db.execute("SELECT (created_at / ?) * ? bucket_at,COUNT(*) count FROM ai_usage WHERE property_id=? AND created_at>=? AND created_at<=? GROUP BY bucket_at ORDER BY bucket_at", (bucket, bucket, property_id, start, end)).fetchall() if not department_id and self._table_exists(db, "ai_usage") else []
            ai_provider_rows = db.execute("SELECT provider_id,model,COUNT(*) count FROM ai_usage WHERE property_id=? AND created_at>=? AND created_at<=? GROUP BY provider_id,model ORDER BY count DESC", (property_id, start, end)).fetchall() if not department_id and self._table_exists(db, "ai_usage") else []
            auth_row = db.execute("SELECT COUNT(*) total,SUM(success) success FROM authentication_attempts WHERE property_id=? AND created_at>=? AND created_at<=?", (property_id, start, end)).fetchone() if not department_id and self._table_exists(db, "authentication_attempts") else None
            message_rows = db.execute("SELECT provider,COUNT(*) count FROM conversation_messages WHERE property_id=? AND role='assistant' AND created_at>=? AND created_at<=? GROUP BY provider", (property_id, start, end)).fetchall() if not department_id and self._table_exists(db, "conversation_messages") else []
            question_rows = db.execute("SELECT content,COUNT(*) count FROM conversation_messages WHERE property_id=? AND role='guest' AND created_at>=? AND created_at<=? GROUP BY lower(trim(content)) ORDER BY count DESC LIMIT 10", (property_id, start, end)).fetchall() if not department_id and self._table_exists(db, "conversation_messages") else []

        completed = [row for row in request_rows if row["status"] == "completed"]
        resolution_times = [max(0, int(row["updated_at"]) - int(row["created_at"])) for row in completed]
        overdue = [row for row in request_rows if row["status"] != "completed" and row["due_at"] and int(row["due_at"]) < end]
        departments = Counter(str(row["department"] or "Unassigned") for row in request_rows)
        services = Counter(str(row["request_type"] or row["description"] or "Request") for row in request_rows)
        buckets: dict[int, int] = Counter((int(row["created_at"]) // bucket) * bucket for row in request_rows)
        provider_counts = {str(row["provider"] or "unknown"): int(row["count"]) for row in message_rows}
        fallback_count = sum(count for provider, count in provider_counts.items() if provider in {"verified_fallback", "fast_path", "none"})
        assistant_total = sum(provider_counts.values())
        comparison = None if previous_requests == 0 else round(((requests - previous_requests) / previous_requests) * 100, 1)
        return {
            "period": period, "start": start, "end": end, "department_scope": department_name,
            "summary": {
                "guests_assisted": int(sessions), "ai_conversations": int(conversations), "service_requests": int(requests),
                "open_requests": sum(1 for row in request_rows if row["status"] != "completed"), "overdue_requests": len(overdue),
                "average_resolution_seconds": round(sum(resolution_times) / len(resolution_times)) if resolution_times else None,
                "sla_performance_percent": round((1 - len(overdue) / max(1, len(request_rows))) * 100, 1),
                "ai_resolution_rate_percent": round((assistant_total - fallback_count) / max(1, assistant_total) * 100, 1),
                "fallback_rate_percent": round(fallback_count / max(1, assistant_total) * 100, 1),
                "human_escalation_rate_percent": round(provider_counts.get("human_queue", 0) / max(1, assistant_total) * 100, 1),
                "request_change_percent": comparison,
            },
            "request_volume": [{"timestamp": key, "value": buckets.get(key, 0)} for key in range((start // bucket) * bucket, end + 1, bucket)],
            "busiest_periods": [{"timestamp": key, "requests": value} for key, value in sorted(buckets.items(), key=lambda item: item[1], reverse=True)[:5]],
            "requests_by_department": [{"name": key, "value": value} for key, value in departments.most_common()],
            "top_services": [{"name": key, "value": value} for key, value in services.most_common(10)],
            "top_questions": [{"question": row["content"], "count": int(row["count"])} for row in question_rows],
            "ai": {"requests": int(ai_row["total"] or 0) if ai_row else 0, "errors": int(ai_row["errors"] or 0) if ai_row else 0, "error_rate_percent": round(int(ai_row["errors"] or 0) / max(1, int(ai_row["total"] or 0)) * 100, 1) if ai_row else 0, "average_latency_ms": round(float(ai_row["latency"] or 0), 1) if ai_row and ai_row["latency"] is not None else None, "first_token_latency_ms": None, "first_token_latency_availability": "unavailable", "tokens": int(ai_row["tokens"] or 0) if ai_row else 0, "provider_usage": provider_counts, "provider_model_usage": [{"provider": row["provider_id"], "model": row["model"], "requests": int(row["count"])} for row in ai_provider_rows], "request_volume": [{"timestamp": int(row["bucket_at"]), "value": int(row["count"])} for row in ai_time_rows], "estimated_cost": None},
            "guest_auth": {"attempts": int(auth_row["total"] or 0) if auth_row else 0, "success_rate": round(int(auth_row["success"] or 0) / max(1, int(auth_row["total"] or 0)) * 100, 1) if auth_row else None},
            "raw_requests": [dict(row) for row in request_rows],
        }

    def evaluate_alerts(self, property_id: str, dashboard: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[tuple[str, str, str, str, str]] = []
        summary = dashboard.get("analytics", {}).get("summary", {})
        ai = dashboard.get("analytics", {}).get("ai", {})
        database = dashboard.get("database", {})
        if summary.get("overdue_requests", 0) > 0:
            candidates.append(("request_queue", "warning", "Overdue guest requests", f"{summary['overdue_requests']} request(s) are past their SLA target.", "overdue_requests"))
        if ai.get("requests", 0) and ai.get("errors", 0) / max(1, ai["requests"]) > 0.1:
            candidates.append(("ai_providers", "warning", "AI provider error rate elevated", f"{ai['errors']} of {ai['requests']} provider requests failed in the selected period.", "ai_error_rate"))
        if database.get("state") in {"warning", "critical"}:
            candidates.append(("database", database["state"], "Database probe requires attention", database.get("evidence", "Database health check failed."), "database_latency_ms"))
        now = int(time.time())
        active_ids: set[str] = set()
        with self._connect() as db:
            for component, severity, title, evidence, metric in candidates:
                alert_id = f"{property_id}:{component}:{metric}"
                active_ids.add(alert_id)
                db.execute(
                    """INSERT INTO operational_alerts(alert_id,property_id,component,severity,title,evidence,metric,first_seen_at,last_seen_at,active)
                    VALUES(?,?,?,?,?,?,?,?,?,1) ON CONFLICT(alert_id) DO UPDATE SET severity=excluded.severity,title=excluded.title,evidence=excluded.evidence,last_seen_at=excluded.last_seen_at,active=1""",
                    (alert_id, property_id, component, severity, title, evidence, metric, now, now),
                )
            if active_ids:
                placeholders = ",".join("?" for _ in active_ids)
                db.execute(f"UPDATE operational_alerts SET active=0 WHERE property_id=? AND alert_id NOT IN ({placeholders})", (property_id, *active_ids))  # nosec B608
            else:
                db.execute("UPDATE operational_alerts SET active=0 WHERE property_id=?", (property_id,))
        return self.alerts(property_id)

    def alerts(self, property_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM operational_alerts WHERE property_id=? AND active=1 ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END,last_seen_at DESC", (property_id,)).fetchall()
        return [{**dict(row), "active": bool(row["active"]), "links": {"metrics": "system-health", "assistant": "ai-assistant"}} for row in rows]

    def recent_errors(self, property_id: str, period: str) -> list[dict[str, Any]]:
        seconds, _ = PERIODS.get(period, PERIODS["1h"])
        cutoff = int(time.time()) - seconds
        with self._connect() as db:
            ai = db.execute("SELECT provider_id component,error_type,latency_ms,created_at FROM ai_usage WHERE property_id=? AND success=0 AND created_at>=? ORDER BY created_at DESC LIMIT 50", (property_id, cutoff)).fetchall() if self._table_exists(db, "ai_usage") else []
            deliveries = db.execute("SELECT 'webhook' component,error error_type,NULL latency_ms,attempted_at created_at FROM webhook_deliveries WHERE property_id=? AND status!='delivered' AND attempted_at>=? ORDER BY attempted_at DESC LIMIT 50", (property_id, cutoff)).fetchall() if self._table_exists(db, "webhook_deliveries") else []
        return [dict(row) for row in [*ai, *deliveries]][:50]

    def log_diagnostic(self, request_id: str, property_id: str, actor_user_id: str, tool_name: str, timeframe: str, summary: str) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO diagnostic_actions(request_id,property_id,actor_user_id,tool_name,timeframe,result_summary,created_at) VALUES(?,?,?,?,?,?,?)", (request_id, property_id, actor_user_id, tool_name, timeframe, summary[:1000], int(time.time())))


class DiagnosticToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {}

    def register(self, name: str, permission: str, function: Callable[..., dict[str, Any]]) -> None:
        self._tools[name] = (permission, function)

    def run(self, name: str, context: DiagnosticContext, **kwargs: Any) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError("Unknown diagnostic tool.")
        permission, function = self._tools[name]
        context.require(permission)
        return function(context=context, **kwargs)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)
