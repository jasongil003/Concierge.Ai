from pathlib import Path

import pytest

import app.main as main_module
from app.guest_identity import GuestIdentityStore
from app.knowledge_management import KnowledgeStore
from app.operations import OperationsStore
from app.session_store import SessionStore


def test_admin_guest_records_are_server_filtered_paged_and_property_scoped(
    admin_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    database = tmp_path / "admin-session-pages.db"
    sessions = SessionStore(database)
    identities = GuestIdentityStore(database)
    operations = OperationsStore(database)
    knowledge_sources = KnowledgeStore(database, tmp_path / "uploads")
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "guest_identities", identities)
    monkeypatch.setattr(main_module, "operations", operations)
    monkeypatch.setattr(main_module, "knowledge_management", knowledge_sources)

    active_session = sessions.create("test-property", "guest-session")
    sessions.issue_guest_credentials(active_session.session_id, ttl_seconds=600)
    sessions.create("other-property", "other-guest")
    for index in range(27):
        mac = f"02:00:00:01:{index // 256:02x}:{index % 256:02x}"
        device_id = identities.observe_device("test-property", mac)
        identities.reconnect_or_create_stay(
            "test-property", device_id, room=f"Paging Room {index:02d}", pms_guest_id=f"paging-pms-{index:02d}"
        )
    other_device = identities.observe_device("other-property", "02:00:00:02:00:01")
    identities.reconnect_or_create_stay("other-property", other_device, room="Paging Room other")
    for index in range(27):
        operations.save_knowledge(
            "test-property", {"kind": "entry", "title": f"Paged entry {index:02d}", "body": f"Entry details {index}", "enabled": False}
        )
        operations.save_knowledge(
            "test-property", {"kind": "faq", "question": f"Paged question {index:02d}", "answer": f"Answer {index}", "enabled": False}
        )
        knowledge_sources.upload(
            "test-property", f"paged-source-{index:02d}.txt", "text/plain", f"Source text {index}".encode(), "pagination-test"
        )

    first = admin_client.get(
        "/api/admin/properties/test-property/sessions",
        params={"limit": 10, "q": "Paging Room", "filter": "all"},
    )
    assert first.status_code == 200, first.text
    data = first.json()
    assert len(data["stays"]) == 10
    assert len(data["guest_sessions"]) == 10
    assert data["pages"]["stays"] == {"total": 27, "limit": 10, "offset": 0}
    assert data["pages"]["guest_sessions"] == {"total": 27, "limit": 10, "offset": 0}
    assert data["pages"]["sessions"]["total"] == 0
    assert data["pages"]["devices"]["total"] == 0
    assert data["result_count"] == 54
    assert all("other" not in str(record).lower() for record in data["stays"] + data["guest_sessions"])
    assert data["counts"]["total_records"] == 82

    later = admin_client.get(
        "/api/admin/properties/test-property/sessions",
        params={"limit": 10, "q": "Paging Room", "filter": "all", "stay_offset": 20, "link_offset": 10},
    )
    assert later.status_code == 200, later.text
    later_data = later.json()
    assert len(later_data["stays"]) == 7
    assert len(later_data["guest_sessions"]) == 10
    assert later_data["pages"]["stays"]["offset"] == 20
    assert later_data["pages"]["guest_sessions"]["offset"] == 10

    active = admin_client.get(
        "/api/admin/properties/test-property/sessions",
        params={"limit": 10, "filter": "active-sessions"},
    )
    assert active.status_code == 200, active.text
    active_data = active.json()
    assert len(active_data["sessions"]) == 1
    assert active_data["sessions"][0]["session_status"] == "active"
    assert active_data["pages"]["sessions"]["total"] == 1
    assert active_data["pages"]["stays"]["total"] == 0
    assert active_data["counts"]["sessions"] == 1
    assert active_data["counts"]["active_sessions"] == 1

    knowledge = admin_client.get(
        "/api/admin/properties/test-property/knowledge",
        params={"limit": 10},
    )
    assert knowledge.status_code == 200, knowledge.text
    knowledge_data = knowledge.json()
    assert len(knowledge_data["items"]) == 10
    assert len(knowledge_data["faqs"]) == 10
    assert knowledge_data["pages"]["items"] == {"total": 27, "limit": 10, "offset": 0}
    assert knowledge_data["pages"]["faqs"] == {"total": 27, "limit": 10, "offset": 0}
    knowledge_later = admin_client.get(
        "/api/admin/properties/test-property/knowledge",
        params={"limit": 10, "entry_offset": 20, "faq_offset": 20},
    )
    assert knowledge_later.status_code == 200, knowledge_later.text
    assert len(knowledge_later.json()["items"]) == 7
    assert len(knowledge_later.json()["faqs"]) == 7

    sources = admin_client.get(
        "/api/admin/properties/test-property/knowledge/managed",
        params={"source_limit": 10},
    )
    assert sources.status_code == 200, sources.text
    assert len(sources.json()["sources"]) == 10
    assert sources.json()["source_pages"] == {"total": 27, "limit": 10, "offset": 0}
    sources_later = admin_client.get(
        "/api/admin/properties/test-property/knowledge/managed",
        params={"source_limit": 10, "source_offset": 20},
    )
    assert sources_later.status_code == 200, sources_later.text
    assert len(sources_later.json()["sources"]) == 7

    assert admin_client.get(
        "/api/admin/properties/test-property/sessions", params={"limit": 101}
    ).status_code == 422
    assert admin_client.get(
        "/api/admin/properties/test-property/sessions", params={"stay_offset": 1_000_001}
    ).status_code == 422
