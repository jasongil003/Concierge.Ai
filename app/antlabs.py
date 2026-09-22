from dataclasses import dataclass
import time
from typing import Any

import httpx

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

    def configuration_status(self) -> dict[str, Any]:
        configured = settings.antlabs_mode == "mock" or bool(settings.antlabs_auth_url)
        return {
            "mode": settings.antlabs_mode,
            "configured": configured,
            "status": "simulation" if settings.antlabs_mode == "mock" else ("configured" if configured else "not_configured"),
            "endpoint": settings.antlabs_auth_url.split("?", 1)[0] if settings.antlabs_auth_url else "",
        }

    async def test_connection(self) -> dict[str, Any]:
        base = self.configuration_status()
        if settings.antlabs_mode == "mock":
            return {**base, "ok": True, "status": "simulation", "latency_ms": 0, "detail": "Mock mode is active; no gateway request was sent."}
        if settings.antlabs_mode != "browser_handoff":
            return {**base, "ok": False, "status": "unsupported_mode", "detail": "The configured ANTlabs mode is not supported."}
        if not settings.antlabs_auth_url:
            return {**base, "ok": False, "status": "not_configured", "detail": "ANTLABS_AUTH_URL is not configured."}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                response = await client.options(settings.antlabs_auth_url)
        except httpx.TimeoutException:
            return {**base, "ok": False, "status": "unreachable", "detail": "The gateway timed out."}
        except httpx.HTTPError as exc:
            return {**base, "ok": False, "status": "unreachable", "detail": f"Gateway request failed: {exc.__class__.__name__}."}
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code in {401, 403}:
            return {**base, "ok": False, "status": "authentication_failure", "latency_ms": latency, "detail": "The gateway is reachable but rejected the connection check."}
        if response.status_code >= 500:
            return {**base, "ok": False, "status": "unreachable", "latency_ms": latency, "detail": f"Gateway returned HTTP {response.status_code}."}
        return {**base, "ok": True, "status": "connected", "latency_ms": latency, "detail": f"Gateway responded with HTTP {response.status_code}."}
