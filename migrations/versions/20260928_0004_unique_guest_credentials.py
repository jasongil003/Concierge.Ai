"""Ensure a browser credential pair can belong to only one guest session.

Revision ID: 20260928_0004
Revises: 20260928_0003
"""

from alembic import op


revision = "20260928_0004"
down_revision = "20260928_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The previous release could store one browser credential pair on several
    # sessions. Revoke each duplicated token before adding the uniqueness rule.
    op.execute(
        "UPDATE sessions SET guest_token_hash=NULL, guest_context_hash=NULL, "
        "guest_token_expires_at=NULL, guest_token_revoked_at=COALESCE(guest_token_revoked_at,0) "
        "WHERE guest_token_hash IN ("
        "SELECT guest_token_hash FROM sessions WHERE guest_token_hash IS NOT NULL "
        "GROUP BY guest_token_hash HAVING COUNT(*) > 1)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sessions_guest_token_hash "
        "ON sessions(guest_token_hash) WHERE guest_token_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sessions_guest_token_hash")
