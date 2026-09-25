"""Process-local Prometheus metrics for request and dependency health.

Metrics deliberately stay out of the transactional database. Prometheus scrapes
this bounded in-memory registry from each API replica.
"""

from __future__ import annotations

import threading

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "concierge_http_requests_total",
    "HTTP responses served by this API replica.",
    ("method", "route", "status_class"),
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION = Histogram(
    "concierge_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=REGISTRY,
)
HTTP_ERRORS = Counter(
    "concierge_http_errors_total",
    "HTTP responses with a 4xx or 5xx status code.",
    ("method", "route", "status_class"),
    registry=REGISTRY,
)
ACTIVE_REQUESTS = Gauge(
    "concierge_active_requests",
    "Requests currently being handled by this API replica.",
    registry=REGISTRY,
)
REQUEST_QUEUE_DEPTH = Gauge(
    "concierge_request_queue_depth",
    "Concurrent requests above one currently handled by this API replica.",
    registry=REGISTRY,
)
RATE_LIMIT_EVENTS = Counter(
    "concierge_rate_limit_events_total",
    "Distributed rate-limit decisions and dependency errors.",
    ("scope", "result"),
    registry=REGISTRY,
)
REDIS_ERRORS = Counter(
    "concierge_redis_errors_total",
    "Redis command failures observed by this API replica.",
    registry=REGISTRY,
)
DATABASE_ERRORS = Counter(
    "concierge_database_errors_total",
    "Database errors observed by this API replica.",
    ("operation",),
    registry=REGISTRY,
)
DATABASE_POOL_CHECKED_OUT = Gauge(
    "concierge_database_pool_checked_out_connections",
    "PostgreSQL connections currently checked out by this API replica.",
    registry=REGISTRY,
)
DATABASE_POOL_CAPACITY = Gauge(
    "concierge_database_pool_capacity_connections",
    "Maximum PostgreSQL connections this API replica can acquire.",
    registry=REGISTRY,
)
DATABASE_POOL_OVERFLOW = Gauge(
    "concierge_database_pool_overflow_connections",
    "PostgreSQL pool connections currently above the base pool size.",
    registry=REGISTRY,
)
AI_PROVIDER_REQUESTS = Counter(
    "concierge_ai_provider_requests_total",
    "Provider generation outcomes observed by this API replica.",
    ("provider", "outcome"),
    registry=REGISTRY,
)
AI_PROVIDER_DURATION = Histogram(
    "concierge_ai_provider_request_duration_seconds",
    "Provider generation latency in seconds.",
    ("provider", "outcome"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 45, 90),
    registry=REGISTRY,
)
AI_PROVIDER_QUEUE_DEPTH = Gauge(
    "concierge_ai_provider_queue_depth",
    "Provider requests waiting for a local or distributed concurrency slot.",
    ("provider",),
    registry=REGISTRY,
)
SERVICE_REQUESTS = Counter(
    "concierge_service_requests_total",
    "Guest service requests created or replayed idempotently.",
    ("result",),
    registry=REGISTRY,
)
WORKER_FAILURES = Counter(
    "concierge_worker_failures_total",
    "Background worker failures.",
    ("worker",),
    registry=REGISTRY,
)

_active_lock = threading.Lock()
_active_count = 0


def route_template(request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def observe_http_request(method: str, route: str, status_code: int, duration_seconds: float) -> None:
    bounded_route = route if route and len(route) <= 200 else "unmatched"
    status_class = f"{max(1, min(5, status_code // 100))}xx"
    HTTP_REQUESTS.labels(method[:12].upper(), bounded_route, status_class).inc()
    if status_code >= 400:
        HTTP_ERRORS.labels(method[:12].upper(), bounded_route, status_class).inc()
    HTTP_REQUEST_DURATION.labels(method[:12].upper(), bounded_route).observe(max(0.0, duration_seconds))


def request_started() -> None:
    global _active_count
    with _active_lock:
        _active_count += 1
        active = _active_count
    ACTIVE_REQUESTS.inc()
    REQUEST_QUEUE_DEPTH.set(max(0, active - 1))


def request_finished() -> None:
    global _active_count
    with _active_lock:
        _active_count = max(0, _active_count - 1)
        active = _active_count
    ACTIVE_REQUESTS.dec()
    REQUEST_QUEUE_DEPTH.set(max(0, active - 1))


def render_metrics() -> bytes:
    return generate_latest(REGISTRY)
