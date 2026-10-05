"""Repair legacy property identity fields and complete the property schema.

Revision ID: 20261005_0001
Revises: 20260930_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_0001"
down_revision = "20260930_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "properties" not in inspector.get_table_names():
        raise RuntimeError("The properties table is required before property integrity migration.")

    columns = {column["name"]: column for column in inspector.get_columns("properties")}
    if "hotel_name" not in columns or "property_id" not in columns:
        raise RuntimeError("The properties table is missing its identity columns.")

    if "brand_assets" not in columns:
        op.add_column(
            "properties",
            sa.Column("brand_assets", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        )
    bind.execute(
        sa.text(
            "UPDATE properties SET hotel_name = property_id "
            "WHERE hotel_name IS NULL OR TRIM(hotel_name) = ''"
        )
    )
    bind.execute(sa.text("UPDATE properties SET brand_assets = '{}' WHERE brand_assets IS NULL"))

    if bind.dialect.name == "postgresql":
        inspector = sa.inspect(bind)
        refreshed = {column["name"]: column for column in inspector.get_columns("properties")}
        if refreshed["hotel_name"]["nullable"]:
            op.alter_column(
                "properties",
                "hotel_name",
                existing_type=sa.Text(),
                nullable=False,
            )
        brand_assets = refreshed["brand_assets"]
        if brand_assets["nullable"] or brand_assets.get("default") is None:
            op.alter_column(
                "properties",
                "brand_assets",
                existing_type=sa.Text(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )


def downgrade() -> None:
    # This forward repair backfills live property rows and may add a column
    # containing user-managed brand assets. Removing that state is destructive.
    raise RuntimeError("Property identity and brand asset repairs are forward-only.")
