import io
import sqlite3
import time
from zipfile import ZipFile

import pytest

from app.ai_providers import AIProviderStore
from app.hospitality import HospitalityStore
from app.observability import DiagnosticContext, DiagnosticToolRegistry, ObservabilityStore
from app.reporting import ReportService, SHEET_NAMES
from app.session_store import SessionStore


def build_store(tmp_path):
    path = tmp_path / "operations.db"
    SessionStore(path, 30)
    HospitalityStore(path)
    AIProviderStore(path)
    return path, ObservabilityStore(path)


def test_metric_history_is_property_isolated(tmp_path):
    _, store = build_store(tmp_path)
    now = int(time.time())
    store.record("hotel-a", "api_latency_ms", 20, "ms", recorded_at=now - 30)
    store.record("hotel-a", "api_latency_ms", 40, "ms", recorded_at=now)
    store.record("hotel-b", "api_latency_ms", 999, "ms", recorded_at=now)

    history = store.history("hotel-a", "api_latency_ms", "1h")

    assert history
    assert max(item["value"] for item in history) <= 40


def test_department_analytics_cannot_see_other_department(tmp_path):
    path, store = build_store(tmp_path)
    now = int(time.time())
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO departments(department_id,property_id,name,created_at,updated_at) VALUES(?,?,?,?,?)",
            ("dept-housekeeping", "hotel-a", "Housekeeping", now, now),
        )
        for request_id, department in (("req-1", "Housekeeping"), ("req-2", "Engineering")):
            db.execute(
                """INSERT INTO service_requests(request_id,property_id,request_type,description,department,status,created_at,updated_at)
                VALUES(?,?,?,?,?,'new',?,?)""",
                (request_id, "hotel-a", "amenity", "Guest request", department, now, now),
            )

    analytics = store.property_analytics("hotel-a", "24h", "dept-housekeeping")

    assert analytics["summary"]["service_requests"] == 1
    assert analytics["requests_by_department"] == [{"name": "Housekeeping", "value": 1}]
    assert {item["request_id"] for item in analytics["raw_requests"]} == {"req-1"}


def test_diagnostic_registry_checks_each_tool_permission():
    registry = DiagnosticToolRegistry()
    registry.register("database", "infrastructure.view", lambda context: {"state": "healthy"})
    denied = DiagnosticContext("hotel-a", "property-manager", None, frozenset({"assistant.use"}), "request-1")
    allowed = DiagnosticContext("hotel-a", "super-admin", None, frozenset({"infrastructure.view"}), "request-2")

    with pytest.raises(PermissionError):
        registry.run("database", denied)
    assert registry.run("database", allowed)["state"] == "healthy"


def test_alerts_are_generated_from_measurable_thresholds(tmp_path):
    _, store = build_store(tmp_path)
    dashboard = {
        "analytics": {"summary": {"overdue_requests": 3}, "ai": {"requests": 20, "errors": 4}},
        "database": {"state": "healthy", "evidence": "Probe succeeded."},
    }

    alerts = store.evaluate_alerts("hotel-a", dashboard)

    assert {item["component"] for item in alerts} == {"request_queue", "ai_providers"}
    assert all(item["evidence"] for item in alerts)


def test_reports_are_valid_and_include_required_sections(tmp_path):
    _, store = build_store(tmp_path)
    analytics = store.property_analytics("hotel-a", "24h")
    service = ReportService()

    workbook = service.workbook("Hotel A", analytics, ["Continue monitoring."])
    with ZipFile(io.BytesIO(workbook)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode()
        assert all(f'name="{name}"' in workbook_xml for name in SHEET_NAMES)
        assert len([name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]) == 8

    pdf = service.management_pdf("Hotel A", analytics, [], ["Continue monitoring."])
    assert pdf.startswith(b"%PDF-1.4")
    assert b"Hotel A Management Report" in pdf
