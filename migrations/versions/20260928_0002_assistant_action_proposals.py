"""Add expiring, single-use Admin AI action proposals.

Revision ID: 20260928_0002
Revises: 20260928_0001
"""

from alembic import op


revision = "20260928_0002"
down_revision = "20260928_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS assistant_action_proposals ("
        "proposal_id TEXT PRIMARY KEY,"
        "property_id TEXT NOT NULL,"
        "user_id TEXT NOT NULL,"
        "role_slug TEXT NOT NULL,"
        "conversation_id TEXT NOT NULL,"
        "action_name TEXT NOT NULL,"
        "parameters_json TEXT NOT NULL,"
        "current_json TEXT NOT NULL,"
        "proposed_json TEXT NOT NULL,"
        "impact TEXT NOT NULL,"
        "permission_used TEXT NOT NULL,"
        "risk_level TEXT NOT NULL,"
        "confirmation_requirement TEXT NOT NULL,"
        "request_id TEXT NOT NULL,"
        "status TEXT NOT NULL,"
        "result_json TEXT NOT NULL DEFAULT '{}',"
        "created_at BIGINT NOT NULL,"
        "expires_at BIGINT NOT NULL,"
        "confirmed_at BIGINT)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_assistant_action_proposals_owner "
        "ON assistant_action_proposals(user_id,property_id,status,expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS assistant_action_proposals")
