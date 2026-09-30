"""Remove obsolete starter-catalog seed tracking metadata.

Revision ID: 20260930_0001
Revises: 20260929_0006
"""

from alembic import op


revision = "20260930_0001"
down_revision = "20260929_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This table only recorded whether automatic demo seeding had run. Catalog
    # rows are deliberately untouched so administrator data is preserved.
    op.execute("DROP TABLE IF EXISTS service_catalog_seed_state")


def downgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS service_catalog_seed_state ("
        "property_id TEXT PRIMARY KEY, initialized_at BIGINT NOT NULL)"
    )
