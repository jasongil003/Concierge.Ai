from __future__ import annotations

import asyncio
import json
import io
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.error
import zipfile

import pytest

from app import build_info, database
from app.backup import create_backup, verify_backup
from app.properties import PropertyRecord, PropertyStore
from deploy.common import deployment_manifest, diagnostics, operation_lock, preflight, update_decision
from deploy import source_service


ROOT = Path(__file__).resolve().parents[1]


def test_version_endpoint_reports_only_safe_build_identity(monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient
    from app.main import app
    import app.main as main_module

    monkeypatch.setenv("CONCIERGE_VERSION", "0.9.2")
    monkeypatch.setenv("CONCIERGE_COMMIT", "a1b2c3d4")
    monkeypatch.setenv("CONCIERGE_BUILD_DATE", "2026-10-06T01:02:03Z")
    monkeypatch.setenv("CONCIERGE_DEPLOYMENT_MODE", "docker-dev")
    monkeypatch.setenv("APP_ENVIRONMENT", "development")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_SECRET", "private-build-secret")
    monkeypatch.setenv("METRICS_TOKEN", "private-metrics-token")
    monkeypatch.setattr(main_module, "BUILD_IDENTITY", {
        "version": "0.9.2", "commit": "a1b2c3d4", "build_date": "2026-10-06T01:02:03Z",
        "deployment_mode": "docker-dev", "profile": "development", "runtime": "python",
        "python_version": sys.version.split()[0],
    })

    with TestClient(app) as client:
        response = client.get("/health/version")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.9.2"}
    assert set(response.json()) == {"status", "version"}
    assert "private-build-secret" not in response.text
    assert "private-metrics-token" not in response.text


def test_build_identity_rejects_untrusted_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_VERSION", "version\nCREDENTIAL=leak")
    monkeypatch.setenv("CONCIERGE_COMMIT", "postgresql://user:password@host")
    monkeypatch.setenv("CONCIERGE_BUILD_DATE", "password=do-not-print")
    monkeypatch.setattr(build_info, "_git_value", lambda *_args: None)
    monkeypatch.setattr(build_info, "_git_timestamp", lambda: None)

    identity = build_info.build_identity()

    assert identity["version"] == "0.0.0+source"
    assert identity["commit"] == "unknown"
    assert identity["build_date"] == "unknown"
    assert "password" not in json.dumps(identity)


@pytest.mark.parametrize(
    ("filename", "value", "expected"),
    [
        ("RELEASE_BUILD_DATE", "2026-10-06T03:15:32Z", "2026-10-06T03:15:32Z"),
        ("RELEASE_BUILD_DATE", "2026-02-30T03:15:32Z", None),
        ("RELEASE_BUILD_DATE", "a1b2c3d4", None),
        ("RELEASE_COMMIT", "2026-10-06T03:15:32Z", None),
        ("RELEASE_VERSION", "2026-10-06T03:15:32Z", None),
    ],
)
def test_release_file_uses_field_specific_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filename, value, expected):
    app_dir = tmp_path / "release" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / filename).write_text(value, encoding="utf-8")
    monkeypatch.setattr(build_info, "__file__", str(app_dir / "build_info.py"))

    assert build_info._release_file(filename) == expected

    if filename == "RELEASE_BUILD_DATE":
        monkeypatch.setattr(build_info, "_git_timestamp", lambda: None)
        monkeypatch.delenv("CONCIERGE_BUILD_DATE", raising=False)
        identity = build_info.build_identity()
        assert identity["build_date"] == (expected or "unknown")


def test_release_file_uses_commit_validator_for_commit_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app_dir = tmp_path / "release" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "RELEASE_COMMIT").write_text("a1b2c3d4", encoding="utf-8")
    monkeypatch.setattr(build_info, "__file__", str(app_dir / "build_info.py"))
    assert build_info._release_file("RELEASE_COMMIT") == "a1b2c3d4"


def test_guest_chat_rate_li