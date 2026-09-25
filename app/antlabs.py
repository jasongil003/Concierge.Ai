from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
        auth_type: str,
        credentials: dict[str, str],
        concierge_session_id: str,
        gateway_context: dict[str, Any],
    ) -> AuthResult:
        if auth_type not in {
            "complimentary", "local", "radius", "pms", "credit_card",
            "access_code", "global_account", "global_code", "user_form",
            "social_network",
        }:
            return AuthResult("failed", "Unsupported authentication method.")

        credentials = {str(key): str(value).strip() for key, value in credentials.items()}
        required_fields = {
            "complimentary": [],
            "local": ["username", "password"],
            "radius": ["username", "password"],
            "pms": ["room", "last_name"],
            "credit_card": [],
            "access_code": ["access_code"],
            "global_account": ["username", "password"],
            "global_code": ["global_code"],
            "user_form": ["name", "email"],
            "social_network": ["social_provider"],
        }[auth_type]
        if any(not credentials.get(name) for name in required_fields):
            return AuthResult("failed", "Complete the required fields and try again.")

        if settings.antlabs_mode == "mock":
            return AuthResult(
                "authenticated",
                "Demo authentication accepted. Internet access is simulated in mock mode.",
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

        auth_url = settings.antlabs_auth_url
        fields: dict[str, str] = {}

        if auth_type == "pms":
            fields.update({
                "p": "pms",
                settings.antlabs_room_field: credentials.get("room", ""),
                settings.antlabs_last_name_field: credentials.get("last_name", ""),
            })
        elif auth_type == "complimentary":
            fields["p"] = "complimentary"
            for key in ("code", "plan", "plan_name"):
                if credentials.get(key):
                    fields[key] = credentials[key]
        elif auth_type == "local":
            fields.update({"p": "local", "uid": credentials.get("username", ""), "pwd": credentials.get("password", "")})
        elif auth_type == "access_code":
            fields.update({"p": "code", "code": credentials.get("access_code", "")})
        elif auth_type == "credit_card":
            # Card entry remains on the gateway's configured secure payment page.
            parsed = urlsplit(auth_url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query["c"] = "cc"
            auth_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
            if credentials.get("plan"):
                fields["plan_name"] = credentials["plan"]
        elif auth_type == "radius":
            fields.update({"action": "auth_login", "type": "radius", "userid": credentials.get("username", ""), "password": credentials.get("password", "")})
        elif auth_type == "global_account":
            fields.update({"action": "auth_login", "type": "acs", "userid": credentials.get("username", ""), "password": credentials.get("password", "")})
        elif auth_type == "global_code":
            fields.update({"action": "auth_login", "type": "acs", "code": credentials.get("global_code", "")})
        elif auth_type == "user_form":
            fields.update({"action": "user_form", "name": credentials.get("name", ""), "email": credentials.get("email", "")})
        elif auth_type == "social_network":
            fields.update({"action": "social", "app": credentials.get("social_provider", "")})

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
            "Continue to the ANTlabs gateway to complete authentication.",
            handoff={
                "method": settings.antlabs_auth_method,
                "url": auth_url,
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
