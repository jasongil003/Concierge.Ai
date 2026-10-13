"""Legacy knowledge writes must respect the separate publication permission."""

import asyncio
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.main import app
from app.operations import OperationsStore
from app.properties import PropertyRecord, PropertyStore


@pytest.fixture
def legacy_knowledge(tmp_path: Path, monkeypatch):
    database = tmp_path / "legacy-knowledge.db"
    properties = PropertyStore(database)
    for property_id in ("hotel-a", "hotel-b"):
        properties.upsert(PropertyRecord(property_id=property_id, hotel_name=property_id))
    auth = AdminAuthStore(database)
    auth.ensure_bootstrap_admin("root", "KnowledgeRoot123!")
    _, root = auth.login("root", "KnowledgeRoot123!", "127.0.0.1", "pytest")
    for username, permissions in (("editor", ["knowledge.edit", "knowledge.view"]), ("publisher", ["knowledge.edit", "knowledge.publish", "knowledge.view"])):
        role = auth.save_role({"name": username, "property_id": "hotel-a", "permissions": permissions}, root)
        auth.create_user({"username": username, "display_name": username, "password": "KnowledgeUser123!", "role_id": role["role_id"], "property_id": "hotel-a"}, root)
    operations = OperationsStore(database)
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "operations", operations)
    monkeypatch.setitem(main_module.configuration_action_services, "operations", operations)
    return operations


def _login(client, username):
    response = client.post("/api/admin/auth/login", json={"username": username, "password": "KnowledgeUser123!"})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["user"]["csrf_token"]


@pytest.mark.parametrize("kind", ["faq", "entry"])
def test_legacy_editor_cannot_create_guest_visible_content_with_explicit_or_default_enable(legacy_knowledge, kind):
    payload = {"kind": kind, "title": "Pool", "body": "Pool closes at ten", "question": "Pool closing?", "answer": "Pool closes at ten"}
    with TestClient(app) as client:
        _login(client, "editor")
        for updates in ({}, {"enabled": True}):
            response = client.put("/api/admin/properties/hotel-a/knowledge", json={**payload, **updates})
            assert response.status_code == 403, response.text
            assert response.json()["detail"] == "Permission required: knowledge.publish"
            assert legacy_knowledge.list_knowledge("hotel-a") == []
            assert legacy_knowledge.search_knowledge("hotel-a", "pool") == []


def test_legacy_draft_editing_and_publisher_transitions_preserve_approval_boundary(legacy_knowledge):
    payload = {"kind": "faq", "question": "Pool closing?", "answer": "Approved pool hours", "enabled": False}
    with TestClient(app) as editor:
        _login(editor, "editor")
        draft = editor.put("/api/admin/properties/hotel-a/knowledge", json=payload)
        assert draft.status_code == 200, draft.text
        item_id = draft.json()["item_id"]
        assert draft.json()["enabled"] is False
        edited_payload = {**payload, "item_id": item_id, "answer": "Draft pool hours"}
        edited = editor.put("/api/admin/properties/hotel-a/knowledge", json=edited_payload)
        assert edited.status_code == 200, edited.text
        assert legacy_knowledge.search_knowledge("hotel-a", "pool") == []
        assert editor.put("/api/admin/properties/hotel-a/knowledge", json={**edited_payload, "enabled": True}).status_code == 403
        assert editor.put("/api/admin/properties/hotel-b/knowledge", json=edited_payload).status_code == 403

        with TestClient(app) as publisher:
            _login(publisher, "publisher")
            published = publisher.put("/api/admin/properties/hotel-a/knowledge", json={**edited_payload, "answer": "Verified pool hours", "enabled": True})
            assert published.status_code == 200, published.text
            before = legacy_knowledge.list_knowledge("hotel-a")[0]
            assert legacy_knowledge.search_knowledge("hotel-a", "pool")[0]["answer"] == "Verified pool hours"
            for enabled in (True, False):
                denied = editor.put("/api/admin/properties/hotel-a/knowledge", json={**edited_payload, "answer": "Unauthorized pool hours", "enabled": enabled})
                assert denied.status_code == 403, denied.text
                assert legacy_knowledge.list_knowledge("hotel-a")[0] == before
                assert legacy_knowledge.search_knowledge("hotel-a", "pool")[0]["answer"] == "Verified pool hours"
            updated = publisher.put("/api/admin/properties/hotel-a/knowledge", json={**edited_payload, "answer": "Updated verified pool hours", "enabled": True})
            assert updated.status_code == 200, updated.text
            unpublished = publisher.put("/api/admin/properties/hotel-a/knowledge", json=edited_payload)
            assert unpublished.status_code == 200, unpublished.text
            assert legacy_knowledge.search_knowledge("hotel-a", "pool") == []
        assert editor.put("/api/admin/properties/hotel-a/knowledge", json=edited_payload).status_code == 200


def test_concurrent_publication_prevents_stale_draft_editor_overwrite(legacy_knowledge, monkeypatch):
    payload = {"kind": "faq", "question": "Pool closing?", "answer": "Draft hours", "enabled": False}
    draft = legacy_knowledge.save_knowledge("hotel-a", payload)
    original_connect = legacy_knowledge._connect
    published = False

    class ConnectionProxy:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, parameters=()):
            nonlocal published
            result = self.connection.execute(sql, parameters)
            if sql.startswith("SELECT item_id FROM knowledge_items") and not published:
                # Complete/release the original read before the publisher
                # commits; return the stale lookup to the waiting editor.
                stale_row = result.fetchone()
                result.close()
                published = True
                with original_connect() as publisher:
                    publisher.execute("UPDATE knowledge_items SET enabled=1,answer=? WHERE item_id=?", ("Concurrent verified hours", draft["item_id"]))
                class StaleCursor:
                    def fetchone(self):
                        return stale_row
                return StaleCursor()
            return result

    @contextmanager
    def racing_connection():
        with original_connect() as connection:
            yield ConnectionProxy(connection)

    monkeypatch.setattr(legacy_knowledge, "_connect", racing_connection)
    with pytest.raises(PermissionError, match="knowledge.publish"):
        legacy_knowledge.save_knowledge("hotel-a", {**payload, "item_id": draft["item_id"], "answer": "Unauthorized stale draft"}, draft["item_id"], allow_publish=False)
    stored = legacy_knowledge.list_knowledge("hotel-a")[0]
    assert stored["enabled"] is True
    assert stored["answer"] == "Concurrent verified hours"


def test_admin_faq_action_propagates_publication_permission_and_stays_draft(legacy_knowledge, monkeypatch):
    from app.configuration_actions import ActionContext

    _, principal = main_module.admin_auth.login("editor", "KnowledgeUser123!", "127.0.0.1", "pytest")
    context = ActionContext(principal, "hotel-a", None, "conversation", "request", main_module.configuration_action_services)
    captured = []
    original_save = legacy_knowledge.save_knowledge

    def capture_save(*args, **kwargs):
        captured.append(kwargs.get("allow_publish"))
        return original_save(*args, **kwargs)

    monkeypatch.setattr(legacy_knowledge, "save_knowledge", capture_save)
    registry = main_module.configuration_action_registry
    action, parameters, _ = registry.prepare("faq.create", {"question": "Pool closing?", "answer": "Draft pool hours"}, context)
    saved = asyncio.run(registry.execute(action, context, parameters))
    assert captured == [False]
    assert saved["enabled"] is False
    assert legacy_knowledge.search_knowledge("hotel-a", "pool") == []
