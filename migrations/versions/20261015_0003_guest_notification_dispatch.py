"""Add durable guest notification preferences and dispatch state.

Revision ID: 20261015_0003
Revises: 20261015_0002
"""

from alembic import op
import sqlalchemy as sa


revision = "20261015_0003"
down_revision = "20261015_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "guest_notification_preferences" not in tables:
        op.create_table(
            "guest_notification_preferences",
            sa.Column("property_id", sa.Text(), nullable=False),
            sa.Column("stay_id", sa.Text(), nullable=False),
            sa.Column("category", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("property_id", "stay_id", "category"),
            sa.CheckConstraint(
                "category IN ('operational','assistance','experience','promotional')",
                name="ck_guest_notification_preferences_category",
            ),
            sa.CheckConstraint("enabled IN (0,1)", name="ck_guest_notification_preferences_enabled"),
        )

    if "guest_inbox_notifications" not in tables:
        op.create_table(
            "guest_inbox_notifications",
            sa.Column("notification_id", sa.Text(), primary_key=True),
            sa.Column("property_id", sa.Text(), nullable=False),
            sa.Column("stay_id", sa.Text(), nullable=False),
            sa.Column("event_id", sa.Text(), nullable=False),
            sa.Column("category", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.Column("sent_at", sa.BigInteger()),
            sa.Column("delivered_at", sa.BigInteger()),
            sa.Column("read_at", sa.BigInteger()),
            sa.Column("failed_at", sa.BigInteger()),
            sa.Column("expired_at", sa.BigInteger()),
            sa.Column("failure_reason", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("expires_at", sa.BigInteger()),
            sa.Column("dispatch_status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("next_attempt_at", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("claim_token", sa.Text()),
            sa.Column("claimed_at", sa.BigInteger()),
            sa.Column("dead_letter_at", sa.BigInteger()),
            sa.Column("scheduled_at", sa.BigInteger()),
            sa.Column("timezone_name", sa.Text(), nullable=False, server_default=sa.text("'UTC'")),
            sa.Column("quiet_hours", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("send_window", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("max_per_window", sa.Integer()),
            sa.Column("frequency_window_seconds", sa.Integer()),
            sa.UniqueConstraint("property_id", "stay_id", "event_id", name="uq_guest_inbox_scope_event"),
            sa.CheckConstraint(
                "category IN ('operational','assistance','experience','promotional')",
                name="ck_guest_inbox_notifications_category",
            ),
            sa.CheckConstraint(
                "status IN ('queued','sent','delivered','read','failed','expired')",
                name="ck_guest_inbox_notifications_status",
            ),
        )

    # Upgrade is also safe for deployments that already created a partial
    # notification table through an earlier application release.
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("guest_inbox_notifications")}
    dispatch_columns = (
        ("dispatch_status", sa.Text(), False, "'queued'"),
        ("attempt_count", sa.Integer(), False, "0"),
        ("next_attempt_at", sa.BigInteger(), False, "0"),
        ("claim_token", sa.Text(), True, None),
        ("claimed_at", sa.BigInteger(), True, None),
        ("dead_letter_at", sa.BigInteger(), True, None),
        ("scheduled_at", sa.BigInteger(), True, None),
        ("timezone_name", sa.Text(), False, "'UTC'"),
        ("quiet_hours", sa.Text(), False, "'{}'"),
        ("send_window", sa.Text(), False, "'{}'"),
        ("max_per_window", sa.Integer(), True, None),
        ("frequency_window_seconds", sa.Integer(), True, None),
    )
    for name, column_type, nullable, default in dispatch_columns:
        if name in existing_columns:
            continue
        options = {"nullable": nullable}
        if default is not None:
            options["server_default"] = sa.text(default)
        op.add_column("guest_inbox_notifications", sa.Column(name, column_type, **options))

    if "guest_notification_frequency_locks" not in tables:
        op.create_table(
            "guest_notification_frequency_locks",
            sa.Column("property_id", sa.Text(), nullable=False),
            sa.Column("stay_id", sa.Text(), nullable=False),
            sa.Column("category", sa.Text(), nullable=False),
            sa.Column("touched_at", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("property_id", "stay_id", "category"),
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("guest_inbox_notifications")}
    for name, columns in (
        ("idx_guest_inbox_scope_created", ["property_id", "stay_id", "created_at"]),
        ("idx_guest_inbox_expiry", ["status", "expires_at"]),
        ("idx_guest_inbox_dispatch_due", ["dispatch_status", "next_attempt_at", "created_at"]),
        ("idx_guest_inbox_dispatch_frequency", ["property_id", "stay_id", "category", "dispatch_status", "claimed_at", "sent_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "guest_inbox_notifications", columns)


def downgrade() -> None:
    # Queued and acknowledged guest messages form an audit trail.
    raise RuntimeError("Guest notification dispatch history is forward-only to preserve delivery records.")
