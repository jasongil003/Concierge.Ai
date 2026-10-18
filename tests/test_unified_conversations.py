from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module
from app.admin_auth import AdminAuthStore
from app.guest_identity import GuestIdentityStore
from app.guardrails import RateLimiter
from app.hospitality import HospitalityStore
from app.main import app
from app.properties import PropertyRecord, PropertyStore
from app.session_store import SessionStore


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/api/admin/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["user"]["csrf_token"]


def test_unified_conversation_transcript_scope_notes_unread_and_idempotent_reply(
    tmp_path: Path, monkeypatch,
):
    database = tmp_path / "unified-conversations.db"
    properties = PropertyStore(database)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    hospitality = HospitalityStore(database)
    housekeeping = hospitality.upsert_department(
        "hotel-a", {"department_id": "dept-housekeeping", "name": "Housekeeping"},
    )
    security = hospitality.upsert_department(
        "hotel-a", {"department_id": "dept-security", "name": "Security"},
    )
    sessions = SessionStore(database)
    auth = AdminAuthStore(database)

    property_admin = auth.create_user({
        "username": "unified.property.admin",
        "display_name": "Property Admin",
        "password": "PropertyAdmin123!",
        "role_id": "role-property-administrator",
        "property_id": "hotel-a",
        "status": "active",
        "force_password_change": False,
    }, actor=None)
    department_manager = auth.create_user({
        "username": "unified.housekeeping",
        "display_name": "Housekeeping Lead",
        "password": "Housekeeping123!",
        "role_id": "role-department-manager",
        "property_id": "hotel-a",
        "department_id": housekeeping["department_id"],
        "status": "active",
        "force_password_change": False,
    }, actor=None)
    guest_session = sessions.create("hotel-a", "unified-guest")
    sessions.record_message(guest_session.session_id, "hotel-a", "guest", "Please send extra towels.")
    sessions.record_message(guest_session.session_id, "hotel-a", "assistant", "I can arrange extra towels.")

    other_session = sessions.create("hotel-a", "other-department-guest")
    sessions.record_message(other_session.session_id, "hotel-a", "guest", "Please check a hallway light.")
    sessions.record_message(other_session.session_id, "hotel-a", "assistant", "I will route that to the team.")

    monkeypatch.setattr(main_module, "properties", properties)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "store", sessions)
    monkeypatch.setattr(main_module, "guest_identities", GuestIdentityStore(database))
    monkeypatch.setattr(main_module, "admin_auth", auth)
    monkeypatch.setattr(main_module, "rate_limiter", RateLimiter())
    monkeypatch.setattr(
        main_module, "security_audit",
        type("NullAudit", (), {"record": lambda self, *args, **kwargs: None})(),
    )

    with TestClient(app) as admin_client, TestClient(app) as department_client:
        _login(admin_client, property_admin["username"], "PropertyAdmin123!")
        routed = admin_client.post(
            f"/api/admin/properties/hotel-a/conversations/{guest_session.session_id}/route",
            json={"department_id": housekeeping["department_id"]},
        )
        assert routed.status_code == 200, routed.text
        routed_other = admin_client.post(
            f"/api/admin/properties/hotel-a/conversations/{other_session.session_id}/route",
            json={"department_id": security["department_id"]},
        )
        assert routed_other.status_code == 200, routed_other.text

        _login(department_client, department_manager["username"], "Housekeeping123!")
        inbox = department_client.get("/api/admin/properties/hotel-a/conversations").json()
        assert inbox["total"] == 1
        assert len(inbox["conversations"]) == 1
        summary = inbox["conversations"][0]
        assert summary["session_id"] == guest_session.session_id
        assert "client_id" not in summary
        assert summary["unread_count"] == 1
        assert "extra towels" in summary["last_message_preview"].lower()
        assert department_client.get("/api/admin/properties/hotel-a/conversations?unread=true").json()["total"] == 1

        detail_url = (
            f"/api/admin/properties/hotel-a/conversations/{guest_session.session_id}/detail"
        )
        detail = department_client.get(detail_url)
        assert detail.status_code == 200, detail.text
        transcript = detail.json()["messages"]
        assert [message["role"] for message in transcript] == ["guest", "assistant"]
        assert transcript[0]["content"] == "Please send extra towels."
        assert transcript[1]["content"] == "I can arrange extra towels."
        assert detail.json()["permissions"]["transcript"] is True
        assert detail.json()["permissions"]["stay"] is False

        hidden_detail = department_client.get(
            f"/api/admin/properties/hotel-a/conversations/{other_session.session_id}/detail"
        )
        assert hidden_detail.status_code == 404
        assert department_client.get(
            f"/api/admin/properties/hotel-b/conversations/{guest_session.session_id}/detail"
        ).status_code == 403

        note_response = department_client.post(
            f"/api/admin/properties/hotel-a/conversations/{guest_session.session_id}/notes",
            json={"note": "Room is preparing for a family arrival."},
        )
        assert note_response.status_code == 200, note_response.text
        with sessions._connect() as db:
            stored_note = db.execute(
                "SELECT content FROM conversation_notes WHERE property_id=? AND session_id=?",
                ("hotel-a", guest_session.session_id),
            ).fetchone()
        assert stored_note is not None
        assert "family arrival" not in stored_note["content"]
        assert department_client.get(detail_url).json()["notes"][0]["content"] == "Room is preparing for a family arrival."

        marked_read = department_client.post(
            f"/api/admin/properties/hotel-a/conversations/{guest_session.session_id}/read",
        )
        assert marked_read.status_code == 200, marked_read.text
        refreshed = department_client.get("/api/admin/properties/hotel-a/conversations").json()
        assert refreshed["conversations"][0]["unread_count"] == 0
        assert department_client.get("/api/admin/properties/hotel-a/conversations?unread=true").json()["total"] == 0

        takeover = department_client.put(
            f"/api/admin/properties/hotel-a/conversations/{guest_session.session_id}",
            json={"status": "open", "human_takeover": True},
        )
        assert takeover.status_code == 200, takeover.text
        assert takeover.json()["state"] == "human_active"

        reply_url = f"/api/admin/properties/hotel-a/conversations/{guest_session.session_id}/messages"
        reply_payload = {
            "message": "Housekeeping is bringing the towels.",
            "client_message_id": "request-reply-001",
        }
        first_reply = department_client.post(reply_url, json=reply_payload)
        retry_reply = department_client.post(reply_url, json=reply_payload)
        assert first_reply.status_code == 200, first_reply.text
        assert retry_reply.status_code == 200, retry_reply.text
        assert retry_reply.json()["duplicate"] is True
        final_detail = department_client.get(detail_url).json()
        matching_staff_replies = [
            item for item in final_detail["messages"]
            if item["role"] == "staff" and item["content"] == reply_payload["message"]
        ]
        assert len(matching_staff_replies) == 1

