"""Add a single country field to each property profile.

Revision ID: 20261015_0001
Revises: 20261005_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20261015_0001"
down_revision = "20261005_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "properties" not in inspector.get_table_names():
        raise RuntimeError("The properties table is required before adding country metadata.")
    columns = {column["name"] for column in inspector.get_columns("properties")}
    if "country" not in columns:
        op.add_column(
            "properties",
            sa.Column("country", sa.Text(), nullable=False, server_default=sa.text("''")),
        )


def downgrade() -> None:
    # Property owners may have entered location data after this migration.
    # Keep the additive field and require a forward corrective migration.
    raise RuntimeError("Property country metadata is forward-only to preserve customer data.")
