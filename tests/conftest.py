import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["ALLOW_BODY_PROPERTY_SELECTION"] = "true"
os.environ["PROPERTY_ID"] = "test-property"
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "PytestOnly-Admin-123!")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_SECRET", "PytestOnly-Encryption-Secret-1234567890")

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.guardrails import RateLimiter
from app.main import app
from app.properties import PropertyRecord, PropertyStore


@pytest.fixture(autouse=True)
def isolate_api_rate_limiter(monkeypatch: pytest.MonkeyPatch):
    """Keep API tests independent of persistent local rate-limit state."""
    monkeypatch.setattr(main_module, "rate_limiter", RateLimiter())


@pytest.fixture(scope="session", autouse=True)
def configured_test_property(tmp_path_factory, request):
    previous = main_module.properties
    store = PropertyStore(tmp_path_factory.mktemp("properties") / "properties.db")
    store.upsert(PropertyRecord(property_id="test-property", hotel_name="Test Property"))
    main_module.properties = store
    request.addfinalizer(lambda: setattr(main_module, "properties", previous))
    return store


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
