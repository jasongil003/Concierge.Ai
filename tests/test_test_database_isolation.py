import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

import pytest

from app.config import Settings, validate_production_settings


ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_DB = ROOT / "state" / "concierge.db"


def _db_signature(path: Path) -> tuple[int, int, str] | None:
    try:
        metadata = path.stat()
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None
    return metadata.st_size, metadata.st_mtime_ns, checksum


def _safe_subprocess_environment(state_directory: Path | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENVIRONMENT": "test",
            "CONCIERGE_TESTING": "1",
            "ADMIN_BOOTSTRAP_PASSWORD": "TestOnly-Admin-123!",
            "CREDENTIAL_ENCRYPTION_SECRET": "TestOnly-Encryption-Secret-1234567890",
            "ANTLABS_MODE": "mock",
            "DATABASE_URL": "",
            "REDIS_URL": "",
        }
    )
    if state_directory is None:
        for variable in ("DB_PATH", "STATE_DIRECTORY", "UPLOAD_ROOT"):
            environment.pop(variable, None)
    else:
        environment["STATE_DIRECTORY"] = str(state_directory)
        environment["DB_PATH"] = str(state_directory / "concierge.db")
        environment["UPLOAD_ROOT"] = str(state_directory / "uploads")
    return environment


def test_test_profile_rejects_default_repository_database_before_app_import():
    before = _db_signature(PERSISTENT_DB)
    environment = _safe_subprocess_environment()
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Test mode requires explicit DB_PATH" in result.stderr
    assert _db_signature(PERSISTENT_DB) == before


def test_test_profile_allows_an_isolated_temporary_database(tmp_path: Path):
    state_directory = tmp_path / "test-state"
    result = subprocess.run(
        [sys.executable, "-c", "import app.main; print(app.main.settings.db_path)"],
        cwd=ROOT,
        env=_safe_subprocess_environment(state_directory),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("test-state/concierge.db")
    assert (state_directory / "concierge.db").is_file()


def test_test_profile_accepts_a_temporary_path_and_rejects_production_name(tmp_path: Path):
    temporary_settings = Settings(
        app_environment="test",
        db_path=tmp_path / "state" / "concierge.db",
        state_directory=tmp_path / "state",
        upload_root=tmp_path / "state" / "uploads",
        credential_encryption_secret="x" * 32,
    )
    validate_production_settings(temporary_settings, check_filesystem=False)

    production_looking_settings = Settings(
        app_environment="test",
        db_path=tmp_path / "production-state" / "production.db",
        state_directory=tmp_path / "production-state",
        upload_root=tmp_path / "production-state" / "uploads",
        credential_encryption_secret="x" * 32,
    )
    with pytest.raises(RuntimeError, match="production-looking"):
        validate_production_settings(production_looking_settings, check_filesystem=False)


def test_test_profile_requires_explicit_per_process_state_and_upload_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("STATE_DIRECTORY", raising=False)
    monkeypatch.delenv("UPLOAD_ROOT", raising=False)
    incomplete = Settings(
        app_environment="test",
        db_path=tmp_path / "concierge.db",
        state_directory=Path(""),
        upload_root=Path(""),
        credential_encryption_secret="x" * 32,
    )
    with pytest.raises(RuntimeError, match="explicit DB_PATH, STATE_DIRECTORY, and UPLOAD_ROOT"):
        validate_production_settings(incomplete, check_filesystem=False)


def test_development_may_keep_the_documented_repository_database(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONCIERGE_TESTING", raising=False)
    development = Settings(
        app_environment="development",
        db_path=Path("state/concierge.db"),
        credential_encryption_secret="x" * 32,
    )
    validate_production_settings(development, check_filesystem=False)


def test_production_configuration_path_validation_is_unchanged(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CONCIERGE_TESTING", raising=False)
    production = Settings(
        app_environment="production",
        db_path=Path("/var/lib/concierge/state/concierge.db"),
        state_directory=Path("/var/lib/concierge/state"),
        upload_root=Path("/var/lib/concierge/state/uploads"),
        admin_bootstrap_username="hotel-admin",
        admin_bootstrap_password="ProductionOnly-Admin-123!",
        credential_encryption_secret="p" * 48,
        admin_cookie_secure=True,
        antlabs_mode="browser_handoff",
        antlabs_auth_url="https://gateway.example.test/login/main.ant?c=proc",
        allow_body_property_selection=False,
        allow_demo_settings=False,
        canonical_hosts=("concierge.example.test",),
        admin_allowed_cidrs=("198.51.100.14/32",),
        public_base_url="https://concierge.example.test",
        forwarded_allow_ips="172.29.0.2",
        metrics_token="m" * 40,
    )
    validate_production_settings(production, check_filesystem=False)


def test_parallel_pytest_processes_get_distinct_state_and_database_paths():
    bootstrap = """
import os, tempfile
from pathlib import Path
root = Path(tempfile.mkdtemp(prefix=f\"concierge-pytest-{os.getpid()}-\")).resolve()
os.environ.update({
    \"APP_ENVIRONMENT\": \"test\",
    \"CONCIERGE_TESTING\": \"1\",
    \"STATE_DIRECTORY\": str(root),
    \"DB_PATH\": str(root / \"concierge.db\"),
    \"UPLOAD_ROOT\": str(root / \"uploads\"),
    \"ADMIN_BOOTSTRAP_PASSWORD\": \"WorkerOnly-Admin-123!\",
    \"CREDENTIAL_ENCRYPTION_SECRET\": \"WorkerOnly-Encryption-Secret-1234567890\",
    \"DATABASE_URL\": \"\",
    \"REDIS_URL\": \"\",
})
import app.main
print(app.main.settings.db_path)
"""
    environments = [_safe_subprocess_environment(), _safe_subprocess_environment()]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda env: subprocess.run(
                    [sys.executable, "-c", bootstrap],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                ),
                environments,
            )
        )

    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    database_paths = [Path(result.stdout.strip()).resolve() for result in results]
    assert database_paths[0] != database_paths[1]
    assert all(path.is_file() for path in database_paths)
