from dataclasses import replace
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main_module
import app.session_store as session_store_module
from app.admin_auth import AdminAuthStore
from app.config import Settings, validate_antlabs_mode, validate_production_settings
from app.guardrails import PropertyGuard
from app.hospitality import HospitalityStore
from app.main import app
from app.personalization import PersonalizationStore
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


@pytest.fixture(autouse=True)
def validate_explicit_profiles_without_pytest_runtime_marker(monkeypatch: pytest.MonkeyPatch):
    """These tests validate supplied Settings objects, not the running pytest profile."""
    monkeypatch.delenv("CONCIERGE_TESTING", raising=False)


def _production_settings(tmp_path: Path, **overrides) -> Settings:
    safe = Settings(
        app_environment="production",
        property_id="hotel-a",
        db_path=tmp_path / "concierge.db",
        admin_bootstrap_password="ProductionOnly123!",
        admin_cookie_secure=True,
        credential_encryption_secret="a" * 32,
        backup_encryption_key="b" * 64,
        antlabs_mode="browser_handoff",
        antlabs_auth_url="https://gateway.example.test/login/main.ant?c=proc",
        allow_body_property_selection=False,
        metrics_token="m" * 40,
        canonical_hosts=("concierge.example.test", "admin.example.test"),
        admin_allowed_cidrs=("198.51.100.14/32",),
        public_base_url="https://concierge.example.test",
        forwarded_allow_ips="172.29.0.2,172.29.0.1",
    )
    return replace(safe, **overrides)


def test_production_rejects_default_admin_password(tmp_path: Path):
    with pytest.raises(RuntimeError, match="ADMIN_BOOTSTRAP_PASSWORD"):
        validate_production_settings(
            _production_settings(tmp_path, admin_bootstrap_password="ChangeMe123!")
        )


def test_production_rejects_the_initial_root_admin_bootstrap_pair(tmp_path: Path):
    production = _production_settings(
        tmp_path,
        admin_bootstrap_username="root",
        admin_bootstrap_password="admin",
    )
    with pytest.raises(RuntimeError, match="default root/admin credential"):
        validate_production_settings(production)


def test_development_keeps_the_initial_root_admin_bootstrap_pair(tmp_path: Path):
    development = replace(
        _production_settings(tmp_path),
        app_environment="development",
        admin_bootstrap_password="admin",
        antlabs_mode="mock",
        admin_cookie_secure=False,
        canonical_hosts=(),
        public_base_url="",
        admin_allowed_cidrs=(),
    )
    validate_production_settings(development)


def test_production_rejects_development_deployment_mode_and_unknown_mode(tmp_path: Path):
    with pytest.raises(RuntimeError, match="docker-dev"):
        validate_production_settings(_production_settings(tmp_path, deployment_mode="docker-dev"))
    with pytest.raises(RuntimeError, match="supported deployment mode"):
        validate_production_settings(_production_settings(tmp_path, deployment_mode="mystery"))


def test_production_rejects_default_encryption_secret(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_SECRET"):
        validate_production_settings(
            _production_settings(tmp_path, credential_encryption_secret="change-me")
        )


def test_production_requires_independent_backup_encryption_key(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CONCIERGE_BACKUP_ENCRYPTION_KEY"):
        validate_production_settings(_production_settings(tmp_path, backup_encryption_key="invalid"))


def test_production_rejects_local_demo_encryption_secret_and_account_name(tmp_path: Path):
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_SECRET"):
        validate_production_settings(_production_settings(
            tmp_path,
            credential_encryption_secret="Local-D