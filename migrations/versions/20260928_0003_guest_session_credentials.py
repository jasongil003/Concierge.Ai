"""Add hashed browser credentials for guest sessions.

Revision ID: 20260928_0003
Revises: 20260928_0002
"""

from alembic import op


revision = "20260928_0003"
down_revision = "20260928_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS guest_token_hash TEXT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS guest_context_hash TEXT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS guest_token_expires_at BIGINT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS guest_token_revoked_at BIGINT")
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS antlabs_session_id TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_guest_token ON sessions(guest_token_hash) "
        "WHERE guest_token_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_guest_token")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS antlabs_session_id")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS guest_token_revoked_at")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS guest_token_expires_at")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS guest_context_hash")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS guest_token_hash")
