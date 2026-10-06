import atexit
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

# Configure the isolated test profile before importing pytest plugins, app.config,
# app.main, or any database-backed service modules.
_TEST_STATE_DIRECTORY = Path(
    tempfile.mkdtemp(prefix=f"concierge-pytest-{os.getpid()}-")
).resolve()
os.environ["APP_ENVIRONMENT"] = "test"
os.environ["CONCIERGE_TESTING"] = "1"
os.environ["STATE_DIRECTORY"] = str(_TEST_STATE_DIRECTORY)
os.environ["DB_PATH"] = str(_TEST_STATE_DIRECTORY / "concierge.db")
os.environ["UPLOAD_ROOT"] = str(_TEST_STATE_DIRECTORY / "uploads")
os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = "PytestOnly-Admin-123!"
os.environ["CREDENTIAL_ENCRYPTION_SECRET"] = "PytestOnly-Encryption-Secret-1234567890"

_PERSISTENT_DATABASE = Path(__file__).resolve().parents[1] / "state" / "concierge.db"
_PERSISTENT_DATABASE_SUFFIXES = ("", "-wal", "-shm", "-journal")


def _persistent_database_snapshot() -> dict[str, tuple[int, int, str] | None]:
    snapshot: dict[str, tuple[int, int, str] | None] = {}
    for suffix in _PERSISTENT_DATABASE_SUFFIXES:
        path = Path(f"{_PERSISTENT_DATABASE}{suffix}")
        try:
            metadata = path.stat()
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            snapshot[str(path)] = None
        else:
            snapshot[str(path)] = (metadata.st_size, metadata.st_mtime_ns, checksum)
    return snapshot


_PERSISTENT_DATABASE_BEFORE = _persistent_database_snapshot()
atexit.register(shutil.rmtree, _TEST_STATE_DIRECTORY, ignore_errors=True)

import pytest
from fastapi.testclient import TestClient

os.environ["ALLOW_BODY_PROPERTY_SELECTION"] = "true"
os.environ["PROPERTY_ID"] = "test-property"

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.guardrails import RateLimiter
from app.main import app
from app.properties import PropertyRecord, PropertyStore


def pytest_report_header(config):
    db_snapshot = _PERSISTENT_DATABASE_BEFORE.get(str(_PERSISTENT_DATABASE))
    if db_snapshot is None:
        return f"Persistent SQLite safeguard: {_PERSISTENT_DATABASE} absent at test start"
    size, mtime_ns, checksum = db_snapshot
    return (
        f"Persistent SQLite safeguard: {_PERSISTENT_DATABASE} "
        f"size={size} mtime_ns={mtime_ns} sha256={checksum}"
    )


def pytest_sessionfinish(session, exitstatus):
    after = _persistent_database_snapshot()
    if after != _PERSISTENT_DATABASE_BEFORE:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_sep("!", "Persistent/default SQLite database changed during tests")
            for path in sorted(set(_PERSISTENT_DATABASE_BEFORE) | set(after)):
                before_value = _PERSISTENT_DATABASE_BEFORE.get(path)
                after_value = after.get(path)
                if before_value != after_value:
                    reporter.write_line(f"{path}: before={before_value!r} after={after_value!r}")
            reporter.write_line("The test suite did not restore or overwrite the database.")
    else:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_sep("-", "Persistent SQLite safety check: unchanged")
            for path in sorted(after):
                reporter.write_line(f"{path}: {after[path]!r}")


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
