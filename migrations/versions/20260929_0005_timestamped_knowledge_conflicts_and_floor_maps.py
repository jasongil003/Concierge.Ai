"""Use timestamps instead of UUID ordering for knowledge conflicts and floor maps.

Revision ID: 20260929_0005
Revises: 20260928_0004
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0005"
down_revision = "20260928_0004"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_name in sa.inspect(op.get_bind()).get_table_names() and column.name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    # The initial PostgreSQL baseline is generated from current store schemas.
    # Fresh databases may already have these fields, while installations at
    # 20260928_0004 need them added in place.
    _add_column_if_missing(
        "km_conflicts",
        sa.Column("created_at", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "km_conflicts",
        sa.Column("created_at_us", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "floor_maps",
        sa.Column("created_at_us", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )

    if {"created_at", "created_at_us"} <= _columns("km_conflicts") and "created_at" in _columns("km_items"):
        op.execute(
            """UPDATE km_conflicts SET created_at=COALESCE(
                 (SELECT MAX(i.created_at) FROM km_items i
                  WHERE i.property_id=km_conflicts.property_id
                    AND i.item_id IN (km_conflicts.item_a,km_conflicts.item_b)),
                 resolved_at,0)
               WHERE created_at=0"""
        )
        op.execute(
            "UPDATE km_conflicts SET created_at_us=CAST(created_at AS BIGINT)*1000000 "
            "WHERE created_at_us=0 AND created_at>0"
        )

    if "created_at_us" in _columns("floor_maps"):
        op.execute(
            "UPDATE floor_maps SET created_at_us=CAST(created_at AS BIGINT)*1000000 "
            "WHERE created_at_us=0 AND created_at>0"
        )


def downgrade() -> None:
    if "created_at_us" in _columns("floor_maps"):
        op.drop_column("floor_maps", "created_at_us")
    if "created_at_us" in _columns("km_conflicts"):
        op.drop_column("km_conflicts", "created_at_us")
    if "created_at" in _columns("km_conflicts"):
        op.drop_column("km_conflicts", "created_at")
