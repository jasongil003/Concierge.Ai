import base64
import importlib
import json

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, inspect, text

import app.main as main_module
import app.zones as zones_module
from app.zones import ZoneStore


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'


def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(zones_module, "UPLOAD_ROOT", tmp_path / "uploads")
    store = ZoneStore(tmp_path / "zones.db")
    building = store.create_building("hotel-a", {"name": "Main Building"})
    floor = store.create_floor(
        "hotel-a", {"building_id": building["building_id"], "name": "Lobby Floor", "level": 0}
    )
    zone = store.upsert_zone(
        "hotel-a",
        {
            "floor_id": floor["floor_id"],
            "name": "Lobby",
            "geometry": {"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10},
        },
    )
    facility = store.create_facility(
        "hotel-a", {"zone_id": zone["zone_id"], "name": "Front Desk", "description": "Guest services"}
    )
    access_point = store.create_access_point(
        "hotel-a",
        {"zone_id": zone["zone_id"], "name": "Lobby AP", "identifier": "internal-ap-id"},
    )
    node = store.create_node(
        "hotel-a", {"floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Entrance"}
    )
    other_node = store.create_node(
        "hotel-a", {"floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Desk"}
    )
    edge = store.create_edge(
        "hotel-a", {"from_node_id": node["node_id"], "to_node_id": other_node["node_id"], "distance": 3}
    )
    floor_map = store.save_floor_map(
        "hotel-a",
        floor["floor_id"],
        {
            "filename": "floor.svg",
            "content_type": "image/svg+xml",
            "content_base64": base64.b64encode(SVG).decode("ascii"),
        },
    )
    return store, floor, zone, facility, access_point, edge, floor_map


def _counts(store, property_id):
    overview = store.overview(property_id)
    return {
        "buildings": len(overview["buildings"]),
        "floors": len(overview["floors"]),
        "floor_maps": len(overview["maps"]),
        "zones": len(overview["zones"]),
        "facilities": len(overview["facilities"]),
        "access_points": len(overview["access_points"]),
        "navigation_nodes": len(overview["navigation_nodes"]),
        "navigation_edges": len(overview["navigation_edges"]),
    }


def test_revision_creation_preview_and_schema_initialization_are_safe_and_idempotent(tmp_path, monkeypatch):
    store, _floor, _zone, _facility, _access_point, _edge, _map = _store(tmp_path, monkeypatch)
    revision = store.create_map_revision("hotel-a", created_by="admin-7")

    # Reinitializing the SQLite store exercises the additive schema path twice.
    ZoneStore(tmp_path / "zones.db")
    preview = store.preview_map_revision("hotel-a", revision["revision_id"])

    assert revision["status"] == "draft"
    assert revision["revision_kind"] == "snapshot"
    assert preview["preview"]["counts"]["access_points"] == 1
    assert preview["preview"]["floors"][0]["name"] == "Lobby Floor"
    assert "snapshot_json" not in preview
    assert "internal-ap-id" not in json.dumps(preview)
    assert "internal-ap-id" not in json.dumps(store.list_map_revisions("hotel-a"))


def test_publish_is_property_scoped_and_rejects_stale_draft(tmp_path, monkeypatch):
    store, _floor, zone, _facility, _access_point, _edge, _map = _store(tmp_path, monkeypatch)
    draft = store.create_map_revision("hotel-a")
    published = store.publish_map_revision("hotel-a", draft["revision_id"], published_by="admin-7")

    assert published["status"] == "published"
    assert store.current_map_revision("hotel-a")["revision_id"] == draft["revision_id"]
    assert store.publish_map_revision("hotel-a", draft["revision_id"])["revision_id"] == draft["revision_id"]
    with pytest.raises(KeyError, match="Map revision not found"):
        store.publish_map_revision("hotel-b", draft["revision_id"])

    stale = store.create_map_revision("hotel-a")
    store.upsert_zone(
        "hotel-a",
        {
            "zone_id": zone["zone_id"],
            "floor_id": zone["floor_id"],
            "name": "Renamed Lobby",
            "geometry": {"type": "rectangle", "x": 1, "y": 1, "width": 9, "height": 9},
        },
    )
    with pytest.raises(ValueError, match="Map data changed"):
        store.publish_map_revision("hotel-a", stale["revision_id"])
    assert store.current_map_revision("hotel-a")["revision_id"] == draft["revision_id"]


def test_rollback_restores_complete_snapshot_and_keeps_property_boundary(tmp_path, monkeypatch):
    store, floor, zone, facility, access_point, edge, original_map = _store(tmp_path, monkeypatch)
    original = store.create_map_revision("hotel-a", created_by="admin-1")
    store.publish_map_revision("hotel-a", original["revision_id"], published_by="admin-1")
    original_counts = _counts(store, "hotel-a")
    original_map_ids = {item["map_id"] for item in store.overview("hotel-a")["maps"]}

    other_building = store.create_building("hotel-b", {"name": "Separate Hotel"})
    store.create_floor("hotel-b", {"building_id": other_building["building_id"], "name": "Ground"})
    other_property_counts = _counts(store, "hotel-b")

    store.upsert_zone(
        "hotel-a",
        {
            "zone_id": zone["zone_id"],
            "floor_id": floor["floor_id"],
            "name": "Temporary Lobby",
            "geometry": {"type": "rectangle", "x": 4, "y": 4, "width": 2, "height": 2},
        },
    )
    store.update_facility(
        "hotel-a", facility["facility_id"], {"zone_id": zone["zone_id"], "name": "Temporary Desk"}
    )
    store.delete_map_record("hotel-a", "access_point", access_point["access_point_id"])
    store.delete_map_record("hotel-a", "navigation_edge", edge["edge_id"])
    changed_map = store.save_floor_map(
        "hotel-a",
        floor["floor_id"],
        {
            "filename": "temporary.svg",
            "content_type": "image/svg+xml",
            "content_base64": base64.b64encode(SVG).decode("ascii"),
        },
    )
    changed_draft = store.create_map_revision("hotel-a")
    store.publish_map_revision("hotel-a", changed_draft["revision_id"])

    restored = store.restore_map_revision(
        "hotel-a", original["revision_id"], restored_by="admin-2", expected_current_revision_id=changed_draft["revision_id"]
    )
    assert restored["status"] == "published"
    assert restored["revision_kind"] == "rollback"
    assert restored["restored_from_revision_id"] == original["revision_id"]
    assert restored["rollback_backup_revision_id"]
    assert store.current_map_revision("hotel-a")["revision_id"] == restored["revision_id"]
    assert _counts(store, "hotel-a") == original_counts
    assert {item["map_id"] for item in store.overview("hotel-a")["maps"]} == original_map_ids
    assert store.overview("hotel-a")["zones"][0]["name"] == "Lobby"
    assert store.overview("hotel-a")["facilities"][0]["name"] == "Front Desk"
    assert store.overview("hotel-a")["access_points"][0]["identifier"] == "internal-ap-id"
    assert store.floor_map_path("hotel-a", original_map["map_id"]).is_file()
    with pytest.raises(KeyError, match="Floor map not found"):
        store.floor_map_path("hotel-a", changed_map["map_id"])
    assert _counts(store, "hotel-b") == other_property_counts

    backup = store.preview_map_revision("hotel-a", restored["rollback_backup_revision_id"])
    assert backup["status"] == "draft"
    assert backup["revision_kind"] == "rollback_backup"
    with pytest.raises(KeyError, match="Map revision not found"):
        store.restore_map_revision("hotel-b", original["revision_id"])


def test_restore_requires_a_published_revision_and_preview_checks_snapshot_integrity(tmp_path, monkeypatch):
    store, _floor, _zone, _facility, _access_point, _edge, _map = _store(tmp_path, monkeypatch)
    draft = store.create_map_revision("hotel-a")
    with pytest.raises(ValueError, match="Only a published map revision can be restored"):
        store.restore_map_revision("hotel-a", draft["revision_id"])

    with store._connect() as db:
        db.execute(
            "UPDATE map_revisions SET snapshot_json=? WHERE property_id=? AND revision_id=?",
            ('{"format":1}', "hotel-a", draft["revision_id"]),
        )
    with pytest.raises(ValueError, match="integrity check failed"):
        store.preview_map_revision("hotel-a", draft["revision_id"])


def test_revision_snapshot_rejects_floor_map_asset_from_another_property(tmp_path, monkeypatch):
    store, _floor, _zone, _facility, _access_point, _edge, _map = _store(tmp_path, monkeypatch)
    other_building = store.create_building("hotel-b", {"name": "Other"})
    other_floor = store.create_floor(
        "hotel-b", {"building_id": other_building["building_id"], "name": "Ground"}
    )
    other_map = store.save_floor_map(
        "hotel-b",
        other_floor["floor_id"],
        {
            "filename": "other.svg",
            "content_type": "image/svg+xml",
            "content_base64": base64.b64encode(SVG).decode("ascii"),
        },
    )
    with store._connect() as db:
        db.execute(
            "UPDATE floor_maps SET storage_path=? WHERE property_id=? AND map_id=?",
            (other_map["storage_path"], "hotel-a", store.overview("hotel-a")["maps"][0]["map_id"]),
        )

    with pytest.raises(ValueError, match="outside its property upload directory"):
        store.create_map_revision("hotel-a")


def test_map_revision_migration_is_idempotent_and_follows_country_migration():
    country_migration = importlib.import_module("migrations.versions.20261015_0001_property_country")
    migration = importlib.import_module("migrations.versions.20261015_0002_map_revisions")
    assert migration.down_revision == country_migration.revision == "20261015_0001"

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        key_columns = {
            "buildings": "building_id",
            "floors": "floor_id",
            "zones": "zone_id",
            "facilities": "facility_id",
            "access_points": "access_point_id",
            "navigation_nodes": "node_id",
        }
        for table, key in key_columns.items():
            connection.execute(text(
                f"CREATE TABLE {table} ({key} TEXT PRIMARY KEY, property_id TEXT NOT NULL)"
            ))
        connection.execute(text(
            "CREATE TABLE floor_maps (map_id TEXT PRIMARY KEY, property_id TEXT NOT NULL, created_at BIGINT NOT NULL)"
        ))
        connection.execute(text(
            """CREATE TABLE navigation_edges (
                edge_id TEXT PRIMARY KEY, property_id TEXT NOT NULL, from_node_id TEXT NOT NULL,
                to_node_id TEXT NOT NULL, distance REAL NOT NULL, bidirectional INTEGER NOT NULL,
                guest_visible INTEGER NOT NULL, created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL
            )"""
        ))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            migration.upgrade()

        inspector = inspect(connection)
        assert {"map_revisions", "map_revision_publications"} <= set(inspector.get_table_names())
        assert "ix_map_revisions_property_number" in {
            index["name"] for index in inspector.get_indexes("map_revisions")
        }
        assert {"transition_type", "accessible"} <= {
            column["name"] for column in inspector.get_columns("navigation_edges")
        }
        assert "created_at_us" in {
            column["name"] for column in inspector.get_columns("floor_maps")
        }
    engine.dispose()


def test_admin_publish_api_controls_guest_map_and_route_reads(admin_client, tmp_path, monkeypatch):
    store = ZoneStore(tmp_path / "published-api.db")
    monkeypatch.setattr(main_module, "zones", store)
    property_id = "test-property"
    building = store.create_building(property_id, {"name": "Published Hotel"})
    floor = store.create_floor(property_id, {"building_id": building["building_id"], "name": "Lobby"})
    zone = store.upsert_zone(property_id, {
        "floor_id": floor["floor_id"], "name": "Guest Lobby",
        "geometry": {"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10},
    })
    start = store.create_node(property_id, {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Entrance", "x": 1, "y": 1,
    })
    destination = store.create_node(property_id, {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Pool", "x": 8, "y": 8,
    })
    store.create_edge(property_id, {
        "from_node_id": start["node_id"], "to_node_id": destination["node_id"], "distance": 7,
        "guest_visible": True,
    })

    before = admin_client.get("/api/guest/zones", params={"property_id": property_id})
    assert before.status_code == 200, before.text
    assert before.json()["navigation_nodes"] == []

    draft = admin_client.post(f"/api/admin/properties/{property_id}/map-revisions")
    assert draft.status_code == 200, draft.text
    preview = admin_client.get(
        f"/api/admin/properties/{property_id}/map-revisions/{draft.json()['revision_id']}/preview"
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"]["counts"]["navigation_nodes"] == 2
    published = admin_client.post(
        f"/api/admin/properties/{property_id}/map-revisions/{draft.json()['revision_id']}/publish",
        json={"expected_current_revision_id": None},
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    visible = admin_client.get("/api/guest/zones", params={"property_id": property_id})
    assert visible.status_code == 200, visible.text
    assert {node["label"] for node in visible.json()["navigation_nodes"]} == {"Entrance", "Pool"}
    route = admin_client.get("/api/guest/navigation/route", params={
        "property_id": property_id, "from_node_id": start["node_id"], "to_node_id": destination["node_id"],
    })
    assert route.status_code == 200, route.text
    assert route.json()["labels"] == ["Entrance", "Pool"]

    store.update_node(property_id, destination["node_id"], {
        "floor_id": floor["floor_id"], "zone_id": zone["zone_id"], "label": "Private Service Room",
    })
    still_published = admin_client.get("/api/guest/zones", params={"property_id": property_id})
    assert {node["label"] for node in still_published.json()["navigation_nodes"]} == {"Entrance", "Pool"}

    revised = admin_client.post(f"/api/admin/properties/{property_id}/map-revisions")
    current_id = published.json()["revision_id"]
    revised_publish = admin_client.post(
        f"/api/admin/properties/{property_id}/map-revisions/{revised.json()['revision_id']}/publish",
        json={"expected_current_revision_id": current_id},
    )
    assert revised_publish.status_code == 200, revised_publish.text
    updated_guest_view = admin_client.get("/api/guest/zones", params={"property_id": property_id})
    assert "Private Service Room" in {node["label"] for node in updated_guest_view.json()["navigation_nodes"]}

    rollback = admin_client.post(
        f"/api/admin/properties/{property_id}/map-revisions/{current_id}/restore",
        json={"expected_current_revision_id": revised_publish.json()["revision_id"]},
    )
    assert rollback.status_code == 200, rollback.text
    restored_guest_view = admin_client.get("/api/guest/zones", params={"property_id": property_id})
    assert "Pool" in {node["label"] for node in restored_guest_view.json()["navigation_nodes"]}
    assert "Private Service Room" not in {node["label"] for node in restored_guest_view.json()["navigation_nodes"]}
