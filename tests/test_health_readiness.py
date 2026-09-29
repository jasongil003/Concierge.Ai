from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_liveness_and_readiness_are_separate_and_do_not_expose_secrets():
    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ok"
    assert {"configuration", "database", "redis", "storage"} <= set(body["checks"])
    assert body["checks"]["configuration"] == "healthy"
    serialized = ready.text.casefold()
    assert all(term not in serialized for term in ("password", "secret", "api_key", "postgresql://", "redis://"))


def test_readiness_reports_database_failure_without_sensitive_details(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def unavailable():
        raise RuntimeError("Sensitive connection detail must not escape readiness.")

    monkeypatch.setattr(main_module, "settings", SimpleNamespace(database_url="postgresql+psycopg://private", upload_root=tmp_path))
    monkeypatch.setattr(main_module, "database_ready", unavailable)

    with pytest.raises(HTTPException) as captured:
        asyncio.run(main_module.health_ready())

    assert captured.value.status_code == 503
    assert captured.value.detail == "Database is not ready."
