from dataclasses import dataclass
from typing import Any

from .config import settings


@dataclass
class AuthResult:
    status: str
    message: str
    handoff: dict[str, Any] | None = None


class AntlabsAdapter:
    """
    Prototype adapter.

    In mock mode, authentication is simulated locally.

    In browser_handoff mode, the backend returns an HTML-form handoff definition.
    The guest browser submits the form to the SG5 authentication URL. This preserves
    the client-side captive-portal context instead of making the login request from
    the Concierge server's IP.

    Exact ANTlabs SG5 login fields MUST be validated on a real gateway before this
    mode is used in production.
    """

    def authenticate(
        self,
        room: str,
        last_name: str,
        concierge_session_id: str,
        gateway_context: dict[str, Any],
    ) -> AuthResult:
        if settings.antlabs_mode == "mock":
            if not room.strip() or not last_name.strip():
                return AuthResult("failed", "Room and last name are required.")
            return AuthResult(
                "authenticated",
                "Prototype authentication successful. Internet access is simulated in mock mode.",
            )

        if settings.antlabs_mode != "browser_handoff":
            return AuthResult(
                "failed",
                f"Unsupported ANTlabs mode: {settings.antlabs_mode}",
            )

        if not settings.antlabs_auth_url:
            return AuthResult(
                "failed",
                "ANTLABS_AUTH_URL is not configured.",
            )

        fields: dict[str, str] = {
            settings.antlabs_room_field: room,
            settings.antlabs_last_name_field: last_name,
        }

        if settings.antlabs_session_field and settings.antlabs_session_context_key:
            gateway_session_value = gateway_context.get(settings.antlabs_session_context_key)
            if gateway_session_value is None:
                return AuthResult(
                    "failed",
                    "Required ANTlabs gateway session context is missing.",
                )
            fields[settings.antlabs_session_field] = str(gateway_session_value)
        for key in settings.antlabs_passthrough_fields:
            value = gateway_context.get(key)
            if value is not None:
                fields[key] = str(value)

        return AuthResult(
            "handoff_required",
            "Submitting authentication to the ANTlabs gateway.",
            handoff={
                "method": settings.antlabs_auth_method,
                "url": settings.antlabs_auth_url,
                "fields": fields,
            },
        )
