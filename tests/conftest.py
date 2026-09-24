import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ALLOW_BODY_PROPERTY_SELECTION", "true")

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.main import app


@pytest.fixture
def admin_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth_store = AdminAuthStore(tmp_path / "suite-admin-auth.db")
    auth_store.ensure_bootstrap_admin("admin", "ChangeMe123!", "Test Administrator")
    monkeypatch.setattr(main_module, "admin_auth", auth_store)
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/auth/login",
            json={"username": "admin", "password": "ChangeMe123!", "remember_me": False},
        )
        assert response.status_code == 200, response.text
        client.headers.update({"X-CSRF-Token": response.json()["user"]["csrf_token"]})
        yield client
