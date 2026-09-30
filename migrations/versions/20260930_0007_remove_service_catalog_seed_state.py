"""Remove the retired automatic starter service catalog seed state.

Revision ID: 20260930_0007
Revises: 20260929_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260930_0007"
down_revision = "20260929_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "service_catalog_seed_state" in inspector.get_table_names():
        op.drop_table("service_catalog_seed_state")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "service_catalog_seed_state" not in inspector.get_table_names():
        op.create_table(
            "service_catalog_seed_state",
            sa.Column("property_id", sa.Text(), primary_key=True),
            sa.Column("initialized_at", sa.BigInteger(), nullable=False),
        )
