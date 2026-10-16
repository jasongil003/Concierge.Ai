from pathlib import Path

import app.main as main_module
from app.session_store import SessionStore


def test_conversation_inbox_pages_are_bounded_scoped_and_report_full_counts(
    tmp_path: Path, admin_client, monkeypatch
):
    sessions = SessionStore(tmp_path / "conversation-pages.db")
    monkeypatch.setattr(main_module, "store", sessions)

    waiting_ids = set()
    for index in range(105):
        session = sessions.create("test-property", f"guest-{index:03d}")
        if index < 7:
            sessions.escalate_conversation(session.session_id, "test-property", "restaurant-test", "Need assistance")
            waiting_ids.add(session.session_id)
    sessions.create("another-property", "out-of-scope-guest")

    first = admin_client.get("/api/admin/properties/test-property/conversations?limit=20&offset=0")
    second = admin_client.get("/api/admin/properties/test-property/conversations?limit=20&offset=20")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["total"] == 105
    assert first_payload["limit"] == 20
    assert first_payload["offset"] == 0
    assert len(first_payload["conversations"]) == len(second_payload["conversations"]) == 20
    first_ids = {item["session_id"] for item in first_payload["conversations"]}
    second_ids = {item["session_id"] for item in second_payload["conversations"]}
    assert first_ids.isdisjoint(second_ids)
    assert not any(item["client_id"] == "out-of-scope-guest" for item in first_payload["conversations"] + second_payload["conversations"])
    assert first_payload["status_counts"]["waiting_for_staff"] == len(waiting_ids)

    waiting = admin_client.get("/api/admin/properties/test-property/conversations?limit=3&status=waiting_for_staff")
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["total"] == 7
    assert len(waiting.json()["conversations"]) == 3
    assert {item["state"] for item in waiting.json()["conversations"]} == {"waiting_for_staff"}
    clamped = admin_client.get("/api/admin/properties/test-property/conversations?limit=3&offset=999&status=waiting_for_staff")
    assert clamped.status_code == 200, clamped.text
    assert clamped.json()["offset"] == 6
    assert len(clamped.json()["conversations"]) == 1

    assert admin_client.get("/api/admin/properties/test-property/conversations?limit=101").status_code == 422
    assert admin_client.get("/api/admin/properties/test-property/conversations?offset=1000001").status_code == 422
    assert admin_client.get("/api/admin/properties/test-property/conversations?status=waiting_for_staff%20OR%201%3D1").status_code == 422
