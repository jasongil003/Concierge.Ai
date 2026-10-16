import sqlite3
import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

import app.main as main_module
from app.guest_identity import GuestIdentityStore, pseudonymous_device_id
from app.location_analytics import LocationAnalyticsStore
from app.privacy_consent import CONSENT_CATEGORIES, PrivacyConsentStore
from app.hospitality import HospitalityStore
from app.properties import PropertyRecord


def _new_guest(admin_client, property_id="test-property"):
    response = admin_client.post(
        "/api/session/start",
        json={"client_id": f"privacy-{uuid.uuid4().hex}", "property_id": property_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def _create_property(location_enabled=False):
    property_id = f"privacy-property-{uuid.uuid4().hex[:10]}"
    main_module.properties.upsert(PropertyRecord(
        property_id=property_id,
        hotel_name="ZZZ Privacy Test Property",
        guardrails={"location_access_enabled": location_enabled},
    ))
    return property_id


def _create_test_access_point(property_id):
    building = main_module.zones.create_building(property_id, {"name": "Privacy Test Building"})
    floor = main_module.zones.create_floor(property_id, {"building_id": building["building_id"], "name": "Lobby"})
    zone = main_module.zones.upsert_zone(property_id, {
        "floor_id": floor["floor_id"], "name": "Lobby Zone",
        "geometry": {"type": "rectangle", "points": []},
    })
    ap = main_module.zones.create_access_point(property_id, {
        "zone_id": zone["zone_id"], "name": "Lobby AP", "identifier": f"privacy-ap-{uuid.uuid4().hex[:8]}",
    })
    return ap["identifier"]


def _link_active_stay(session_id, property_id="test-property", raw_mac="02:00:00:00:00:01"):
    main_module.store.mark_authenticated(session_id)
    device_id = main_module.guest_identities.observe_device(property_id, raw_mac)
    stay = main_module.guest_identities.reconnect_or_create_stay(
        property_id, device_id, concierge_session_id=session_id,
    )
    return device_id, stay


def test_guest_privacy_defaults_grants_withdraws_and_isolates_properties(admin_client):
    property_a = _create_property()
    property_b = _create_property()
    session_a = _new_guest(admin_client, property_a)
    session_b = _new_guest(admin_client, property_b)

    defaults = admin_client.get("/api/guest/privacy", params={"session_id": session_a})
    assert defaults.status_code == 200, defaults.text
    assert defaults.json()["consents"] == {category: False for category in CONSENT_CATEGORIES}

    _link_active_stay(session_a, property_a, "02:00:00:00:00:61")
    granted = admin_client.put("/api/guest/privacy", json={
        "session_id": session_a,
        "consents": {"location_services": True, "promotional_messages": True},
    })
    assert granted.status_code == 200, granted.text
    assert granted.json()["consents"]["location_services"] is True
    assert granted.json()["consents"]["promotional_messages"] is True
    assert granted.json()["consents"]["proactive_notifications"] is False

    isolated = admin_client.get("/api/guest/privacy", params={"session_id": session_b})
    assert isolated.status_code == 200, isolated.text
    assert isolated.json()["consents"] == {category: False for category in CONSENT_CATEGORIES}

    withdrawn = admin_client.put("/api/guest/privacy", json={
        "session_id": session_a,
        "consents": {"location_services": False, "promotional_messages": False},
    })
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["consents"]["location_services"] is False
    assert withdrawn.json()["consents"]["promotional_messages"] is False


def test_guest_privacy_rejects_invalid_session(admin_client):
    response = admin_client.get("/api/guest/privacy", params={"session_id": "missing-privacy-session"})
    assert response.status_code == 401


def test_location_consent_cannot_be_granted_before_stay_link(admin_client):
    property_id = _create_property(location_enabled=True)
    session_id = _new_guest(admin_client, property_id)
    response = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"location_services": True},
    })
    assert response.status_code == 409
    assert admin_client.get("/api/guest/privacy", params={"session_id": session_id}).json()["consents"]["location_services"] is False


def test_nearby_search_requires_external_processing_consent(admin_client, monkeypatch):
    session_id = _new_guest(admin_client)
    called = []

    async def forbidden_places_search(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("Places provider must not receive a request before consent.")

    monkeypatch.setattr(main_module.places, "search_with_status", forbidden_places_search)
    response = admin_client.post("/api/chat", json={
        "session_id": session_id,
        "message": "What local attractions are nearby?",
    })
    assert response.status_code == 200, response.text
    assert response.json()["nearby_status"] == "consent_required"
    assert response.json()["live_places_used"] is False
    assert called == []


def test_location_observation_requires_consent_and_never_persists_unauthorized_mac(admin_client):
    property_id = _create_property(location_enabled=True)
    ap = _create_test_access_point(property_id)
    session_id = _new_guest(admin_client, property_id)
    linked_mac = "02:00:00:00:00:11"
    _link_active_stay(session_id, property_id, linked_mac)
    stranger_mac = "02:00:00:00:00:12"
    stranger_device_id = pseudonymous_device_id(main_module.guest_identities.property_secret(property_id), stranger_mac)
    before_devices = {row["device_id"] for row in main_module.guest_identities.list_devices(property_id)}

    response = admin_client.post(
        f"/api/admin/properties/{property_id}/location/observations",
        json={"session_id": session_id, "raw_mac": stranger_mac, "access_point_identifier": ap},
    )
    after_devices = {row["device_id"] for row in main_module.guest_identities.list_devices(property_id)}
    assert response.status_code == 403
    assert after_devices == before_devices
    assert stranger_device_id not in after_devices
    with main_module.location_analytics._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM location_observations WHERE property_id=?", (property_id,)).fetchone()[0] == 0


def test_location_observation_grant_withdrawal_and_server_derived_binding(admin_client):
    property_id = _create_property(location_enabled=True)
    ap = _create_test_access_point(property_id)
    session_id = _new_guest(admin_client, property_id)
    mac = "02:00:00:00:00:21"
    device_id, stay = _link_active_stay(session_id, property_id, mac)

    grant = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"location_services": True},
    })
    assert grant.status_code == 200, grant.text

    observation = admin_client.post(
        f"/api/admin/properties/{property_id}/location/observations",
        json={"session_id": session_id, "raw_mac": mac, "access_point_identifier": ap},
    )
    assert observation.status_code == 200, observation.text
    assert observation.json()["device_id"] == device_id
    assert observation.json()["stay_id"] == stay["stay_id"]
    assert "raw_mac" not in observation.json()

    forged = admin_client.post(
        f"/api/admin/properties/{property_id}/location/observations",
        json={
            "session_id": session_id, "raw_mac": mac, "access_point_identifier": ap,
            "stay_id": "caller-claimed-stay", "device_id": "caller-claimed-device",
        },
    )
    assert forged.status_code == 422

    withdrawn = admin_client.put("/api/guest/privacy", json={
        "session_id": session_id, "consents": {"location_services": False},
    })
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["consents"]["location_services"] is False
    rejected = admin_client.post(
        f"/api/admin/properties/{property_id}/location/observations",
        json={"session_id": session_id, "raw_mac": mac, "access_point_identifier": ap},
    )
    assert rejected.status_code == 403
    with main_module.location_analytics._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM location_observations WHERE stay_id=?", (stay["stay_id"],)).fetchone()[0] == 0


def test_location_observation_requires_active_property_policy_and_valid_session(admin_client):
    property_id = _create_property(location_enabled=False)
    ap = _create_test_access_point(property_id)
    session_id = _new_guest(admin_client, property_id)
    mac = "02:00:00:00:00:31"
    _link_active_stay(session_id, property_id, mac)
    admin_client.put("/api/guest/privacy", json={"session_id": session_id, "consents": {"location_services": True}})

    disabled = admin_client.post(
        f"/api/admin/properties/{property_id}/location/observations",
        json={"session_id": session_id, "raw_mac": mac, "access_point_identifier": ap},
    )
    invalid = admin_client.post(
        f"/api/admin/properties/{_create_property(location_enabled=True)}/location/observations",
        json={"session_id": "not-a-session", "raw_mac": mac, "access_point_identifier": ap},
    )
    assert disabled.status_code == 403
    assert invalid.status_code == 401


def test_checkout_erases_guest_consent_and_location_data(admin_client):
    property_id = _create_property(location_enabled=True)
    ap = _create_test_access_point(property_id)
    session_id = _new_guest(admin_client, property_id)
    mac = "02:00:00:00:00:41"
    _, stay = _link_active_stay(session_id, property_id, mac)
    admin_client.put("/api/guest/privacy", json={"session_id": session_id, "consents": {"location_services": True}})
    recorded = admin_client.post(
        f"/api/admin/properties/{property_id}/location/observations",
        json={"session_id": session_id, "raw_mac": mac, "access_point_identifier": ap},
    )
    assert recorded.status_code == 200, recorded.text

    checkout = admin_client.post(f"/api/admin/properties/{property_id}/stays/{stay['stay_id']}/checkout")
    assert checkout.status_code == 200, checkout.text
    assert admin_client.get("/api/guest/privacy", params={"session_id": session_id}).json()["consents"] == {
        category: False for category in CONSENT_CATEGORIES
    }
    with main_module.location_analytics._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM location_observations WHERE stay_id=?", (stay["stay_id"],)).fetchone()[0] == 0


def test_consent_and_location_retention_cleanup(tmp_path: Path):
    db_path = tmp_path / "privacy-retention.db"
    identities = GuestIdentityStore(db_path)
    consents = PrivacyConsentStore(db_path)
    analytics = LocationAnalyticsStore(db_path)
    property_id = "retention-property"
    session_id = "retention-session"
    device_id = identities.observe_device(property_id, "02:00:00:00:00:51")
    stay = identities.reconnect_or_create_stay(property_id, device_id, concierge_session_id=session_id)
    consents.set(
        property_id,
        session_id,
        {"location_services": True},
        expires_at=10_000,
        location_stay_id=stay["stay_id"],
        now=100,
    )
    analytics.record_observation(property_id, device_id, "zone-retention", "ap-retention", stay_id=stay["stay_id"], observed_at=100)
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE concierge_stays SET retention_until=100 WHERE property_id=? AND stay_id=?", (property_id, stay["stay_id"]))

    assert consents.cleanup_retention(now=101) == 0
    assert analytics.cleanup_retention(now=101) == 0
    assert consents.get(
        property_id, session_id, now=101, location_stay_id=stay["stay_id"],
    )["location_services"] is True
    identities.checkout(property_id, stay["stay_id"])
    assert consents.cleanup_retention(now=101) >= 1
    assert analytics.cleanup_retention(now=101) >= 1
    assert consents.get(property_id, session_id, now=101)["location_services"] is False
    assert analytics.live(property_id)["currently_detected"] == 0


def test_active_stay_survives_five_day_retention_and_reconnect(tmp_path: Path, monkeypatch):
    import app.guest_identity as identity_module

    db_path = tmp_path / "long-active-stay.db"
    identities = GuestIdentityStore(db_path)
    start = 1_000
    monkeypatch.setattr(identity_module, "_now", lambda: start)
    device_id = identities.observe_device("long-stay-property", "02:00:00:00:00:71")
    first = identities.reconnect_or_create_stay(
        "long-stay-property", device_id, concierge_session_id="long-stay-session-a", retention_days=1,
    )

    # Simulate a database from before the lifecycle migration, where active
    # rows incorrectly carried a post-checkout deadline from check-in.
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE concierge_stays SET retention_until=? WHERE stay_id=?", (start + 1, first["stay_id"]))
        db.execute("ALTER TABLE concierge_stays DROP COLUMN retention_days")
    identities = GuestIdentityStore(db_path)

    after_five_days = start + 5 * 86_400
    monkeypatch.setattr(identity_module, "_now", lambda: after_five_days)
    assert identities.cleanup_retention(now=after_five_days) == 0
    second = identities.reconnect_or_create_stay(
        "long-stay-property", device_id, concierge_session_id="long-stay-session-b", retention_days=1,
    )

    assert second["stay_id"] == first["stay_id"]
    assert second["status"] == "active"
    assert second["retention_until"] is None
    assert {row["concierge_session_id"] for row in identities.list_guest_sessions("long-stay-property")} == {
        "long-stay-session-a", "long-stay-session-b",
    }


def test_checkout_starts_retention_and_repeat_checkout_does_not_extend_it(tmp_path: Path, monkeypatch):
    import app.guest_identity as identity_module

    identities = GuestIdentityStore(tmp_path / "early-checkout.db")
    monkeypatch.setattr(identity_module, "_now", lambda: 100)
    device_id = identities.observe_device("checkout-property", "02:00:00:00:00:72")
    stay = identities.reconnect_or_create_stay(
        "checkout-property", device_id, concierge_session_id="checkout-session", retention_days=2,
    )

    checkout_at = 1_000
    monkeypatch.setattr(identity_module, "_now", lambda: checkout_at)
    checked_out = identities.checkout("checkout-property", stay["stay_id"])
    assert checked_out["retention_until"] == checkout_at + 2 * 86_400
    first_checkout_time = checked_out["checked_out_at"]

    monkeypatch.setattr(identity_module, "_now", lambda: checkout_at + 3_600)
    repeated = identities.checkout("checkout-property", stay["stay_id"])
    assert repeated["retention_until"] == checked_out["retention_until"]
    assert repeated["checked_out_at"] == first_checkout_time
    assert identities.cleanup_retention(now=checkout_at + 2 * 86_400 - 1) == 0
    assert identities.cleanup_retention(now=checkout_at + 2 * 86_400) == 1
    assert identities.cleanup_retention(now=checkout_at + 2 * 86_400) == 0


def test_session_reconnect_uses_server_retention_policy_not_client_value(admin_client):
    property_id = _create_property()
    original = main_module.settings.guest_data_retention_days
    object.__setattr__(main_module.settings, "guest_data_retention_days", 5)
    try:
        response = admin_client.post(
            f"/api/admin/properties/{property_id}/sessions/reconnect",
            json={"raw_mac": "02:00:00:00:00:76", "retention_days": 0},
        )
        assert response.status_code == 200, response.text
        stay = response.json()["stay"]
        assert stay["retention_days"] == 5
        assert stay["retention_until"] is None
    finally:
        object.__setattr__(main_module.settings, "guest_data_retention_days", original)


def test_concurrent_retention_cleanup_is_idempotent_and_property_scoped(tmp_path: Path, monkeypatch):
    import app.guest_identity as identity_module

    db_path = tmp_path / "concurrent-retention.db"
    first_store = GuestIdentityStore(db_path)
    second_store = GuestIdentityStore(db_path)
    monkeypatch.setattr(identity_module, "_now", lambda: 100)
    shared_mac = "02:00:00:00:00:73"
    device_a = first_store.observe_device("cleanup-property-a", shared_mac)
    device_b = first_store.observe_device("cleanup-property-b", shared_mac)
    stay_a = first_store.reconnect_or_create_stay(
        "cleanup-property-a", device_a, concierge_session_id="cleanup-session-a", retention_days=0,
    )
    stay_b = first_store.reconnect_or_create_stay(
        "cleanup-property-b", device_b, concierge_session_id="cleanup-session-b", retention_days=0,
    )
    first_store.checkout("cleanup-property-a", stay_a["stay_id"])
    first_store.checkout("cleanup-property-b", stay_b["stay_id"])
    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO guest_sessions VALUES(?,?,?,?,?,?,?,?)",
            ("orphan-session", "cleanup-property-a", "missing-stay", "orphan-concierge", None, None, 100, 100),
        )

    barrier = Barrier(2)

    def cleanup(store):
        barrier.wait()
        return store.cleanup_retention(property_id="cleanup-property-a", now=100)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(cleanup, (first_store, second_store)))

    assert sorted(results) == [0, 1]
    assert first_store.list_stays("cleanup-property-a") == []
    assert [row["stay_id"] for row in first_store.list_stays("cleanup-property-b")] == [stay_b["stay_id"]]
    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM guest_sessions WHERE property_id='cleanup-property-a'"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM device_identities WHERE property_id='cleanup-property-a'"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM device_identities WHERE property_id='cleanup-property-b'"
        ).fetchone()[0] == 1
    assert first_store.cleanup_retention(property_id="cleanup-property-a", now=100) == 0


def test_expired_optional_consent_is_retained_for_active_stay_then_removed_on_checkout(tmp_path: Path):
    db_path = tmp_path / "active-consent-retention.db"
    identities = GuestIdentityStore(db_path)
    consents = PrivacyConsentStore(db_path)
    property_id = "active-consent-property"
    session_id = "active-consent-session"
    device_id = identities.observe_device(property_id, "02:00:00:00:00:74")
    stay = identities.reconnect_or_create_stay(property_id, device_id, concierge_session_id=session_id)
    consents.set(
        property_id, session_id, {"proactive_notifications": True},
        expires_at=101, linked_stay_id=stay["stay_id"], now=100,
    )

    assert consents.cleanup_retention(now=200) == 0
    assert consents.get(property_id, session_id, now=200)["proactive_notifications"] is True

    identities.checkout(property_id, stay["stay_id"])
    assert consents.cleanup_retention(now=200) == 1
    assert consents.get(property_id, session_id, now=200)["proactive_notifications"] is False


def test_optional_consent_withdrawal_cascades_across_linked_sessions(admin_client):
    property_id = _create_property()
    session_a = _new_guest(admin_client, property_id)
    session_b = _new_guest(admin_client, property_id)
    main_module.store.mark_authenticated(session_a)
    main_module.store.mark_authenticated(session_b)
    device_id = main_module.guest_identities.observe_device(property_id, "02:00:00:00:00:75")
    stay = main_module.guest_identities.reconnect_or_create_stay(
        property_id, device_id, concierge_session_id=session_a,
    )
    second_link = main_module.guest_identities.reconnect_or_create_stay(
        property_id, device_id, concierge_session_id=session_b,
    )
    assert second_link["stay_id"] == stay["stay_id"]

    for session_id in (session_a, session_b):
        response = admin_client.put("/api/guest/privacy", json={
            "session_id": session_id, "consents": {"proactive_notifications": True},
        })
        assert response.status_code == 200, response.text

    withdrawn = admin_client.put("/api/guest/privacy", json={
        "session_id": session_a, "consents": {"proactive_notifications": False},
    })
    assert withdrawn.status_code == 200, withdrawn.text
    assert main_module.privacy_consents.get(property_id, session_a)["proactive_notifications"] is False
    assert main_module.privacy_consents.get(property_id, session_b)["proactive_notifications"] is False


def test_periodic_retention_cleans_expired_data_without_app_restart(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "periodic-retention.db"
    identities = GuestIdentityStore(db_path)
    consents = PrivacyConsentStore(db_path)
    analytics = LocationAnalyticsStore(db_path)
    hospitality = HospitalityStore(db_path)
    property_id = "periodic-property"
    session_id = "periodic-session"
    device_id = identities.observe_device(property_id, "02:00:00:00:00:52")
    stay = identities.reconnect_or_create_stay(property_id, device_id, concierge_session_id=session_id)
    consents.set(property_id, session_id, {"location_services": True},
                 expires_at=101, location_stay_id=stay["stay_id"], now=100)
    analytics.record_observation(property_id, device_id, "zone", "ap", stay_id=stay["stay_id"], observed_at=100)
    identities.checkout(property_id, stay["stay_id"])
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE concierge_stays SET retention_until=101 WHERE stay_id=?", (stay["stay_id"],))
    monkeypatch.setattr(main_module, "privacy_consents", consents)
    monkeypatch.setattr(main_module, "location_analytics", analytics)
    monkeypatch.setattr(main_module, "hospitality", hospitality)
    monkeypatch.setattr(main_module, "guest_identities", identities)
    monkeypatch.setattr(main_module.personalization, "cleanup_expired", lambda: 0)

    async def run_worker():
        worker = asyncio.create_task(main_module._retention_maintenance_worker(0.01))
        try:
            for _ in range(100):
                await asyncio.sleep(0.01)
                with sqlite3.connect(db_path) as db:
                    remaining = db.execute("SELECT COUNT(*) FROM location_observations").fetchone()[0]
                if remaining == 0:
                    break
            assert remaining == 0
        finally:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    asyncio.run(run_worker())
    assert consents.get(property_id, session_id)["location_services"] is False
    assert identities.list_stays(property_id) == []
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM guest_sessions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM device_identities").fetchone()[0] == 0
    counts = main_module._run_retention_maintenance()
    assert counts["location"] == 0
    assert counts["stays"] == 0
