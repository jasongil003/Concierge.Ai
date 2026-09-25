"""Create the PostgreSQL baseline schema for Concierge.AI.

Revision ID: 20260926_0001
Revises:
Create Date: 2026-09-26
"""

from alembic import op

from app.schema_bootstrap import create_baseline_schema


revision = "20260926_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_baseline_schema(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("The initial production schema baseline cannot be downgraded; restore a verified backup instead.")
