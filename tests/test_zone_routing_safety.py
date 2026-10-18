import math
import sqlite3

import pytest

from app.zones import ZoneStore


def _route_fixture(tmp_path):
    zones = ZoneStore(tmp_path / "zones.db")
    building = zones.create_building("hotel-a", {"name": "Main"})
    floor = zones.create_floor(
        "hotel-a", {"building_id": building["building_id"], "name": "Ground"}
    )
    start = zones.create_node(
        "hotel-a", {"floor_id": floor["floor_id"], "label": "Lobby", "x": 10, "y": 10}
    )
    end = zones.create_node(
        "hotel-a", {"floor_id": floor["floor_id"], "label": "Pool", "x": 20, "y": 20}
    )
    return zones, start, end


@pytest.mark.parametrize("distance", [0, -1, math.nan, math.inf, -math.inf])
def test_create_edge_rejects_non_positive_or_non_finite_weights(tmp_path, distance):
    zones, start, end = _route_fixture(tmp_path)

    with pytest.raises(ValueError, match="finite number greater than zero"):
        zones.create_edge(
            "hotel-a",
            {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": distance},
        )


@pytest.mark.parametrize("distance", [0, -1, math.nan, math.inf, -math.inf])
def test_update_edge_rejects_non_positive_or_non_finite_weights(tmp_path, distance):
    zones, start, end = _route_fixture(tmp_path)
    edge = zones.create_edge(
        "hotel-a",
        {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 2},
    )

    with pytest.raises(ValueError, match="finite number greater than zero"):
        zones.update_edge("hotel-a", edge["edge_id"], {"distance": distance})


@pytest.mark.parametrize("distance", [-1, "nan", "inf", "not-a-number"])
def test_route_fails_closed_on_invalid_stored_legacy_weights(tmp_path, distance):
    zones, start, end = _route_fixture(tmp_path)
    edge = zones.create_edge(
        "hotel-a",
        {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 2},
    )
    with zones._connect() as db:
        db.execute(
            "UPDATE navigation_edges SET distance=? WHERE property_id=? AND edge_id=?",
            (distance, "hotel-a", edge["edge_id"]),
        )

    with pytest.raises(ValueError, match="invalid route distance"):
        zones.route("hotel-a", start["node_id"], end["node_id"], guest=False)


def test_route_preserves_valid_positive_distances(tmp_path):
    zones, start, end = _route_fixture(tmp_path)
    zones.create_edge(
        "hotel-a",
        {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 12.5},
    )

    route = zones.route("hotel-a", start["node_id"], end["node_id"], guest=False)

    assert route["labels"] == ["Lobby", "Pool"]
    assert route["distance"] == 12.5


def test_map_validation_reports_missing_and_disconnected_guest_routes(tmp_path):
    zones, start, end = _route_fixture(tmp_path)
    third = zones.create_node(
        "hotel-a",
        {"floor_id": start["floor_id"], "label": "Restaurant", "x": 40, "y": 40},
    )
    zones.create_edge("hotel-a", {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 2})

    validation = zones.validate_map("hotel-a")
    codes = {issue["code"] for issue in validation["issues"]}
    assert validation["status"] == "review"
    assert "floor_map_missing" in codes
    assert "routes_disconnected" in codes

    zones.create_edge("hotel-a", {"from_node_id": end["node_id"], "to_node_id": third["node_id"], "distance": 4})
    connected = zones.validate_map("hotel-a")
    assert "routes_disconnected" not in {issue["code"] for issue in connected["issues"]}


def test_existing_path_edges_are_not_assumed_accessible(tmp_path):
    zones, start, end = _route_fixture(tmp_path)
    zones.create_edge(
        "hotel-a",
        {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 12.5},
    )

    with pytest.raises(ValueError, match="No route exists"):
        zones.route("hotel-a", start["node_id"], end["node_id"], accessible=True, guest=False)


def test_edge_update_can_explicitly_mark_a_path_accessible(tmp_path):
    zones, start, end = _route_fixture(tmp_path)
    edge = zones.create_edge(
        "hotel-a",
        {"from_node_id": start["node_id"], "to_node_id": end["node_id"], "distance": 2},
    )

    updated = zones.update_edge(
        "hotel-a",
        edge["edge_id"],
        {"distance": 2, "accessible": True},
    )

    assert updated["accessible"] is True
    assert zones.route("hotel-a", start["node_id"], end["node_id"], accessible=True, guest=False)["labels"] == [
        "Lobby", "Pool"
    ]


def test_route_rejects_distance_overflow_in_a_valid_weight_graph(tmp_path):
    zones, start, end = _route_fixture(tmp_path)
    middle = zones.create_node(
        "hotel-a", {"floor_id": start["floor_id"], "label": "Hall", "x": 15, "y": 15}
    )
    zones.create_edge(
        "hotel-a",
        {"from_node_id": start["node_id"], "to_node_id": middle["node_id"], "distance": 1e308},
    )
    zones.create_edge(
        "hotel-a",
        {"from_node_id": middle["node_id"], "to_node_id": end["node_id"], "distance": 1e308},
    )

    with pytest.raises(ValueError, match="distance overflowed"):
        zones.route("hotel-a", start["node_id"], end["node_id"], guest=False)


def _multi_floor_fixture(tmp_path):
    zones = ZoneStore(tmp_path / "multi-floor.db")
    building = zones.create_building("hotel-a", {"name": "Main"})
    ground = zones.create_floor(
        "hotel-a", {"building_id": building["building_id"], "name": "Ground", "level": 0}
    )
    upper = zones.create_floor(
        "hotel-a", {"building_id": building["building_id"], "name": "Second", "level": 2}
    )
    lobby = zones.create_node(
        "hotel-a", {"floor_id": ground["floor_id"], "label": "Lobby", "x": 10, "y": 10}
    )
    stair_ground = zones.create_node(
        "hotel-a", {"floor_id": ground["floor_id"], "label": "Stair Ground", "x": 20, "y": 20}
    )
    stair_upper = zones.create_node(
        "hotel-a", {"floor_id": upper["floor_id"], "label": "Stair Second", "x": 20, "y": 20}
    )
    lift_ground = zones.create_node(
        "hotel-a", {"floor_id": ground["floor_id"], "label": "Elevator Ground", "x": 30, "y": 30}
    )
    lift_upper = zones.create_node(
        "hotel-a", {"floor_id": upper["floor_id"], "label": "Elevator Second", "x": 30, "y": 30}
    )
    pool = zones.create_node(
        "hotel-a", {"floor_id": upper["floor_id"], "label": "Pool", "x": 40, "y": 40}
    )
    zones.create_edge("hotel-a", {"from_node_id": lobby["node_id"], "to_node_id": stair_ground["node_id"], "distance": 1})
    zones.create_edge(
        "hotel-a",
        {
            "from_node_id": stair_ground["node_id"], "to_node_id": stair_upper["node_id"],
            "distance": 2, "transition_type": "stairs",
        },
    )
    zones.create_edge("hotel-a", {"from_node_id": stair_upper["node_id"], "to_node_id": pool["node_id"], "distance": 1})
    zones.create_edge(
        "hotel-a",
        {
            "from_node_id": lobby["node_id"], "to_node_id": lift_ground["node_id"],
            "distance": 2, "accessible": True,
        },
    )
    zones.create_edge(
        "hotel-a",
        {
            "from_node_id": lift_ground["node_id"], "to_node_id": lift_upper["node_id"],
            "distance": 1, "transition_type": "elevator", "accessible": True,
        },
    )
    zones.create_edge(
        "hotel-a",
        {
            "from_node_id": lift_upper["node_id"], "to_node_id": pool["node_id"],
            "distance": 2, "accessible": True,
        },
    )
    return zones, ground, upper, lobby, pool, stair_ground, stair_upper, lift_ground, lift_upper


def test_cross_floor_route_reports_floor_steps_and_explicit_transitions(tmp_path):
    zones, ground, upper, lobby, pool, *_rest = _multi_floor_fixture(tmp_path)

    route = zones.route("hotel-a", lobby["node_id"], pool["node_id"], guest=False)

    assert route["floor_ids"] == [ground["floor_id"], upper["floor_id"]]
    assert [step["floor_label"] for step in route["steps"]] == [
        "Ground", "Ground", "Second", "Second"
    ]
    assert any(
        transition["type"] == "stairs"
        and transition["from_floor_id"] != transition["to_floor_id"]
        for transition in route["transitions"]
    )
    assert route["distance"] == 4


def test_accessible_route_uses_explicitly_accessible_elevator_edges(tmp_path):
    zones, ground, upper, lobby, pool, _stair_ground, _stair_upper, lift_ground, lift_upper = _multi_floor_fixture(tmp_path)

    route = zones.route("hotel-a", lobby["node_id"], pool["node_id"], accessible=True, guest=False)

    assert route["accessible"] is True
    assert route["floor_ids"] == [ground["floor_id"], upper["floor_id"]]
    assert lift_ground["node_id"] in route["node_ids"]
    assert lift_upper["node_id"] in route["node_ids"]
    assert all(transition["accessible"] for transition in route["transitions"])
    assert any(transition["type"] == "elevator" for transition in route["transitions"])
    assert pool["node_id"] == route["node_ids"][-1]


def test_legacy_cross_floor_edges_are_not_treated_as_verified_transitions(tmp_path):
    zones, _ground, _upper, lobby, pool, *_rest = _multi_floor_fixture(tmp_path)
    with zones._connect() as db:
        db.execute("DELETE FROM navigation_edges WHERE property_id=?", ("hotel-a",))
        db.execute(
            """INSERT INTO navigation_edges
            (edge_id,property_id,from_node_id,to_node_id,distance,bidirectional,guest_visible,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            ("legacy-cross-floor", "hotel-a", lobby["node_id"], pool["node_id"], 1, 1, 1, 1, 1),
        )

    with pytest.raises(ValueError, match="No route exists"):
        zones.route("hotel-a", lobby["node_id"], pool["node_id"], guest=False)


def test_route_requires_explicit_transition_and_rejects_false_accessibility(tmp_path):
    zones, _ground, _upper, lobby, pool, stair_ground, _stair_upper, *_rest = _multi_floor_fixture(tmp_path)
    other_building = zones.create_building("hotel-a", {"name": "Annex"})
    other_floor = zones.create_floor(
        "hotel-a", {"building_id": other_building["building_id"], "name": "Annex Ground"}
    )
    annex = zones.create_node(
        "hotel-a", {"floor_id": other_floor["floor_id"], "label": "Annex Lobby"}
    )

    with pytest.raises(ValueError, match="explicit elevator, stairs, or ramp"):
        zones.create_edge(
            "hotel-a",
            {"from_node_id": lobby["node_id"], "to_node_id": pool["node_id"], "distance": 1},
        )
    with pytest.raises(ValueError, match="cannot be marked accessible"):
        zones.create_edge(
            "hotel-a",
            {
                "from_node_id": stair_ground["node_id"], "to_node_id": pool["node_id"],
                "distance": 1, "transition_type": "stairs", "accessible": True,
            },
        )
    with pytest.raises(ValueError, match="Cross-building"):
        zones.create_edge(
            "hotel-a",
            {
                "from_node_id": lobby["node_id"], "to_node_id": annex["node_id"],
                "distance": 1, "transition_type": "elevator",
            },
        )


def test_edge_accessibility_schema_migration_is_repeatable_and_defaults_closed(tmp_path):
    database = tmp_path / "legacy-zones.db"
    with sqlite3.connect(database) as db:
        db.execute(
            """CREATE TABLE navigation_edges (
                edge_id TEXT PRIMARY KEY, property_id TEXT NOT NULL,
                from_node_id TEXT NOT NULL, to_node_id TEXT NOT NULL,
                distance REAL NOT NULL DEFAULT 1,
                bidirectional INTEGER NOT NULL DEFAULT 1,
                guest_visible INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            )"""
        )

    zones = ZoneStore(database)
    zones = ZoneStore(database)
    with zones._connect() as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(navigation_edges)")}

    assert {"transition_type", "accessible"} <= columns
