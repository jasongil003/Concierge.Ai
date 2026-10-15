"""Add property-scoped map revision and publication metadata.

Revision ID: 20261015_0002
Revises: 20261015_0001
"""

import hashlib
import json
import time
import uuid

from alembic import op
import sqlalchemy as sa


revision = "20261015_0002"
down_revision = "20261015_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "navigation_edges" not in tables or "floor_maps" not in tables:
        raise RuntimeError("Map tables must exist before adding publication metadata.")
    edge_columns = {column["name"] for column in inspector.get_columns("navigation_edges")}
    if "transition_type" not in edge_columns:
        op.add_column("navigation_edges", sa.Column("transition_type", sa.Text(), nullable=False, server_default=sa.text("'path'")))
    if "accessible" not in edge_columns:
        op.add_column("navigation_edges", sa.Column("accessible", sa.Integer(), nullable=False, server_default=sa.text("0")))
    map_columns = {column["name"] for column in inspector.get_columns("floor_maps")}
    if "created_at_us" not in map_columns:
        op.add_column("floor_maps", sa.Column("created_at_us", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    bind.execute(sa.text(
        "UPDATE floor_maps SET created_at_us=CAST(created_at AS BIGINT)*1000000 "
        "WHERE created_at_us=0 AND created_at>0"
    ))

    if "map_revisions" not in tables:
        op.create_table(
            "map_revisions",
            sa.Column("revision_id", sa.Text(), primary_key=True),
            sa.Column("property_id", sa.Text(), nullable=False),
            sa.Column("revision_number", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("revision_kind", sa.Text(), nullable=False, server_default=sa.text("'snapshot'")),
            sa.Column("snapshot_json", sa.Text(), nullable=False),
            sa.Column("snapshot_sha256", sa.Text(), nullable=False),
            sa.Column("preview_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("created_by", sa.Text()),
            sa.Column("published_at", sa.BigInteger()),
            sa.Column("published_by", sa.Text()),
            sa.Column("restored_from_revision_id", sa.Text()),
            sa.Column("rollback_backup_revision_id", sa.Text()),
            sa.UniqueConstraint("property_id", "revision_number", name="uq_map_revisions_property_number"),
        )
    if "map_revision_publications" not in tables:
        op.create_table(
            "map_revision_publications",
            sa.Column("property_id", sa.Text(), primary_key=True),
            sa.Column("revision_id", sa.Text(), nullable=False),
            sa.Column("published_at", sa.BigInteger(), nullable=False),
            sa.Column("published_by", sa.Text()),
        )

    inspector = sa.inspect(bind)
    if "map_revisions" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("map_revisions")}
        if "ix_map_revisions_property_number" not in indexes:
            op.create_index(
                "ix_map_revisions_property_number",
                "map_revisions",
                ["property_id", "revision_number"],
            )

    _publish_existing_maps(bind)


def _publish_existing_maps(bind) -> None:
    """Preserve maps already in service as each property's initial publication."""
    table_keys = {
        "buildings": "building_id",
        "floors": "floor_id",
        "floor_maps": "map_id",
        "zones": "zone_id",
        "facilities": "facility_id",
        "access_points": "access_point_id",
        "navigation_nodes": "node_id",
        "navigation_edges": "edge_id",
    }
    property_sql = " UNION ".join(
        f"SELECT property_id FROM {table}" for table in table_keys
    )
    property_ids = [row[0] for row in bind.execute(sa.text(property_sql))]
    now = int(time.time())
    for property_id in property_ids:
        current = bind.execute(
            sa.text("SELECT revision_id FROM map_revision_publications WHERE property_id=:property_id"),
            {"property_id": property_id},
        ).first()
        if current:
            continue
        snapshot_tables = {}
        for table, key in table_keys.items():
            rows = bind.execute(
                sa.text(f"SELECT * FROM {table} WHERE property_id=:property_id ORDER BY {key}"),
                {"property_id": property_id},
            ).mappings().all()
            snapshot_tables[table] = [dict(row) for row in rows]
        snapshot = {"format": 1, "property_id": property_id, "tables": snapshot_tables}
        snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        revision_id = "maprev_legacy_" + uuid.uuid4().hex
        revision_number = bind.execute(
            sa.text("SELECT COALESCE(MAX(revision_number),0)+1 FROM map_revisions WHERE property_id=:property_id"),
            {"property_id": property_id},
        ).scalar_one()
        buildings = {item["building_id"]: item["name"] for item in snapshot_tables["buildings"]}
        zones = {item["zone_id"]: item for item in snapshot_tables["zones"]}
        zones_by_floor = {}
        for item in snapshot_tables["zones"]:
            zones_by_floor[item["floor_id"]] = zones_by_floor.get(item["floor_id"], 0) + 1
        maps_by_floor = {}
        for item in snapshot_tables["floor_maps"]:
            maps_by_floor[item["floor_id"]] = maps_by_floor.get(item["floor_id"], 0) + 1
        facilities_by_floor = {}
        for item in snapshot_tables["facilities"]:
            zone = zones.get(item["zone_id"])
            if zone:
                floor_id = zone["floor_id"]
                facilities_by_floor[floor_id] = facilities_by_floor.get(floor_id, 0) + 1
        preview = {
            "counts": {table: len(snapshot_tables[table]) for table in table_keys},
            "floors": [
                {
                    "floor_id": floor["floor_id"],
                    "name": floor["name"],
                    "building_name": buildings.get(floor["building_id"], ""),
                    "zone_count": zones_by_floor.get(floor["floor_id"], 0),
                    "facility_count": facilities_by_floor.get(floor["floor_id"], 0),
                    "floor_plan_count": maps_by_floor.get(floor["floor_id"], 0),
                }
                for floor in snapshot_tables["floors"]
            ],
        }
        bind.execute(
            sa.text("""INSERT INTO map_revisions
                (revision_id,property_id,revision_number,status,revision_kind,snapshot_json,snapshot_sha256,
                 preview_json,created_at,published_at)
                VALUES (:revision_id,:property_id,:revision_number,'published','snapshot',:snapshot_json,
                        :snapshot_sha256,:preview_json,:now,:now)"""),
            {
                "revision_id": revision_id,
                "property_id": property_id,
                "revision_number": revision_number,
                "snapshot_json": snapshot_json,
                "snapshot_sha256": digest,
                "preview_json": json.dumps(preview, sort_keys=True, separators=(",", ":")),
                "now": now,
            },
        )
        bind.execute(
            sa.text("""INSERT INTO map_revision_publications
                (property_id,revision_id,published_at,published_by)
                VALUES (:property_id,:revision_id,:now,NULL)"""),
            {"property_id": property_id, "revision_id": revision_id, "now": now},
        )


def downgrade() -> None:
    # Published pointers and immutable rollback history are retained so a
    # downgrade cannot silently discard operational map history.
    raise RuntimeError("Map revision history is forward-only to preserve audit data.")
