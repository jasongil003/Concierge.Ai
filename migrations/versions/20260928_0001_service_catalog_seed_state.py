"""Track one-time initialization of starter service catalogs.

Revision ID: 20260928_0001
Revises: 20260926_0002
"""

from alembic import op


revision = "20260928_0001"
down_revision = "20260926_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS service_catalog_seed_state ("
        "property_id TEXT PRIMARY KEY, initialized_at BIGINT NOT NULL)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_catalog_seed_state")
