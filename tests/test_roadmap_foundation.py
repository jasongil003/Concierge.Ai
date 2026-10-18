import base64
from datetime import datetime, timezone
from pathlib import Path

from app.guest_identity import GuestIdentityStore, pseudonymous_device_id
from app.intro import IntroExperienceStore
from app.location_analytics import LocationAnalyticsStore
import app.location_analytics as location_analytics_module
from app.properties import PropertyRecord, PropertyStore
import app.zones as zones_module
from app.zones import ZoneStore


def _stores(tmp_path: Path):
    db = tmp_path / "concierge.db"
    upload = tmp_path / "uploads"
    upload.mkdir(parents=True, exist_ok=True)
    zones_module.UPLOAD_ROOT = upload
    properties = PropertyStore(db)
    zones = ZoneStore(db)
    identities = GuestIdentityStore(db)
    analytics = LocationAnalyticsStore(db)
    intro = IntroExperienceStore(db)
    properties.upsert(PropertyRecord(property_id="hotel-a", hotel_name="Hotel A"))
    properties.upsert(PropertyRecord(property_id="hotel-b", hotel_name="Hotel B"))
    return properties, zones, identities, analytics, intro


def test_zones_floor_map_navigation_and_property_isolation(tmp_path: Path):
    _, zones, _, _, _ = _stores(tmp_path)
    building = zones.create_building("hotel-a", {"name": "Tower"})
    floor = zones.create_floor("hotel-a", {"building_id": building["building_id"], "name": "Ground", "level": 0})
    uploaded = zones.save_floor_map(
        "hotel-a",
        floor["floor_id"],
        {
            "filename": "../lobby.svg",
            "content_type": "image/svg+xml",
            "content_base64": base64.b64encode(
                b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
            ).decode(),
            "width": 1000,
            "height": 800,
        },
    )
    assert uploaded["original_filename"] == "lobby.svg"

    zone = zones.upsert_zone(
        "hotel-a",
        {
            "floor_id": floor["floor_id"],
            "name": "Lobby",
            "geometry": {"type": "polygon", "points": [[0, 0], [10, 0], [10, 10]]},
            "guest_visible": True,
        },
    )
    facility = zones.create_facility("hotel-a", {"zone_id": zone["zone_id"], "name": "Reception"})
    ap = zones.create_access_point("hotel-a", {"zone_id": zone["zone_id"], "name": "AP Lobby", "identifier": "ap-lobby"})
    assert facility["name"] == "Reception"
    assert ap["identifier"] == "ap-lobby"

    start = zones.create_node("hotel-a", {"floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Lobby"})
    end = zones.create_node("hotel-a", {"floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Elevator Lobby"})
    zones.create_edge("hotel-a", {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 12})
    revision = zones.create_map_revision("hotel-a")
    zones.publish_map_revision("hotel-a", revision["revision_id"])
    assert zones.route("hotel-a", start["node_id"], end["node_id"])["labels"] == ["Lobby", "Elevator Lobby"]

    guest_overview = zones.overview("hotel-a", guest=True)
    assert guest_overview["access_points"] == []
    assert guest_overview["zones"][0]["name"] == "Lobby"

    try:
        zones.create_floor("hotel-b", {"building_id": building["building_id"], "name": "Stolen"})
    except KeyError:
        pass
    else:
        raise AssertionError("Cross-property building use should be rejected")


def test_device_pseudonymization_reconnect_memory_checkout_and_retention(tmp_path: Path):
    _, _, identities, _, _ = _stores(tmp_path)
    device_a = identities.observe_device("hotel-a", "AA:BB:CC:DD:EE:FF")
    device_b = identities.observe_device("hotel-b", "AA:BB:CC:DD:EE:FF")
    assert device_a.startswith("device_")
    assert device_a != device_b
    assert pseudonymous_device_id(identities.property_secret("hotel-a"), "aa-bb-cc-dd-ee-ff") == device_a

    first = identities.reconnect_or_create_stay("hotel-a", device_a, concierge_session_id="s1", room="1503")
    second = identities.reconnect_or_create_stay("hotel-a", device_a, concierge_session_id="s2")
    assert first["stay_id"] == second["stay_id"]

    memory = identities.update_memory(
        "hotel-a",
        first["stay_id"],
        {"conversation_summary": "Guest asked for spa directions.", "preferences": ["quiet table"]},
    )
    assert memory["memory_summary"]["preferences"] == ["quiet table"]

    checked_out = identities.checkout("hotel-a", first["stay_id"])
    assert checked_out["status"] == "checked_out"
    assert checked_out["room"] is None
    assert checked_out["memory_summary"] == {}


def test_location_analytics_observation_dwell_movement_and_aggregation(tmp_path: Path):
    _, zones, identities, analytics, _ = _stores(tmp_path)
    building = zones.create_building("hotel-a", {"name": "Tower"})
    floor = zones.create_floor("hotel-a", {"building_id": building["building_id"], "name": "Ground"})
    lobby = zones.upsert_zone("hotel-a", {"floor_id": floor["floor_id"], "name": "Lobby", "geometry": {"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10}})
    pool = zones.upsert_zone("hotel-a", {"floor_id": floor["floor_id"], "name": "Pool", "geometry": {"type": "ellipse", "cx": 50, "cy": 10, "rx": 8, "ry": 8}})
    zones.create_access_point("hotel-a", {"zone_id": lobby["zone_id"], "name": "AP Lobby", "identifier": "ap-lobby"})
    zones.create_access_point("hotel-a", {"zone_id": pool["zone_id"], "name": "AP Pool", "identifier": "ap-pool"})
    device_id = identities.observe_device("hotel-a", "AA:BB:CC:DD:EE:FF")

    analytics.record_observation("hotel-a", device_id, lobby["zone_id"], "ap-lobby", observed_at=100)
    analytics.record_observation("hotel-a", device_id, pool["zone_id"], "ap-pool", observed_at=220)
    report = analytics.aggregate("hotel-a", 0, 300)

    assert report["area_metrics"][lobby["zone_id"]]["average_dwell_seconds"] == 120
    assert report["movement_patterns"][0]["source_zone_id"] == lobby["zone_id"]
    assert report["movement_patterns"][0]["destination_zone_id"] == pool["zone_id"]


def test_live_location_summary_is_recent_property_scoped_and_does_not_expose_device_ids(tmp_path: Path, monkeypatch):
    _, _, _, analytics, _ = _stores(tmp_path)
    monkeypatch.setattr(location_analytics_module, "_now", lambda: 1_000)
    analytics.record_observation("hotel-a", "pseudonymous-a", "lobby", "ap-a", stay_id="stay-a", observed_at=960)
    analytics.record_observation("hotel-a", "pseudonymous-a", "lobby", "ap-a", stay_id="stay-a", observed_at=970)
    analytics.record_observation("hotel-a", "pseudonymous-old", "pool", "ap-b", stay_id="stay-b", observed_at=10)
    analytics.record_observation("hotel-b", "other-property", "lobby", "ap-c", stay_id="stay-c", observed_at=990)

    summary = analytics.live("hotel-a")

    assert summary["currently_detected"] == 1
    assert summary["active_sessions"] == 1
    assert summary["occupancy_by_zone"] == {"lobby": 1}
    assert summary["last_observation_at"] == 970
    assert summary["window_minutes"] == 15
    assert "device_id" not in summary


def test_location_peak_hours_are_property_local_and_deduplicate_devices_per_day(tmp_path: Path):
    _, _, _, analytics, _ = _stores(tmp_path)
    first_day_0900 = int(datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc).timestamp())
    second_day_0900 = int(datetime(2026, 1, 2, 1, 0, tzinfo=timezone.utc).timestamp())
    analytics.record_observation("hotel-a", "device-a", "lobby", "ap-1", stay_id="stay-a", observed_at=first_day_0900)
    analytics.record_observation("hotel-a", "device-a", "lobby", "ap-1", stay_id="stay-a", observed_at=first_day_0900 + 1_800)
    analytics.record_observation("hotel-a", "device-b", "lobby", "ap-2", stay_id="stay-b", observed_at=first_day_0900)
    analytics.record_observation("hotel-a", "device-a", "lobby", "ap-1", stay_id="stay-a", observed_at=second_day_0900)
    analytics.record_observation("hotel-a", "device-c", "lobby", "ap-3", stay_id="stay-c", observed_at=second_day_0900)
    analytics.record_observation("hotel-b", "other-property-device", "lobby", "ap-4", stay_id="stay-x", observed_at=first_day_0900)

    report = analytics.aggregate(
        "hotel-a",
        first_day_0900,
        second_day_0900 + 3_600,
        timezone_name="Asia/Manila",
    )

    assert report["timezone"] == "Asia/Manila"
    assert report["hourly_observed_devices"] == [{
        "hour": 9,
        "average_observed_devices": 2.0,
        "sample_days": 2,
    }]
    assert report["peak_hours"] == report["hourly_observed_devices"]


def test_location_report_rejects_invalid_intervals_and_timezones(tmp_path: Path):
    _, _, _, analytics, _ = _stores(tmp_path)

    import pytest

    with pytest.raises(ValueError, match="end must be at or after its start"):
        analytics.aggregate("hotel-a", 2, 1)
    with pytest.raises(ValueError, match="valid IANA timezone"):
        analytics.aggregate("hotel-a", 1, 2, timezone_name="Mars/Olympus")


def test_intro_config_and_asset_validation(tmp_path: Path):
    _, _, _, _, intro = _stores(tmp_path)
    config = intro.save(
        "hotel-a",
        {
            "mode": "generate_from_logo",
            "preset": "luxury_reveal",
            "duration_ms": 2500,
            "first_visit_only": True,
            "allow_skip": True,
        },
    )
    assert config["preset"] == "luxury_reveal"
    uploaded = intro.upload_asset(
        "hotel-a",
        {"filename": "intro.webm", "content_type": "video/webm", "content_base64": base64.b64encode(b"\x1aE\xdf\xa3\x00\x00\x00\x00").decode()},
    )
    assert uploaded["mode"] == "custom_upload"
    assert uploaded["asset_type"] == "video/webm"

    removed = intro.remove_asset("hotel-a")
    assert removed["asset_url"] == ""
    assert removed["asset_type"] == ""
    assert removed["mode"] == "generate_from_logo"

    try:
        intro.save("hotel-a", {"mode": "custom_upload", "preset": "fade_scale"})
    except ValueError as exc:
        assert "Upload a valid" in str(exc)
    else:
        raise AssertionError("Custom video mode should require an uploaded video")

    try:
        intro.upload_asset(
            "hotel-a",
            {"filename": "bad.exe", "content_type": "application/x-msdownload", "content_base64": base64.b64encode(b"x").decode()},
        )
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Executable uploads should be rejected")
