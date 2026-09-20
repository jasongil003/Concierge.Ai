import base64
from pathlib import Path

from app.guest_identity import GuestIdentityStore, pseudonymous_device_id
from app.intro import IntroExperienceStore
from app.location_analytics import LocationAnalyticsStore
from app.properties import PropertyRecord, PropertyStore
from app.zones import ZoneStore


def _stores(tmp_path: Path):
    db = tmp_path / "concierge.db"
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
            "filename": "../lobby.png",
            "content_type": "image/png",
            "content_base64": base64.b64encode(b"png").decode(),
            "width": 1000,
            "height": 800,
        },
    )
    assert uploaded["original_filename"] == "lobby.png"

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
        {"filename": "intro.webm", "content_type": "video/webm", "content_base64": base64.b64encode(b"webm").decode()},
    )
    assert uploaded["mode"] == "custom_upload"

    try:
        intro.upload_asset(
            "hotel-a",
            {"filename": "bad.exe", "content_type": "application/x-msdownload", "content_base64": base64.b64encode(b"x").decode()},
        )
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Executable uploads should be rejected")
