import uuid

import pytest

import app.main as main_module
from app.properties import PropertyRecord


def _start_campaign_guest(admin_client, property_id: str, device_id: str | None = None):
    response = admin_client.post("/api/session/start", json={
        "client_id": f"campaign-{uuid.uuid4().hex}", "property_id": property_id,
    })
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    main_module.store.mark_authenticated(session_id)
    if device_id is None:
        mac = ":".join(f"{part:02x}" for part in bytes.fromhex(uuid.uuid4().hex[:12]))
        device_id = main_module.guest_identities.observe_device(property_id, mac)
    stay = main_module.guest_identities.reconnect_or_create_stay(
        property_id, device_id, concierge_session_id=session_id,
    )
    return session_id, device_id, stay


def _campaign_payload(**overrides):
    payload = {
        "name": "Verified pool update",
        "title": "Pool hours this week",
        "body": "The pool closes at 8 PM this week.",
        "source_reference": "operations-event-2026-10-16",
    }
    payload.update(overrides)
    return payload


def _create_campaign(admin_client, property_id: str, **overrides):
    response = admin_client.post(
        f"/api/admin/properties/{property_id}/notification-campaigns",
        json=_campaign_payload(**overrides),
    )
    assert response.status_code == 200, response.text
    return response.json()["campaign"]


def _grant_campaign_consent(property_id: str, session_id: str, stay_id: str):
    main_module.privacy_consents.set(
        property_id, session_id, {"promotional_messages": True}, linked_stay_id=stay_id,
    )
    main_module.hospitality.set_guest_notification_preference(
        property_id, stay_id, "promotional", True,
    )


def test_campaign_preview_and_publish_only_queue_for_fully_consented_active_stays(admin_client):
    property_id = f"campaign-{uuid.uuid4().hex[:12]}"
    main_module.properties.upsert(PropertyRecord(property_id=property_id, hotel_name="Campaign Test Hotel", timezone="Asia/Manila"))
    eligible_session, _device, eligible_stay = _start_campaign_guest(admin_client, property_id)
    consent_missing_session, _device, consent_missing_stay = _start_campaign_guest(admin_client, property_id)
    preference_disabled_session, _device, preference_disabled_stay = _start_campaign_guest(admin_client, property_id)
    _grant_campaign_consent(property_id, eligible_session, eligible_stay["stay_id"])
    _grant_campaign_consent(property_id, preference_disabled_session, preference_disabled_stay["stay_id"])
    main_module.hospitality.set_guest_notification_preference(
        property_id, preference_disabled_stay["stay_id"], "promotional", False,
    )

    campaign = _create_campaign(admin_client, property_id)
    campaign_path = f"/api/admin/properties/{property_id}/notification-campaigns/{campaign['campaign_id']}"
    preview = admin_client.post(f"{campaign_path}/preview", json={"expected_revision": campaign["revision"]})
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "campaign_id": campaign["campaign_id"],
        "revision": campaign["revision"],
        "audience": "active_stays_with_promotional_consent",
        "active_stays": 3,
        "eligible": 1,
        "no_active_guest_session": 0,
        "promotional_consent_required": 1,
        "promotional_preference_disabled": 1,
    }
    assert "stay_id" not in preview.text and "session_id" not in preview.text

    published = admin_client.post(f"{campaign_path}/publish", json={"expected_revision": campaign["revision"]})
    assert published.status_code == 200, published.text
    assert published.json()["queued"] == 1
    assert published.json()["already_queued"] == 0
    assert published.json()["suppressed_at_publish"] == 2
    assert published.json()["delivery_state"].startswith("queued_in_app;")

    eligible_items = main_module.hospitality.list_guest_inbox_notifications(property_id, eligible_stay["stay_id"])
    denied_items = main_module.hospitality.list_guest_inbox_notifications(property_id, consent_missing_stay["stay_id"])
    preference_items = main_module.hospitality.list_guest_inbox_notifications(property_id, preference_disabled_stay["stay_id"])
    assert len(eligible_items) == 1
    assert eligible_items[0]["event_id"] == f"campaign:{campaign['campaign_id']}"
    assert eligible_items[0]["category"] == "promotional"
    assert denied_items == []
    assert preference_items == []

    duplicate = admin_client.post(f"{campaign_path}/publish", json={"expected_revision": published.json()["campaign"]["revision"]})
    assert duplicate.status_code == 409
    assert len(main_module.hospitality.list_guest_inbox_notifications(property_id, eligible_stay["stay_id"])) == 1


def test_campaign_draft_revision_is_compare_and_swap_and_property_scoped(admin_client):
    property_id = f"campaign-{uuid.uuid4().hex[:12]}"
    other_property_id = f"campaign-other-{uuid.uuid4().hex[:8]}"
    main_module.properties.upsert(PropertyRecord(property_id=property_id, hotel_name="Campaign Test Hotel"))
    main_module.properties.upsert(PropertyRecord(property_id=other_property_id, hotel_name="Other Campaign Hotel"))
    campaign = _create_campaign(admin_client, property_id)
    path = f"/api/admin/properties/{property_id}/notification-campaigns/{campaign['campaign_id']}"

    saved = admin_client.put(path, json=_campaign_payload(
        title="Updated verified pool hours", expected_revision=1,
    ))
    assert saved.status_code == 200, saved.text
    assert saved.json()["campaign"]["revision"] == 2
    assert saved.json()["campaign"]["status"] == "draft"
    assert "policy" not in saved.json()["campaign"]

    stale = admin_client.put(path, json=_campaign_payload(
        title="Stale overwrite", expected_revision=1,
    ))
    assert stale.status_code == 409
    assert "Stale overwrite" not in admin_client.get(
        f"/api/admin/properties/{property_id}/notification-campaigns"
    ).text

    cross_property = admin_client.get(
        f"/api/admin/properties/{other_property_id}/notification-campaigns/{campaign['campaign_id']}"
    )
    assert cross_property.status_code == 403
    with pytest.raises(KeyError):
        main_module.hospitality.get_notification_campaign(other_property_id, campaign["campaign_id"])
    stale_preview = admin_client.post(f"{path}/preview", json={"expected_revision": 1})
    assert stale_preview.status_code == 409


def test_campaign_publish_rechecks_consent_after_preview_and_queue_guard_checks_every_linked_session(admin_client):
    property_id = f"campaign-{uuid.uuid4().hex[:12]}"
    main_module.properties.upsert(PropertyRecord(property_id=property_id, hotel_name="Campaign Consent Hotel"))
    session_id, device_id, stay = _start_campaign_guest(admin_client, property_id)
    _grant_campaign_consent(property_id, session_id, stay["stay_id"])
    campaign = _create_campaign(admin_client, property_id)
    path = f"/api/admin/properties/{property_id}/notification-campaigns/{campaign['campaign_id']}"

    preview = admin_client.post(f"{path}/preview", json={"expected_revision": 1})
    assert preview.status_code == 200 and preview.json()["eligible"] == 1
    main_module.privacy_consents.set(
        property_id, session_id, {"promotional_messages": False}, linked_stay_id=stay["stay_id"],
    )
    revoked_publish = admin_client.post(f"{path}/publish", json={"expected_revision": 1})
    assert revoked_publish.status_code == 409
    assert main_module.hospitality.list_guest_inbox_notifications(property_id, stay["stay_id"]) == []

    second_session, _same_device, same_stay = _start_campaign_guest(admin_client, property_id, device_id=device_id)
    assert same_stay["stay_id"] == stay["stay_id"]
    _grant_campaign_consent(property_id, session_id, stay["stay_id"])
    main_module.hospitality.set_guest_notification_preference(property_id, stay["stay_id"], "promotional", True)
    event_id = f"campaign:manual-{uuid.uuid4().hex}"
    with pytest.raises(PermissionError):
        main_module.hospitality.create_guest_inbox_notification(
            property_id, stay["stay_id"], event_id, "promotional",
            "Campaign", "This should not queue.", require_promotional_consent=True,
        )
    assert main_module.privacy_consents.get(property_id, second_session, location_stay_id=stay["stay_id"])["promotional_messages"] is False

    # Simulate a previously queued shared inbox item; dispatch must suppress it
    # if a new linked session has not opted in, even if another session has.
    main_module.hospitality.create_guest_inbox_notification(
        property_id, stay["stay_id"], event_id, "promotional", "Campaign", "Shared inbox message.",
    )
    assert main_module._dispatch_guest_inbox_notifications(property_id=property_id) == 0
    assert main_module.hospitality.list_guest_inbox_notifications(property_id, stay["stay_id"]) == []
