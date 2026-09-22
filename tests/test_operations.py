import base64
from pathlib import Path

import pytest

from app.admin_auth import AdminAuthStore, AuthenticationError
from app.operations import OperationsStore


def test_knowledge_crud_search_and_property_isolation(tmp_path: Path):
    store = OperationsStore(tmp_path / "operations.db")
    item = store.save_knowledge(
        "hotel-a",
        {"kind": "entry", "title": "Rooftop pool", "body": "The rooftop pool closes at 10 PM."},
    )

    assert store.list_knowledge("hotel-b") == []
    assert store.search_knowledge("hotel-a", "When does the pool close?")[0]["title"] == "Rooftop pool"
    assert store.search_knowledge("hotel-a", "I am bored. What can I do inside the hotel?") == []
    assert store.delete_knowledge("hotel-b", item["item_id"]) is False
    assert store.delete_knowledge("hotel-a", item["item_id"]) is True


def test_document_ingestion_reports_unsupported_types_truthfully(tmp_path: Path):
    store = OperationsStore(tmp_path / "operations.db")
    ready = store.upload_document(
        "hotel-a", "guide.txt", "text/plain", base64.b64encode(b"Breakfast starts at 6 AM").decode()
    )
    unsupported = store.upload_document(
        "hotel-a", "guide.pdf", "application/pdf", base64.b64encode(b"not-a-real-pdf").decode()
    )

    assert ready["status"] == "ready"
    assert unsupported["status"] == "error"
    assert unsupported["enabled"] is False
    assert "extractor" in unsupported["error"]


def test_webhook_secret_is_encrypted_masked_and_property_scoped(tmp_path: Path):
    store = OperationsStore(tmp_path / "operations.db")
    webhook = store.save_webhook(
        "hotel-a",
        {
            "name": "Operations",
            "endpoint_url": "https://example.com/hooks/concierge",
            "events": ["guest.request.created"],
            "secret": "super-secret-signing-key",
        },
    )

    assert webhook["secret_configured"] is True
    assert "secret" not in webhook
    assert store.get_webhook("hotel-b", webhook["webhook_id"], include_secret=True) is None
    assert store.get_webhook("hotel-a", webhook["webhook_id"], include_secret=True)["secret"] == "super-secret-signing-key"


def test_smtp_password_is_preserved_and_never_returned_in_plaintext(tmp_path: Path):
    store = OperationsStore(tmp_path / "operations.db")
    public = store.save_email_settings(
        {
            "host": "smtp.example.com",
            "port": 587,
            "username": "mailer",
            "from_address": "concierge@example.com",
            "security": "starttls",
            "enabled": True,
            "password": "smtp-password",
        }
    )
    updated = store.save_email_settings(
        {
            "host": "smtp2.example.com",
            "port": 587,
            "username": "mailer",
            "from_address": "concierge@example.com",
            "security": "starttls",
            "enabled": True,
            "password": "",
        }
    )

    assert public["password_configured"] is True
    assert "password" not in public
    assert updated["password_masked"] != "smtp-password"
    assert store.get_email_settings(include_secret=True)["password"] == "smtp-password"


def test_password_reset_token_is_single_use_and_revokes_old_password(tmp_path: Path):
    store = AdminAuthStore(tmp_path / "auth.db")
    store.ensure_bootstrap_admin("admin", "ChangeMe123!", "Administrator")
    _, actor = store.login("admin", "ChangeMe123!", "127.0.0.1", "pytest")
    user = store.list_users(actor)[0]
    store.update_user(user["id"], {"email": "admin@example.com"}, actor)
    reset = store.create_password_reset("admin")
    assert reset is not None

    store.consume_password_reset(reset["token"], "A-New-Password-123!")
    with pytest.raises(AuthenticationError, match="invalid or has expired"):
        store.consume_password_reset(reset["token"], "Another-Password-123!")

    with pytest.raises(AuthenticationError):
        store.login("admin", "ChangeMe123!", "127.0.0.1", "pytest")
    assert store.login("admin", "A-New-Password-123!", "127.0.0.1", "pytest") is not None
