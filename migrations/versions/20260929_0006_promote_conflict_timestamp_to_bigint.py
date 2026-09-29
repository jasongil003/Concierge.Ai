"""Promote deployed PostgreSQL conflict timestamps to BIGINT.

Revision ID: 20260929_0006
Revises: 20260929_0005
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0006"
down_revision = "20260929_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    if "km_conflicts" not in inspector.get_table_names():
        return
    columns = inspector.get_columns("km_conflicts")
    created_at = next((column for column in columns if column["name"] == "created_at"), None)
    if created_at is not None and not isinstance(created_at["type"], sa.BigInteger):
        # Existing rows are cast by PostgreSQL in place, preserving their values.
        op.alter_column(
            "km_conflicts",
            "created_at",
            existing_type=created_at["type"],
            type_=sa.BigInteger(),
        )


def downgrade() -> None:
    # Keep the widened type: narrowing could truncate timestamps from newer rows.
    pass
