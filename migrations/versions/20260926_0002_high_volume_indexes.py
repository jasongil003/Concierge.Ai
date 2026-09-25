"""Add indexes for high-volume tenant, request, conversation, and audit reads.

Revision ID: 20260926_0002
Revises: 20260926_0001
"""

from alembic import op


revision = "20260926_0002"
down_revision = "20260926_0001"
branch_labels = None
depends_on = None


INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sessions_property_created ON sessions(property_id,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_property_last_seen ON sessions(property_id,last_seen_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auth_attempts_property_session_time ON authentication_attempts(property_id,session_id,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_messages_property_session_time ON conversation_messages(property_id,session_id,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_state_property_state_time ON conversation_state(property_id,state,updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_admin_users_property_role_status ON admin_users(property_id,role_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_user_restaurants_user_property ON user_restaurants(user_id,property_id,restaurant_id)",
    "CREATE INDEX IF NOT EXISTS idx_service_requests_property_status_created ON service_requests(property_id,status,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_service_requests_property_department_state ON service_requests(property_id,department,status,updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_service_requests_property_stay_time ON service_requests(property_id,stay_id,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_service_request_history_property_request_time ON service_request_history(property_id,request_id,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_journey_events_property_time ON guest_journey_events(property_id,occurred_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_property_time ON guest_feedback(property_id,created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_security_events_property_time ON security_events(property_id,timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_gateway_nonces_property_expiry ON gateway_assertion_nonces(property_id,expires_at)",
)


def upgrade() -> None:
    for statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    for name in (
        "idx_sessions_property_created",
        "idx_sessions_property_last_seen",
        "idx_auth_attempts_property_session_time",
        "idx_messages_property_session_time",
        "idx_conversation_state_property_state_time",
        "idx_admin_users_property_role_status",
        "idx_user_restaurants_user_property",
        "idx_service_requests_property_status_created",
        "idx_service_requests_property_department_state",
        "idx_service_requests_property_stay_time",
        "idx_service_request_history_property_request_time",
        "idx_journey_events_property_time",
        "idx_feedback_property_time",
        "idx_security_events_property_time",
        "idx_gateway_nonces_property_expiry",
    ):
        op.execute(f"DROP INDEX IF EXISTS {name}")
