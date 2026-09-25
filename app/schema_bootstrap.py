"""One-time PostgreSQL baseline used only by Alembic revision 20260926_0001.

The stores still contain their original SQLite-first schema declarations. This
bridge applies those declarations once inside the migration transaction while
runtime PostgreSQL connections reject DDL unless Alembic has enabled it.
Future schema changes must be represented by a new Alembic revision.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection

from .database import bind_migration_connection, migration_schema_mode


def create_baseline_schema(connection: Connection) -> None:
    from .admin_auth import AdminAuthStore
    from .admin_copilot import AdminCopilotStore
    from .ai_providers import AIProviderStore
    from .config import settings
    from .guest_identity import GuestIdentityStore
    from .hospitality import HospitalityStore
    from .improvement_loop import ImprovementLoopStore
    from .intro import IntroExperienceStore
    from .knowledge_management import KnowledgeStore
    from .location_analytics import LocationAnalyticsStore
    from .observability import ObservabilityStore
    from .operations import OperationsStore
    from .personalization import PersonalizationStore
    from .properties import PropertyStore
    from .session_store import SessionStore
    from .zones import ZoneStore
    from .guardrails import SecurityAuditLogger

    path = settings.db_path
    with migration_schema_mode(), bind_migration_connection(connection):
        PropertyStore(path)
        SessionStore(path, settings.session_ttl_minutes)
        ZoneStore(path)
        GuestIdentityStore(path)
        PersonalizationStore(path)
        LocationAnalyticsStore(path)
        IntroExperienceStore(path)
        HospitalityStore(path)
        AIProviderStore(path)
        ImprovementLoopStore(path)
        AdminCopilotStore(path)
        AdminAuthStore(
            path,
            session_ttl_minutes=settings.admin_session_ttl_minutes,
            lockout_attempts=settings.admin_lockout_attempts,
            lockout_minutes=settings.admin_lockout_minutes,
        )
        OperationsStore(path)
        KnowledgeStore(path, settings.upload_root)
        ObservabilityStore(path)
        SecurityAuditLogger(path)
