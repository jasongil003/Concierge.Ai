from pathlib import Path

import pytest

import app.main as main_module
from app.guest_identity import GuestIdentityStore
from app.hospitality import HospitalityStore
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


def test_guest_360_sanitizes_context_and_link_actions_preserve_related_records(
    admin_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    database = tmp_path / "guest-360.db"
    sessions = SessionStore(database)
    identities = GuestIdentityStore(database)
    hotel = HospitalityStore(database)
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "guest_identities", identities)
    monkeypatch.setattr(main_module, "hospitality", hotel)

    concierge = sessions.create("test-property", "guest-client")
    sessions.issue_guest_credentials(concierge.session_id, ttl_seconds=600)
    sessions.record_message(concierge.session_id, "test-property", "guest", "PRIVATE_GUEST_MESSAGE")
    device_id = identities.observe_device("test-property", "02:00:00:11:22:33")
    stay = identities.reconnect_or_create_stay(
        "test-property", device_id, concierge_session_id=concierge.session_id,
        antlabs_session_id="PRIVATE_GATEWAY_ID", browser_session_id="PRIVATE_BROWSER_ID",
        room="1204", pms_guest_id="PRIVATE_PMS_ID",
    )
    identities.update_memory(
        "test-property", stay["stay_id"], {"conversation_summary": "PRIVATE_STAFF_NOTE"}
    )
    hotel.create_service_request("test-property", {
        "stay_id": stay["stay_id"], "room": "1204", "request_type": "Housekeeping",
        "description": "Fresh towels", "priority": "normal", "department": "Housekeeping",
        "notes": ["PRIVATE_INTERNAL_REQUEST_NOTE"],
    })

    response = admin_client.get(
        f"/api/admin/properties/test-property/stays/{stay['stay_id']}/guest-360"
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["stay"]["memory_summary"]["conversation_summary"] == "PRIVATE_STAFF_NOTE"
    assert payload["stay"]["device_id"].startswith("Device · ••••")
    assert "02:00:00:11:22:33" not in response.text
    assert payload["requests"][0]["description"] == "Fresh towels"
    assert "notes" not in payload["requests"][0]
    assert "PRIVATE_INTERNAL_REQUEST_NOTE" not in response.text
    assert "PRIVATE_GUEST_MESSAGE" not in response.text
    assert payload["conversations"][0]["message_count"] == 1

    auth = main_module.admin_auth
    _, root = auth.login("admin", "ChangeMe123!", "127.0.0.1", "guest-360-test")
    role = auth.save_role({
        "name": "Guest Records Reviewer",
        "property_id": "test-property",
        "permissions": ["properties.view", "guest_sessions.view", "requests.view", "conversations.view"],
    }, root)
    auth.create_user({
        "username": "stay.reviewer", "display_name": "Stay Reviewer", "password": "StayReviewer-123!",
        "role_id": role["role_id"], "property_id": "test-property", "status": "active",
    }, root)
    from fastapi.testclient import TestClient
    with TestClient(main_module.app) as reviewer:
        login = reviewer.post("/api/admin/auth/login", json={"username": "stay.reviewer", "password": "StayReviewer-123!"})
        assert login.status_code == 200, login.text
        reviewer.headers["X-CSRF-Token"] = login.json()["user"]["csrf_token"]
        restricted = reviewer.get(
            f"/api/admin/properties/test-property/stays/{stay['stay_id']}/guest-360"
        )
        assert restricted.status_code == 200, restricted.text
        assert restricted.json()["visibility"]["staff_notes"] is False
        assert "memory_summary" not in restricted.json()["stay"]
        assert "PRIVATE_STAFF_NOTE" not in restricted.text
        assert "PRIVATE_GATEWAY_ID" not in restricted.text
        assert "PRIVATE_BROWSER_ID" not in restricted.text
        assert "PRIVATE_PMS_ID" not in restricted.text
        assert restricted.json()["conversations"][0]["message_count"] == 1
        records = reviewer.get("/api/admin/properties/test-property/sessions")
        assert records.status_code == 200, records.text
        assert "memory_summary" not in records.json()["stays"][0]
        assert "02:00:00:11:22:33" not in records.text
        assert records.json()["sessions"][0]["session_id"].startswith("Concierge session · ••••")
        assert "action_id" not in records.json()["sessions"][0]
        assert "action_id" not in records.json()["guest_sessions"][0]
        assert reviewer.post(
            f"/api/admin/properties/test-property/guest-sessions/{stay['guest_session_id']}/unlink"
        ).status_code == 403
        assert reviewer.post(
            f"/api/admin/properties/test-property/sessions/{concierge.session_id}/expire"
        ).status_code == 403
        assert sessions.peek(concierge.session_id).guest_token_hash is not None
        assert identities.guest_sessions_for_stay("test-property", stay["stay_id"])

    other_device = identities.observe_device("other-property", "02:00:00:44:55:66")
    other_stay = identities.reconnect_or_create_stay("other-property", other_device, room="2099")
    other_link_id = other_stay["guest_session_id"]
    assert admin_client.post(
        f"/api/admin/properties/test-property/guest-sessions/{other_link_id}/unlink"
    ).status_code == 404
    assert identities.guest_sessions_for_stay("other-property", other_stay["stay_id"])
    assert admin_client.get(
        f"/api/admin/properties/test-property/stays/{other_stay['stay_id']}/guest-360"
    ).status_code == 404

    cross_property_session = sessions.create("other-property", "other-client")
    sessions.issue_guest_credentials(cross_property_session.session_id, ttl_seconds=600)
    before_stays = len(identities.list_stays("test-property"))
    rejected = admin_client.post(
        "/api/admin/properties/test-property/sessions/reconnect",
        json={"raw_mac": "02:00:00:aa:bb:cc", "concierge_session_id": cross_property_session.session_id},
    )
    assert rejected.status_code == 404
    assert len(identities.list_stays("test-property")) == before_stays
    assert admin_client.post(
        f"/api/admin/properties/test-property/sessions/{cross_property_session.session_id}/expire"
    ).status_code == 404
    assert sessions.peek(cross_property_session.session_id).guest_token_hash is not None

    conflict = admin_client.post(
        "/api/admin/properties/test-property/sessions/reconnect",
        json={"raw_mac": "02:00:00:aa:bb:dd", "concierge_session_id": concierge.session_id},
    )
    assert conflict.status_code == 409
    assert len(identities.list_stays("test-property")) == before_stays

    guest_link_id = stay["guest_session_id"]
    unlinked = admin_client.post(
        f"/api/admin/properties/test-property/guest-sessions/{guest_link_id}/unlink"
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json() == {"unlinked": True, "stay_id": stay["stay_id"]}
    assert identities.get_stay("test-property", stay["stay_id"])["status"] == "active"
    assert sessions.peek(concierge.session_id) is not None
    assert identities.guest_sessions_for_stay("test-property", stay["stay_id"]) == []

    expired = admin_client.post(
        f"/api/admin/properties/test-property/sessions/{concierge.session_id}/expire"
    )
    assert expired.status_code == 200, expired.text
    assert sessions.peek(concierge.session_id).guest_token_hash is None
