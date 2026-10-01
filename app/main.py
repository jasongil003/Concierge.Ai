from contextlib import asynccontextmanager
import asyncio
import base64
import binascii
import hashlib
import hmac
import inspect
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import smtplib
import socket
import sqlite3
import ssl
import time
import uuid
from typing import Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from urllib.parse import quote, urlparse, urlsplit

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST

from .admin_auth import (
    PERMISSIONS,
    SESSION_COOKIE,
    AccountLockedError,
    AdminAuthStore,
    AdminPrincipal,
    AuthenticationError,
)
from .ai_providers import AIModelService, AIProviderStore
from .antlabs import AntlabsAdapter
from .config import settings
from .database import configure_database, database_ready, dispose_database, verify_schema_current
from .improvement_loop import ImprovementLoopManager, ImprovementLoopStore
from .guest_identity import GuestIdentityStore
from .guest_context import build_guest_context
from .stay_context import StayContextEngine
from .assistant_decisions import AssistantDecisionEngine
from .guest_actions import GuestActionRegistry
from .personalization import PREFERENCE_CATEGORIES, PersonalizationStore, extract_preferences, preference_commands
from .admin_copilot import (
    ADMIN_ACTION_POLICY,
    ADMIN_KNOWLEDGE_POLICY,
    ADMIN_POLICY,
    AdminCopilotStore,
    action_planner_prompt,
    available_tools,
    parse_action_plan,
    parse_tool_plan,
    planner_prompt,
    synthesis_prompt,
)
from .admin_configuration_actions import register_admin_configuration_actions
from .configuration_actions import (
    ActionContext,
    ActionDenied,
    ActionValidationError,
    AssistantActionProposalStore,
    ConfigurationActionRegistry,
    encode_json,
)
from .guardrails import (
    AIInputSanitizer,
    AIOutputValidator,
    ActionGuard,
    GuardrailDecision,
    GuardrailDenied,
    GuestHostnameConflict,
    GatewayGuard,
    InternetGuard,
    NetworkGuard,
    PrivacyGuard,
    PropertyGuard,
    RateLimitUnavailable,
    RedisRateLimiter,
    SQLiteRateLimiter,
    SecurityAuditLogger,
    normalize_guest_access_hosts,
    normalize_guest_hostname,
    normalize_host_header,
    normalize_guardrails,
    property_guest_hostnames,
    public_guardrails,
)
from .hospitality import HospitalityStore
from .intro import IntroExperienceStore
from .location_analytics import LocationAnalyticsStore
from .operations import OperationsStore
from .knowledge_management import KnowledgeStore, CATEGORIES, parse_document, validate_file
from .network_access import (
    DEFAULT_MANAGEMENT_CIDRS,
    ManagementAccessGuard,
    detected_server_network,
    find_network_overlaps,
    normalize_cidrs,
    normalize_management_access,
    unsafe_management_networks,
)
from .observability import DiagnosticContext, DiagnosticToolRegistry, ObservabilityStore, PERIODS, period_window
from .outbound_http import OutboundRequestBroker, OutboundRequestError
from .places import GooglePlaces, format_places_for_ai, rank_places
from .properties import AUTHENTICATION_RULES, DesignRevisionConflict, PropertyRecord, PropertyStore, default_design_config, validate_design_config
from .guest_experience import COMPONENT_REGISTRY
from .reporting import ReportService
from .rbac import bind_admin_route_policies, matched_admin_policy
from .session_store import SessionStore
from .zones import ZoneStore
from . import metrics

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

configure_database(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_pre_ping=True,
    pool_use_lifo=True,
    connect_args={
        "connect_timeout": settings.db_connect_timeout_seconds,
        "options": f"-c statement_timeout={settings.db_statement_timeout_ms} -c idle_in_transaction_session_timeout=10000",
    },
)
verify_schema_current()

store = SessionStore(settings.db_path, settings.session_ttl_minutes)
properties = PropertyStore(settings.db_path)
zones = ZoneStore(settings.db_path)
guest_identities = GuestIdentityStore(settings.db_path)
personalization = PersonalizationStore(settings.db_path)
location_analytics = LocationAnalyticsStore(settings.db_path)
intro_experiences = IntroExperienceStore(settings.db_path)
hospitality = HospitalityStore(settings.db_path)
ai_provider_store = AIProviderStore(settings.db_path)
ai_models = AIModelService(ai_provider_store)
improvement_loop_store = ImprovementLoopStore(settings.db_path)
improvement_loops = ImprovementLoopManager(
    improvement_loop_store,
    ai_models,
    worker_enabled=settings.background_workers_enabled,
)
admin_copilot_store = AdminCopilotStore(settings.db_path)
assistant_action_proposals = AssistantActionProposalStore(settings.db_path)
configuration_action_registry = ConfigurationActionRegistry()
admin_auth = AdminAuthStore(
    settings.db_path,
    session_ttl_minutes=settings.admin_session_ttl_minutes,
    lockout_attempts=settings.admin_lockout_attempts,
    lockout_minutes=settings.admin_lockout_minutes,
)
admin_auth.ensure_bootstrap_admin(
    settings.admin_bootstrap_username,
    settings.admin_bootstrap_password,
)
places = GooglePlaces()
antlabs = AntlabsAdapter()
operations = OperationsStore(settings.db_path)
knowledge_management = KnowledgeStore(settings.db_path, settings.upload_root)
observability = ObservabilityStore(settings.db_path)
diagnostic_tools = DiagnosticToolRegistry()
report_service = ReportService()
network_guard = NetworkGuard()
action_guard = ActionGuard()
rate_limiter = RedisRateLimiter(settings.redis_url) if settings.redis_url else SQLiteRateLimiter(settings.db_path)
if isinstance(rate_limiter, RedisRateLimiter):
    ai_models.set_distributed_redis(rate_limiter.client)
security_audit = SecurityAuditLogger(settings.db_path)
management_access_guard = ManagementAccessGuard()


@asynccontextmanager
async def lifespan(app: FastAPI):
    personalization.cleanup_expired()
    async def process_pending_knowledge():
        while True:
            try:
                improvement_loops.resume_running()
                pending = await asyncio.to_thread(knowledge_management.pending_sources)
                for property_id, source_id in pending:
                    try:
                        await asyncio.to_thread(knowledge_management.process, property_id, source_id)
                    except Exception as exc:
                        metrics.WORKER_FAILURES.labels("knowledge_ingest").inc()
                        logger.error("Knowledge ingestion job failed (%s)", exc.__class__.__name__)
                        await asyncio.sleep(1)
            except Exception as exc:
                metrics.WORKER_FAILURES.labels("knowledge_poll").inc()
                logger.error("Knowledge queue poll failed (%s)", exc.__class__.__name__)
            await asyncio.sleep(10)
    knowledge_worker = None
    if settings.background_workers_enabled:
        improvement_loops.resume_persisted()
        knowledge_worker = asyncio.create_task(process_pending_knowledge())
    yield
    if knowledge_worker is not None:
        knowledge_worker.cancel()
        try:
            await knowledge_worker
        except asyncio.CancelledError:
            pass
    deadline = time.monotonic() + 20
    while observability.active_requests > 0 and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    if settings.background_workers_enabled:
        improvement_loops.shutdown()
    if isinstance(rate_limiter, RedisRateLimiter):
        await rate_limiter.close()
    if settings.database_url:
        await asyncio.to_thread(dispose_database)


SECURE_ENVIRONMENTS = {"production", "staging"}
GUEST_SESSION_COOKIE = "concierge_guest_session"
GUEST_CONTEXT_COOKIE = "concierge_guest_context"


def documentation_options(environment: str) -> dict[str, Any]:
    if environment in SECURE_ENVIRONMENTS:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


def _floor_map_file_response(path: Path) -> FileResponse:
    headers = {
        "Content-Security-Policy": "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
    }
    if path.suffix.casefold() == ".pdf":
        headers["Content-Disposition"] = "attachment"
    return FileResponse(path, headers=headers)


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    lifespan=lifespan,
    **documentation_options(settings.app_environment),
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(GuardrailDenied)
async def guardrail_denied_handler(request: Request, exc: GuardrailDenied) -> JSONResponse:
    del request
    return JSONResponse(exc.decision.payload(guest_safe=True), status_code=exc.status_code)


@app.exception_handler(RateLimitUnavailable)
async def rate_limit_unavailable_handler(request: Request, exc: RateLimitUnavailable) -> JSONResponse:
    del request
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(GuestHostnameConflict)
async def guest_hostname_conflict_handler(request: Request, exc: GuestHostnameConflict) -> JSONResponse:
    del request
    return JSONResponse(
        {
            "detail": {
                "code": "guest_host_conflict",
                "message": str(exc),
            }
        },
        status_code=409,
    )


def _path_property_id(path: str) -> str | None:
    match = re.match(r"^/api/admin/properties/([^/]+)", path)
    return match.group(1) if match else None


async def _rate_limit_allowed(key: str, limit: int, seconds: int) -> bool:
    decision = rate_limiter.allow(key, limit, seconds)
    return bool(await decision) if inspect.isawaitable(decision) else bool(decision)


async def _admin_rate_limited(session_id: str) -> bool:
    return not await _rate_limit_allowed(f"admin-api:{session_id}", 300, 60)


async def _chat_rate_limited(session_id: str) -> bool:
    return not await _rate_limit_allowed(f"guest-chat:{session_id}", 20, 60)


def _apply_security_headers(request: Request, response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: https:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    response.headers["X-Request-ID"] = getattr(request.state, "request_id", "")
    if settings.app_environment in SECURE_ENVIRONMENTS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request.state.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", supplied) else uuid.uuid4().hex
    response = await call_next(request)
    return _apply_security_headers(request, response)


@app.middleware("http")
async def collect_request_telemetry(request: Request, call_next):
    observability.request_started()
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        property_id = _path_property_id(request.url.path)
        observability.record_request(
            property_id,
            round((time.perf_counter() - started) * 1000, 2),
            status_code,
            observability.request_finished(),
            request.method,
            metrics.route_template(request),
        )


@app.middleware("http")
async def enforce_admin_security(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    public_admin_pages = {"/admin/login"}
    is_admin_page = path == "/admin"
    is_admin_api = path == "/api/admin" or path.startswith("/api/admin/")
    if path in public_admin_pages or not (is_admin_page or is_admin_api):
        return await call_next(request)

    policy, matched_scope = matched_admin_policy(request.app, request.scope, request.method) if is_admin_api else (None, request.scope)
    if policy and policy.authentication == "public":
        return await call_next(request)

    principal = admin_auth.authenticate(request.cookies.get(SESSION_COOKIE))
    if principal is None:
        if is_admin_page:
            return RedirectResponse("/admin/login", status_code=303)
        return JSONResponse({"detail": "Administrator authentication required."}, status_code=401)
    request.state.admin = principal

    if is_admin_api:
        if policy is None:
            return JSONResponse({"detail": "No administrator authorization policy is registered for this operation."}, status_code=403)
        request.state.admin_route_policy = policy
        if await _admin_rate_limited(principal.session_id):
            return JSONResponse({"detail": "Administrative request limit exceeded. Try again shortly."}, status_code=429)
        if principal.force_password_change and path not in {
            "/api/admin/auth/me", "/api/admin/auth/change-password", "/api/admin/auth/logout"
        }:
            return JSONResponse({"detail": "Change your temporary password before continuing."}, status_code=428)
        permission = policy.permission
        if permission and not principal.can(permission):
            return JSONResponse({"detail": f"Permission required: {permission}"}, status_code=403)
        property_id = matched_scope.get("path_params", {}).get("property_id")
        if property_id and not principal.can_access_property(property_id):
            return JSONResponse({"detail": "You do not have access to this property."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf = request.headers.get("X-CSRF-Token", "")
            if not csrf or not secrets_compare(csrf, principal.csrf_token):
                return JSONResponse({"detail": "CSRF validation failed."}, status_code=403)

    response = await call_next(request)
    if is_admin_api and request.method not in {"GET", "HEAD", "OPTIONS"} and response.status_code < 400:
        property_id = matched_scope.get("path_params", {}).get("property_id")
        admin_auth.audit(
            principal,
            f"api.{request.method.lower()}",
            "api",
            path,
            property_id=property_id,
            ip_address=request.client.host if request.client else "",
        )
    return response


def secrets_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _admin_principal(request: Request) -> AdminPrincipal:
    principal = getattr(request.state, "admin", None)
    if principal is None:
        raise HTTPException(status_code=401, detail="Administrator authentication required.")
    return principal


def _department_scope_name(principal: AdminPrincipal, property_id: str) -> str | None:
    if principal.role_slug != "department-manager":
        return None
    if not principal.department_id:
        raise HTTPException(status_code=403, detail="A department assignment is required for this operation.")
    department = hospitality.get_department(property_id, principal.department_id)
    if department is None:
        raise HTTPException(status_code=403, detail="The assigned department is not available in this property.")
    return str(department["name"])


def _require_department_request_scope(
    principal: AdminPrincipal, property_id: str, request_id: str
) -> dict[str, Any] | None:
    department_name = _department_scope_name(principal, property_id)
    if department_name is None:
        return None
    request_record = hospitality.get_service_request(property_id, request_id)
    if request_record is None:
        raise HTTPException(status_code=404, detail="Service request not found.")
    if str(request_record.get("department") or "").casefold() != department_name.casefold():
        raise HTTPException(status_code=403, detail="This account is not assigned to that department.")
    return request_record


def _require_department_service_scope(principal: AdminPrincipal, property_id: str, service_id: str) -> None:
    if principal.role_slug != "department-manager":
        return
    _department_scope_name(principal, property_id)
    service = hospitality.get_service(property_id, service_id)
    if service is None or service.get("department_id") != principal.department_id:
        raise HTTPException(status_code=403, detail="This account is not assigned to that service department.")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid.uuid4().hex)


def _outbound_broker(property_id: str, request_id: str = "system") -> OutboundRequestBroker:
    def audit(event: str, metadata: dict[str, Any]) -> None:
        security_audit.record(request_id, property_id, event, "blocked" if event.endswith("blocked") else "recorded", resource="outbound_http", metadata=metadata)

    return OutboundRequestBroker(audit=audit)


def _guest_property(request: Request, supplied_property_id: str | None = None) -> PropertyRecord:
    try:
        return PropertyGuard.resolve(
            properties.list(),
            settings.property_id,
            request.headers.get("host", ""),
            supplied_property_id,
            allow_body_selection=settings.allow_body_property_selection,
        )
    except PermissionError as exc:
        decision = GuardrailDecision(False, "The requested property is not available from this guest address.", "property_isolation", supplied_property_id, 4, False, False, _request_id(request))
        security_audit.record(decision.request_id, supplied_property_id, "property_access_violation", "denied", request.client.host if request.client else "")
        raise GuardrailDenied(decision) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Property not found.") from exc


def _enforce_guest_network(request: Request, property_record: PropertyRecord, action_level: int = 1) -> GuardrailDecision:
    direct_ip = request.client.host if request.client else ""
    if property_record.guest_configuration_malformed:
        security_audit.record(
            _request_id(request),
            property_record.property_id,
            "guest_configuration_invalid",
            "denied",
            direct_ip,
            metadata={"path": request.url.path},
        )
        decision = GuardrailDecision(
            False,
            "Guest access is unavailable while this property's network configuration is invalid.",
            "configuration_validation",
            property_record.property_id,
            action_level,
            False,
            False,
            _request_id(request),
        )
        raise GuardrailDenied(decision)
    decision = network_guard.evaluate(property_record.property_id, property_record.guardrails, direct_ip, request.headers, _request_id(request), action_level)
    request.state.guardrail_decision = decision
    if not decision.allowed:
        security_audit.record(decision.request_id, property_record.property_id, "network_access_denied", "denied", decision.client_ip, metadata={"path": request.url.path})
        raise GuardrailDenied(decision)
    if _guest_https_is_required(request):
        local_development_request = settings.app_environment not in SECURE_ENVIRONMENTS and _request_is_loopback(request)
        if request.url.scheme != "https" and not local_development_request:
            raise HTTPException(status_code=426, detail="HTTPS is required for guest access.")
    return decision


def _guest_cookie_names(session_id: str | None = None) -> tuple[str, str]:
    if session_id is None:
        # Read-only compatibility names for credentials issued before the
        # per-session cookie migration.
        if settings.app_environment in SECURE_ENVIRONMENTS:
            return "__Host-concierge_guest_session", "__Host-concierge_guest_context"
        return GUEST_SESSION_COOKIE, GUEST_CONTEXT_COOKIE
    selector = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:24]
    prefix = "__Host-concierge_guest_" if settings.app_environment in SECURE_ENVIRONMENTS else "concierge_guest_"
    return f"{prefix}{selector}_session", f"{prefix}{selector}_context"


def _set_guest_cookies(response: Response, session_id: str, token: str, context: str, ttl_seconds: int) -> None:
    secure = settings.app_environment in SECURE_ENVIRONMENTS or settings.admin_cookie_secure
    token_cookie, context_cookie = _guest_cookie_names(session_id)
    options = {
        "max_age": max(60, int(ttl_seconds)),
        "httponly": True,
        "secure": secure,
        "samesite": "strict",
        "path": "/",
    }
    # Keep both independent 256-bit credentials, but carry them in one
    # session-specific cookie. Browsers send cookies for every open guest tab
    # on each request; using two names per tab needlessly doubles header size.
    response.set_cookie(token_cookie, f"{token}.{context}", **options)
    response.delete_cookie(
        context_cookie, path="/", httponly=True, secure=secure, samesite="strict"
    )
    response.headers["Cache-Control"] = "no-store"


def _clear_legacy_guest_cookies(response: Response) -> None:
    secure = settings.app_environment in SECURE_ENVIRONMENTS or settings.admin_cookie_secure
    for cookie_name in _guest_cookie_names():
        response.delete_cookie(cookie_name, path="/", httponly=True, secure=secure, samesite="strict")


def _refresh_guest_cookie_response(request: Request, response: Response) -> Response:
    cleanup_session_id = getattr(request.state, "guest_cookie_cleanup_session_id", None)
    if cleanup_session_id and response.status_code >= 400:
        secure = settings.app_environment in SECURE_ENVIRONMENTS or settings.admin_cookie_secure
        for cookie_name in _guest_cookie_names(cleanup_session_id):
            response.delete_cookie(
                cookie_name, path="/", httponly=True, secure=secure, samesite="strict"
            )
        return response
    candidate = getattr(request.state, "guest_cookie_refresh", None)
    if not candidate or response.status_code >= 400:
        return response
    session_id, token, context, ttl_seconds, legacy = candidate
    if legacy:
        credentials = store.rotate_guest_credentials(
            session_id, token, context, ttl_seconds=ttl_seconds
        )
        if credentials is None:
            return response
        _set_guest_cookies(response, session_id, *credentials, ttl_seconds)
        _clear_legacy_guest_cookies(response)
        return response
    threshold = max(30, min(300, ttl_seconds // 3))
    if store.extend_guest_credentials_if_needed(
        session_id,
        token,
        context,
        ttl_seconds=ttl_seconds,
        refresh_threshold_seconds=threshold,
    ):
        _set_guest_cookies(response, session_id, token, context, ttl_seconds)
    return response


def _guest_session(request: Request, session_id: str | None, action_level: int = 1):
    selector = request.headers.get("X-Concierge-Session", "").strip()
    if session_id and selector and not hmac.compare_digest(session_id, selector):
        resolved_session_id = None
    else:
        resolved_session_id = session_id or selector or None
    token_cookie, context_cookie = _guest_cookie_names(resolved_session_id) if resolved_session_id else ("", "")
    token = request.cookies.get(token_cookie) if token_cookie else None
    context = request.cookies.get(context_cookie) if context_cookie else None
    if token and not context and "." in token:
        # New cookies bundle the same two independent credentials under one
        # name. Continue accepting the former pair during its remaining TTL.
        token, context = token.split(".", 1)
    legacy = False
    # Upgrade uniquely owned pre-0004 credentials after validating them against
    # this specific session. Ambiguous legacy pairs have been revoked by 0004.
    if resolved_session_id and (not token or not context):
        legacy_token_name, legacy_context_name = _guest_cookie_names()
        legacy_token = request.cookies.get(legacy_token_name)
        legacy_context = request.cookies.get(legacy_context_name)
        if store.verify_guest_credentials(resolved_session_id, legacy_token, legacy_context):
            token, context = legacy_token, legacy_context
            legacy = True
    session = store.peek(resolved_session_id) if resolved_session_id else None
    if session is None:
        if resolved_session_id and (token or context):
            request.state.guest_cookie_cleanup_session_id = resolved_session_id
        decision = GuardrailDecision(False, "Concierge session expired.", "session_validation", None, action_level, False, False, _request_id(request))
        raise GuardrailDenied(decision, status_code=401)
    if not store.verify_guest_credentials(session.session_id, token, context):
        request.state.guest_cookie_cleanup_session_id = session.session_id
        # Legacy sessions without browser credentials fail closed in every environment.
        decision = GuardrailDecision(False, "Concierge session expired.", "session_validation", None, action_level, False, False, _request_id(request))
        raise GuardrailDenied(decision, status_code=401)
    property_record = _guest_property(request, session.property_id)
    policy_config = normalize_guardrails(property_record.guardrails)
    if session.last_seen_at < int(time.time()) - int(policy_config["guest_session_timeout"]) * 60:
        store.delete(session.session_id)
        request.state.guest_cookie_cleanup_session_id = session.session_id
        decision = GuardrailDecision(False, "Concierge session expired.", "session_validation", property_record.property_id, action_level, False, False, _request_id(request))
        raise GuardrailDenied(decision, status_code=401)
    try:
        _enforce_guest_network(request, property_record, action_level)
    except GuardrailDenied:
        policy = policy_config.get("session_network_revalidation")
        if policy == "expire":
            store.delete(session.session_id)
        else:
            store.mark_network_status(session.session_id, "suspended")
        raise
    if session.network_status != "active":
        store.mark_network_status(session.session_id, "active")
    request.state.guest_cookie_refresh = (
        session.session_id,
        token,
        context,
        int(policy_config["guest_session_timeout"]) * 60,
        legacy,
    )
    refreshed = store.get(session.session_id)
    if refreshed is None or refreshed.property_id != property_record.property_id:
        decision = GuardrailDecision(False, "Concierge session expired.", "session_validation", property_record.property_id, action_level, False, False, _request_id(request))
        raise GuardrailDenied(decision, status_code=401)
    return refreshed, property_record


class StartSessionRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    property_id: str | None = None
    gateway_context: dict[str, Any] = Field(default_factory=dict)


class ResumeSessionRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)


class AuthRequest(BaseModel):
    session_id: str
    auth_type: str = Field(default="pms", min_length=1, max_length=40)
    credentials: dict[str, str] = Field(default_factory=dict)
    # Kept temporarily for older guest clients that still submit the PMS shape.
    room: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=128)


class GuestChatHistoryItem(BaseModel):
    role: str = Field(pattern=r"^(guest|assistant)$")
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    mode: str = "auto"
    conversation_history: list[GuestChatHistoryItem] = Field(default_factory=list, max_length=10)


class GuestPersonalizationPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    level: str = "stay"


class GuestPreferencePayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=160)
    preference_key: str | None = Field(default=None, max_length=100)


class PropertyPayload(BaseModel):
    property_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    hotel_name: str = Field(min_length=1, max_length=200)
    description: str = ""
    domain: str = ""
    deployment_mode: str = Field(default="on-prem", pattern=r"^(on-prem|cloud|hybrid|edge)$")
    timezone: str = "UTC"
    latitude: float | None = None
    longitude: float | None = None
    address: str = ""
    contact_details: dict[str, Any] = Field(default_factory=dict)
    logo_url: str = ""
    brand_assets: dict[str, Any] = Field(default_factory=dict)
    concierge_name: str = "Concierge"
    concierge_avatar_url: str = ""
    primary_color: str = "#171717"
    secondary_color: str = "#f4f3ef"
    background: str = ""
    languages: list[str] = Field(default_factory=lambda: ["en"])
    facilities: list[dict[str, Any]] = Field(default_factory=list)
    dining: list[dict[str, Any]] = Field(default_factory=list)
    spa: dict[str, Any] = Field(default_factory=dict)
    pool: dict[str, Any] = Field(default_factory=dict)
    gym: dict[str, Any] = Field(default_factory=dict)
    policies: list[dict[str, Any]] = Field(default_factory=list)
    support_contacts: list[dict[str, Any]] = Field(default_factory=list)
    quick_actions: list[dict[str, Any]] = Field(default_factory=list)
    ai_settings: dict[str, Any] = Field(default_factory=dict)
    antlabs_config: dict[str, Any] = Field(default_factory=dict)
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    rooms: list[dict[str, Any]] = Field(default_factory=list)
    guest_modules: list[dict[str, Any]] = Field(default_factory=list)
    personality: dict[str, Any] = Field(default_factory=dict)
    guardrails: dict[str, Any] = Field(default_factory=dict)
    app_settings: dict[str, Any] = Field(default_factory=dict)
    welcome: str = "How can I help?"

    def to_record(self) -> PropertyRecord:
        return PropertyRecord(**self.model_dump())


class ManagementAccessPayload(BaseModel):
    management_access_enabled: bool = True
    management_allowed_cidrs: list[str] = Field(default_factory=list, max_length=64)
    management_trusted_proxy_ranges: list[str] = Field(default_factory=list, max_length=64)
    confirm_unsafe: bool = False
    confirm_overlap: bool = False
    confirm_lockout: bool = False
    confirm_public_exposure: bool = False


class GuestNetworkAccessPayload(BaseModel):
    guest_access_enabled: bool = True
    guest_domain: str = Field(default="", max_length=253)
    guest_url: str = Field(default="", max_length=1000)
    guest_access_hosts: list[Any] = Field(default_factory=list, max_length=64)
    guest_https_required: bool = True
    reverse_proxy: bool = False
    guest_network_only: bool = True
    allowed_cidrs: list[str] = Field(default_factory=list, max_length=64)
    trusted_proxy_ranges: list[str] = Field(default_factory=list, max_length=64)
    session_network_revalidation: str = "suspend"
    guest_session_timeout: int = Field(default=30, ge=5, le=1440)
    antlabs_gateway_enabled: bool = False
    antlabs_gateway_ranges: list[str] = Field(default_factory=list, max_length=64)
    confirm_overlap: bool = False


class PropertyLogoPayload(BaseModel):
    logo_url: str = Field(default="", max_length=700_000)


class DesignConfigPayload(BaseModel):
    config: dict[str, Any]
    expected_revision: int | None = Field(default=None, ge=1)


class DesignPublishPayload(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)


class RestoreDesignPayload(BaseModel):
    version: int
    expected_revision: int | None = Field(default=None, ge=1)


class AISettingsPayload(BaseModel):
    default_provider: str | None = None
    organization_default_provider: str | None = None
    routing_mode: str | None = None
    local_only: bool | None = None
    fallback_chain: list[str] | None = None
    limits: dict[str, Any] | None = None


class AIProviderPayload(BaseModel):
    enabled: bool = False
    auth_method: str | None = None
    selected_model: str | None = None
    endpoint_url: str = ""
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=160, ge=1, le=32000)
    timeout_seconds: int = Field(default=45, ge=1, le=300)
    config: dict[str, Any] = Field(default_factory=dict)


class CredentialPayload(BaseModel):
    credential_type: str = Field(default="api_key", min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=8000)


class GenericPayload(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class GuardrailConfigPayload(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class UploadPayload(BaseModel):
    filename: str = Field(min_length=1, max_length=220)
    content_type: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(min_length=1)
    width: float | None = None
    height: float | None = None


class KnowledgeItemUpdatePayload(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    visibility: str | None = None
    role_slug: str | None = None
    effective_at: int | None = None
    expires_at: int | None = None


class KnowledgeDraftPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    category: str = "Other"


class ConflictResolutionPayload(BaseModel):
    winner_id: str
    note: str = ""


class GuestUploadPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=220)
    content_type: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(min_length=1, max_length=1_500_000)


class DeviceSessionPayload(BaseModel):
    raw_mac: str = Field(min_length=12, max_length=32)
    concierge_session_id: str | None = None
    antlabs_session_id: str | None = None
    browser_session_id: str | None = None
    room: str | None = None
    pms_guest_id: str | None = None
    retention_days: int = Field(default=2, ge=0, le=60)


class MemoryPayload(BaseModel):
    memory: dict[str, Any] = Field(default_factory=dict)


class ObservationPayload(BaseModel):
    raw_mac: str | None = None
    device_id: str | None = None
    stay_id: str | None = None
    access_point_identifier: str = Field(min_length=1, max_length=160)
    observed_at: int | None = None


class AnalyticsQuery(BaseModel):
    start_at: int
    end_at: int
    filters: dict[str, Any] = Field(default_factory=dict)


class ServiceStatusPayload(BaseModel):
    status: str


class GuestServiceRequestPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    service_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    room: str | None = Field(default=None, max_length=80)
    client_request_id: str | None = Field(default=None, min_length=8, max_length=120)
    confirmed: bool = False


class GuestServiceProposalPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2000)


class GuestServiceConfirmationPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    proposal_token: str = Field(min_length=20, max_length=3000)


class GuestRequestCancelPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    confirmed: bool = False


class ServiceRequestUpdatePayload(BaseModel):
    priority: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=120)
    assigned_to: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=1000)


class ConversationStatePayload(BaseModel):
    status: str = Field(pattern=r"^(open|closed|escalated)$")
    human_takeover: bool = False


class RestaurantEscalationPayload(BaseModel):
    restaurant_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=500)


class ConversationAssignPayload(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)


class ConversationRetentionPayload(BaseModel):
    retention_days: int = Field(ge=1, le=365)


class StaffReplyPayload(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class NotificationEvaluatePayload(BaseModel):
    stay_id: str | None = None
    verified_payload: dict[str, Any] = Field(default_factory=dict)
    guest_preferences: dict[str, Any] = Field(default_factory=dict)
    current_zone_id: str | None = None


class ImprovementLoopConfigPayload(BaseModel):
    objective: str = Field(default="")
    satisfaction_criteria: str = Field(default="")
    evidence: str = Field(default="")
    provider_id: str = Field(default="local")
    model: str = Field(default="")
    approval_mode: str = Field(default="manual")
    interval_seconds: int = Field(default=60)
    max_iterations: int = Field(default=0)
    max_consecutive_failures: int = Field(default=3)


class ImprovementLoopDecisionPayload(BaseModel):
    decision: str = Field(pattern=r"^(approved|revision_requested)$")
    feedback: str = Field(default="")


class AdminLoginPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember_me: bool = False


class AdminUserCreatePayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    property_id: str | None = None
    department_id: str | None = None
    role_id: str
    email: str | None = Field(default=None, max_length=254)
    status: str = Field(default="active", pattern=r"^(active|disabled|locked)$")
    force_password_change: bool = True
    restaurant_ids: list[str] = Field(default_factory=list, max_length=100)


class AdminUserUpdatePayload(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    property_id: str | None = None
    department_id: str | None = None
    role_id: str | None = None
    email: str | None = Field(default=None, max_length=254)
    status: str | None = Field(default=None, pattern=r"^(active|disabled|locked)$")
    restaurant_ids: list[str] | None = Field(default=None, max_length=100)


class AdminPasswordResetPayload(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    force_password_change: bool = True


class AdminPasswordChangePayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class AdminPasswordResetRequestPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class AdminPasswordResetConfirmPayload(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=12, max_length=256)


class AdminRolePayload(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    property_id: str | None = None
    permissions: list[str] = Field(default_factory=list)


class AssistantQueryPayload(BaseModel):
    question: str = Field(min_length=2, max_length=40000)
    intent: str = Field(default="auto", pattern=r"^(auto|report|health)$")
    period: str = Field(default="24h", pattern=r"^(1h|6h|24h|7d|30d|today|yesterday)$")
    current_page: str = Field(default="overview", max_length=80)
    conversation_id: str | None = Field(default=None, max_length=80)


class AssistantMenuImportPayload(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
    files: list[UploadPayload] = Field(min_length=1, max_length=5)
    conversation_id: str | None = Field(default=None, max_length=80)


class AssistantConversationPayload(BaseModel):
    conversation_id: str = Field(min_length=16, max_length=80)


class AssistantActionConfirmationPayload(BaseModel):
    confirmation_phrase: str | None = Field(default=None, max_length=80)


class HotelAssistantPayload(BaseModel):
    question: str | None = Field(default=None, min_length=2, max_length=1200)
    conversation_id: str | None = Field(default=None, max_length=80)
    attached_files: list[str] = Field(default_factory=list, max_length=5)


class KnowledgePayload(BaseModel):
    item_id: str | None = None
    kind: str = Field(default="entry", pattern=r"^(entry|faq)$")
    title: str = Field(default="", max_length=200)
    question: str = Field(default="", max_length=500)
    answer: str = Field(default="", max_length=12000)
    body: str = Field(default="", max_length=50000)
    enabled: bool = True


class WebhookPayload(BaseModel):
    webhook_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    endpoint_url: str = Field(min_length=1, max_length=1000)
    events: list[str] = Field(default_factory=list)
    enabled: bool = True
    secret: str = Field(default="", max_length=8000)


class EmailSettingsPayload(BaseModel):
    host: str = Field(default="", max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=8000)
    from_address: str = Field(default="", max_length=254)
    security: str = Field(default="starttls", pattern=r"^(starttls|ssl|none)$")
    enabled: bool = False


@app.get("/")
async def index(request: Request) -> Response:
    try:
        record = _guest_property(request)
        _enforce_guest_network(request, record)
    except GuardrailDenied as exc:
        return FileResponse(STATIC_DIR / "access-restricted.html", status_code=exc.status_code)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin/login")
async def admin_login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin-login.html")


@app.get("/admin")
async def admin() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return await health_ready()


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, Any]:
    checks: dict[str, str] = {
        "configuration": "healthy",
        "database": "healthy",
        "redis": "not_configured",
        "storage": "healthy",
    }
    try:
        if settings.database_url:
            await asyncio.to_thread(database_ready)
        else:
            with sqlite3.connect(settings.db_path, timeout=2) as db:
                db.execute("SELECT 1").fetchone()
    except Exception as exc:
        metrics.DATABASE_ERRORS.labels("readiness").inc()
        checks["database"] = "unavailable"
        logger.warning(
            "Database readiness probe failed",
            extra={"error_type": exc.__class__.__name__},
        )
        raise HTTPException(status_code=503, detail="Database is not ready.") from exc
    if isinstance(rate_limiter, RedisRateLimiter):
        try:
            if not await rate_limiter.ping():
                raise RateLimitUnavailable("Redis did not answer the readiness probe.")
            checks["redis"] = "healthy"
        except RateLimitUnavailable as exc:
            checks["redis"] = "unavailable"
            raise HTTPException(status_code=503, detail="Redis is not ready.") from exc
    if not settings.upload_root.is_dir() or not os.access(settings.upload_root, os.W_OK):
        checks["storage"] = "unavailable"
        raise HTTPException(status_code=503, detail="Required storage is not ready.")
    return {
        "status": "ok",
        "checks": checks,
    }


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    expected = settings.metrics_token
    supplied = request.headers.get("Authorization", "")
    if len(expected) < 32:
        raise HTTPException(status_code=404, detail="Not found.")
    if not supplied.startswith("Bearer ") or not secrets_compare(supplied[7:], expected):
        raise HTTPException(status_code=401, detail="Metrics authentication required.")
    metrics.update_process_resources()
    return Response(metrics.render_metrics(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health/details")
async def health_details(request: Request) -> dict[str, Any]:
    principal = admin_auth.authenticate(request.cookies.get(SESSION_COOKIE))
    if principal is None or not principal.can("diagnostics.view"):
        raise HTTPException(status_code=401 if principal is None else 403, detail="Administrator diagnostics permission required.")
    database = observability.database_health()
    return {
        "status": "ok" if database.get("state") == "healthy" else "degraded",
        "database": database,
        "queued_requests": observability.queue_depth,
    }


@app.get("/api/hotel")
async def hotel(request: Request) -> dict[str, Any]:
    property_record = _guest_property(request)
    _enforce_guest_network(request, property_record)
    profile = property_record.public_profile
    if settings.antlabs_mode == "browser_handoff":
        supported_authentication_types = set(antlabs.supported_authentication_types())
        profile["authentication"]["enabled_types"] = [
            item for item in profile["authentication"]["enabled_types"]
            if item["id"] in supported_authentication_types
        ]
    if not profile.get("ai"):
        profile["ai"] = {
            "guest_mode_switch": settings.ai_guest_mode_switch,
            "default_mode": settings.ai_default_mode,
            "modes": [],
        }
    profile["property_id"] = property_record.property_id
    return profile


@app.get("/api/guest/zones")
async def guest_zones(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    overview = zones.overview(record.property_id, guest=True)
    overview["maps"] = [
        {
            "map_id": item["map_id"],
            "floor_id": item["floor_id"],
            "original_filename": item["original_filename"],
            "content_type": item["content_type"],
            "width": item["width"],
            "height": item["height"],
            "url": f"/api/guest/floor-maps/{item['map_id']}/asset?property_id={quote(record.property_id, safe='')}",
        }
        for item in overview["maps"]
    ]
    return overview


@app.get("/api/guest/floor-maps/{map_id}/asset")
async def guest_floor_map_asset(request: Request, map_id: str, property_id: str | None = None) -> FileResponse:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    try:
        return _floor_map_file_response(zones.floor_map_path(record.property_id, map_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/guest/intro")
async def guest_intro(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    intro = intro_experiences.get(record.property_id)
    if intro.get("asset_url"):
        filename = Path(intro["asset_url"].split("?", 1)[0]).name
        intro["asset_url"] = f"/api/guest/intro/assets/{quote(filename, safe='')}?property_id={quote(record.property_id, safe='')}"
    return intro


@app.get("/api/guest/intro/assets/{filename}")
async def guest_intro_asset(request: Request, filename: str, property_id: str | None = None) -> FileResponse:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    try:
        return FileResponse(intro_experiences.asset_path(record.property_id, filename))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/guest/navigation/route")
async def guest_route(request: Request, from_node_id: str, to_node_id: str, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    if not normalize_guardrails(record.guardrails)["directions_enabled"]:
        raise GuardrailDenied(GuardrailDecision(False, "Directions are not enabled for this property.", "internet_access", record.property_id, 1, False, False, _request_id(request)))
    try:
        return zones.route(record.property_id, from_node_id, to_node_id, guest=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/guest/facilities")
async def guest_facilities(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    return hospitality.guest_facilities(record.property_id)


@app.get("/api/guest/restaurants/{restaurant_id}/menus")
async def guest_restaurant_menus(restaurant_id: str, request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    restaurant = hospitality.get_restaurant(record.property_id, restaurant_id, guest=True)
    if not restaurant or restaurant.get("archived") or restaurant.get("status") in {"disabled", "archived"}:
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    menus = hospitality.restaurant_menus(record.property_id, restaurant_id, guest=True)
    safe_menus = [{
        "name": menu.get("name", ""), "meal_period": menu.get("meal_period", ""),
        "items": [{key: value for key, value in item.items() if key in {"name", "description", "price", "ingredients", "allergens", "dietary_tags", "available"}} for item in menu.get("items", [])],
    } for menu in menus]
    return {"restaurant": {"name": restaurant.get("name", ""), "cuisine": restaurant.get("cuisine", "")}, "menus": safe_menus}


@app.get("/api/guest/service-catalog")
async def guest_service_catalog(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    return hospitality.catalog(record.property_id, guest=True)


@app.get("/api/guest/recommendations")
async def guest_recommendations(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    return {"recommendations": hospitality.recommendations(record.property_id, guest=True)}


@app.get("/api/guest/home")
async def guest_home(request: Request, session_id: str | None = None) -> dict[str, Any]:
    session, property_record = _guest_session(request, session_id)
    context = StayContextEngine().build(
        property_record, session, hospitality, guest_identities, personalization, store,
    )
    home = AssistantDecisionEngine().decide(context)
    memory = personalization.guest_state(session.property_id, session.session_id)
    preferred_name = next((
        item.get("value") for item in memory.get("preferences", [])
        if memory.get("enabled") and memory.get("level") == "personal" and item.get("category") == "preferred_name"
    ), None)
    home["greeting"] = context["time_context"]["greeting"]
    home["preferred_name"] = preferred_name
    home["stay"] = context["stay"]
    home["local_time"] = context["time_context"]["local_time"]
    allowed = {
        "restaurants": {"restaurant_id", "facility_id", "name", "location", "opening_hours", "meal_periods", "reservation_available", "description", "status", "cuisine", "dress_code", "external_reservation_url", "guest_notes", "images"},
        "facilities": {"facility_id", "zone_id", "building_id", "floor_id", "name", "facility_type", "opening_hours", "description", "images", "capacity", "booking_supported", "live_status", "status_note"},
        "promotions": {"promotion_id", "restaurant_id", "title", "description", "starts_at", "ends_at", "status"},
        "menu_items": {"item_id", "menu_id", "name", "description", "price", "image_url", "ingredients", "allergens", "dietary_tags", "available"},
        "recommendations": {"recommendation_id", "name", "category", "description", "address", "map_url", "opening_hours", "images"},
    }
    for category, fields in allowed.items():
        home["inventory"][category] = [
            {key: value for key, value in item.items() if key in fields}
            for item in home["inventory"].get(category, [])
        ]
    return home


@app.get("/api/guest/requests")
async def guest_requests(request: Request, session_id: str | None = None) -> dict[str, Any]:
    session, property_record = _guest_session(request, session_id)
    context = StayContextEngine().build(
        property_record, session, hospitality, guest_identities, personalization, store,
    )
    return {"requests": context["recent_requests"]}


@app.get("/api/guest/personalization")
async def get_guest_personalization(request: Request, session_id: str | None = None) -> dict[str, Any]:
    session, _ = _guest_session(request, session_id)
    return personalization.guest_state(session.property_id, session.session_id)


@app.put("/api/guest/personalization")
async def set_guest_personalization(payload: GuestPersonalizationPayload, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, payload.session_id)
    try:
        return personalization.set_guest_state(session.property_id, session.session_id, payload.enabled, payload.level)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/guest/personalization/preferences")
async def save_guest_preference(payload: GuestPreferencePayload, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, payload.session_id)
    state = personalization.guest_state(session.property_id, session.session_id)
    try:
        preference = personalization.save_preference(
            session.property_id, session.session_id, payload.category, payload.value,
            preference_key=payload.preference_key,
            source="explicit", confidence=1.0,
            persistence="profile" if state["level"] == "personal" else "stay",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"preference": preference, **personalization.guest_state(session.property_id, session.session_id)}


@app.delete("/api/guest/personalization/preferences")
async def clear_guest_preferences(request: Request, session_id: str | None = None) -> dict[str, Any]:
    session, _ = _guest_session(request, session_id)
    deleted = personalization.clear_preferences(session.property_id, session.session_id)
    return {"deleted": deleted, **personalization.guest_state(session.property_id, session.session_id)}


@app.delete("/api/guest/personalization/preferences/{preference_key}")
async def delete_guest_preference(preference_key: str, request: Request, session_id: str | None = None) -> dict[str, Any]:
    session, _ = _guest_session(request, session_id)
    deleted = personalization.delete_preference(session.property_id, session.session_id, preference_key)
    return {"deleted": deleted, **personalization.guest_state(session.property_id, session.session_id)}


@app.post("/api/guest/uploads")
async def upload_guest_document(payload: GuestUploadPayload, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, payload.session_id)
    if payload.content_type not in {"text/plain", "text/markdown", "text/csv", "application/json", "text/html"}:
        raise HTTPException(status_code=415, detail="Upload a TXT, Markdown, CSV, JSON, or HTML document.")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="Upload content is not valid base64.") from exc
    if len(content) > 1_000_000:
        raise HTTPException(status_code=413, detail="Guest uploads are limited to 1 MB.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="The uploaded document must be UTF-8 text.") from exc
    if payload.content_type == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise HTTPException(status_code=422, detail="The uploaded document is empty.")
    return {
        "status": "ready",
        "filename": payload.filename,
        "message_context": f"The guest uploaded {payload.filename}. Use this document only for this answer:\n{text[:12000]}",
    }


@app.post("/api/guest/actions/propose")
async def propose_guest_service_action(payload: GuestServiceProposalPayload, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, payload.session_id)
    registry = GuestActionRegistry()
    definition = registry.get("service_request.create")
    if not await _rate_limit_allowed(f"guest-action-propose:{session.property_id}:{session.session_id}", *definition.rate_limit):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before trying again.")
    query = payload.message.strip()
    catalog = hospitality.catalog(session.property_id, guest=True)
    service, alternatives = registry.match_service(query, catalog.get("services", []))
    if not service:
        return {"status": "ambiguous" if alternatives else "unmatched", "choices": [{"name": item.get("name"), "department": (hospitality.get_department(session.property_id, item.get("department_id")) or {}).get("name", "")} for item in alternatives]}
    department = hospitality.get_department(session.property_id, service.get("department_id")) if service.get("department_id") else None
    description = query[:1000]
    secret = guest_identities.property_secret(session.property_id)
    token = registry.make_service_proposal(secret, session.property_id, session.session_id, service, description)
    client_ip = getattr(request.state, "guardrail_decision").client_ip
    security_audit.record(
        _request_id(request), session.property_id, definition.audit_event, "recorded", client_ip,
        resource="guest_action", metadata={"action_name": definition.name, "service_name": service.get("name", "")[:120]},
    )
    return {
        "status": "proposed", "action": definition.name, "proposal_token": token,
        "confirmation_required": True,
        "card": {
            "type": "service_request", "title": service.get("name", "Service request"),
            "department": department.get("name", "") if department else "",
            "description": description,
        },
    }


@app.post("/api/guest/actions/confirm")
async def confirm_guest_service_action(payload: GuestServiceConfirmationPayload, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id, action_level=2)
    registry = GuestActionRegistry()
    definition = registry.get("service_request.create")
    if not await _rate_limit_allowed(f"guest-action-confirm:{session.property_id}:{session.session_id}", *definition.rate_limit):
        raise HTTPException(status_code=429, detail="Too many service requests. Please wait before trying again.")
    try:
        proposal = registry.read_service_proposal(
            guest_identities.property_secret(session.property_id), payload.proposal_token,
            session.property_id, session.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    service = next((item for item in hospitality.catalog(session.property_id, guest=True).get("services", []) if item.get("service_id") == proposal.get("service")), None)
    if service is None:
        security_audit.record(_request_id(request), session.property_id, "guest.action.denied", "denied", getattr(request.state, "guardrail_decision").client_ip, resource="guest_action", metadata={"action_name": definition.name, "reason": "service_unavailable"})
        raise HTTPException(status_code=409, detail="That service is no longer available.")
    decision = action_guard.decide("service_request", session.property_id, property_record.guardrails, _request_id(request), True)
    if not decision.allowed:
        security_audit.record(decision.request_id, session.property_id, "guest.action.denied", "denied", getattr(request.state, "guardrail_decision", decision).client_ip, resource="guest_action", metadata={"action_name": definition.name})
        raise GuardrailDenied(decision, status_code=409 if decision.confirmation_required else 403)
    linked_stay = guest_identities.active_stay_for_session(session.property_id, session.session_id) if session.authenticated else None
    room = linked_stay.get("room") if linked_stay and personalization.policy(session.property_id).get("allow_pms_personalization") else None
    client_request_id = "guest-action-" + hashlib.sha256(payload.proposal_token.encode()).hexdigest()[:40]
    try:
        record = hospitality.create_service_request(session.property_id, {
            "service_id": service["service_id"], "description": proposal["description"],
            "room": room, "stay_id": session.session_id, "client_request_id": client_request_id,
        })
    except ValueError as exc:
        security_audit.record(_request_id(request), session.property_id, "guest.action.failed", "failed", getattr(request.state, "guardrail_decision").client_ip, resource="guest_action", metadata={"action_name": definition.name})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    replayed = bool(record.pop("idempotent_replay", False))
    client_ip = getattr(request.state, "guardrail_decision").client_ip
    security_audit.record(
        _request_id(request), session.property_id, "guest.action.confirmed", "recorded", client_ip,
        resource="guest_action", metadata={"action_name": definition.name, "request_id": record.get("request_id")},
    )
    if not replayed:
        metrics.SERVICE_REQUESTS.labels("created").inc()
        await _dispatch_webhooks(session.property_id, "guest.request.created", {"request": record})
    return {"status": "existing" if replayed else "created", "request": record}


@app.post("/api/guest/service-requests")
async def create_guest_service_request(payload: GuestServiceRequestPayload, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id, action_level=2)
    decision = action_guard.decide("service_request", session.property_id, property_record.guardrails, _request_id(request), payload.confirmed)
    if not decision.allowed:
        security_audit.record(decision.request_id, session.property_id, "service_request_blocked", "denied", getattr(request.state, "guardrail_decision", decision).client_ip)
        raise GuardrailDenied(decision, status_code=409 if decision.confirmation_required else 403)
    if not await _rate_limit_allowed(f"service:{session.property_id}:{session.session_id}", 10, 300):
        raise HTTPException(status_code=429, detail="Too many service requests. Please wait before trying again.")
    try:
        request_record = hospitality.create_service_request(
            session.property_id,
            {
                "service_id": payload.service_id,
                "description": payload.description,
                "room": payload.room,
                "stay_id": session.session_id,
                "client_request_id": payload.client_request_id,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    replayed = bool(request_record.pop("idempotent_replay", False))
    metrics.SERVICE_REQUESTS.labels("replayed" if replayed else "created").inc()
    if not replayed:
        security_audit.record(
            _request_id(request), session.property_id, "guest.request.created", "recorded",
            getattr(request.state, "guardrail_decision").client_ip, resource="service_request",
            metadata={"request_id": request_record.get("request_id"), "service_name": request_record.get("request_type", "")},
        )
        await _dispatch_webhooks(session.property_id, "guest.request.created", {"request": request_record})
    return {"status": "existing" if replayed else "created", "request": request_record}


@app.post("/api/guest/requests/{request_id}/cancel")
async def cancel_guest_request(request_id: str, payload: GuestRequestCancelPayload, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id, action_level=2)
    decision = action_guard.decide("service_request", session.property_id, property_record.guardrails, _request_id(request), payload.confirmed)
    if not decision.allowed:
        raise GuardrailDenied(decision, status_code=409 if decision.confirmation_required else 403)
    if not await _rate_limit_allowed(f"guest-request-cancel:{session.property_id}:{session.session_id}", 10, 300):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before trying again.")
    stay_ids = {session.session_id}
    linked_stay = guest_identities.active_stay_for_session(session.property_id, session.session_id) if session.authenticated else None
    if linked_stay and linked_stay.get("stay_id"):
        stay_ids.add(str(linked_stay["stay_id"]))
    try:
        result = hospitality.cancel_guest_service_request(session.property_id, request_id, stay_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Service request not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    security_audit.record(
        _request_id(request), session.property_id, "guest.action.confirmed", "recorded",
        getattr(request.state, "guardrail_decision").client_ip, resource="guest_action",
        metadata={"action_name": "service_request.cancel", "request_id": request_id},
    )
    return {"status": "cancelled", "request": result}


@app.get("/api/guest/conversations/{session_id}/staff-messages")
async def guest_staff_messages(session_id: str, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, session_id)
    state = store.conversation_state(session_id, session.property_id)
    if not state.get("restaurant_id"):
        raise HTTPException(status_code=404, detail="Staff conversation not found.")
    return {"state": state["state"], "messages": store.staff_messages(session_id, session.property_id)}


@app.post("/api/guest/conversations/{session_id}/escalate")
async def guest_escalate_conversation(session_id: str, payload: RestaurantEscalationPayload, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, session_id, action_level=2)
    client_ip = getattr(request.state, "guardrail_decision").client_ip
    if (
        not await _rate_limit_allowed(f"restaurant-escalation:session:{session.property_id}:{session.session_id}", 5, 900)
        or not await _rate_limit_allowed(f"restaurant-escalation:ip:{client_ip}", 30, 900)
    ):
        raise HTTPException(status_code=429, detail="Too many staff requests. Please wait before requesting help again.")
    if not normalize_guardrails(property_record.guardrails)["human_escalation_enabled"]:
        raise HTTPException(status_code=403, detail="Human escalation is not enabled for this property.")
    restaurant = hospitality.get_restaurant(session.property_id, payload.restaurant_id, guest=True)
    if not restaurant or restaurant["archived"] or restaurant["status"] in {"disabled", "archived"}:
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    try:
        state = store.escalate_conversation(session_id, session.property_id, payload.restaurant_id, payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Guest session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    security_audit.record(_request_id(request), session.property_id, "conversation_escalated", "recorded", client_ip, resource="restaurant_conversation", metadata={"restaurant_id": payload.restaurant_id, "reason_category": "guest_request"})
    return {"status": state["state"], "restaurant_id": state["restaurant_id"]}


@app.post("/api/admin/auth/login")
async def admin_login(payload: AdminLoginPayload, request: Request, response: Response) -> dict[str, Any]:
    try:
        token, principal = admin_auth.login(
            payload.username,
            payload.password,
            request.client.host if request.client else "",
            request.headers.get("User-Agent", ""),
        )
    except AccountLockedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    max_age = settings.admin_session_ttl_minutes * 60 if payload.remember_me else None
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.admin_cookie_secure or settings.app_environment == "production",
        samesite="strict",
        path="/",
    )
    return {"user": principal.public_dict(), "redirect": "/admin"}


@app.post("/api/admin/auth/password-reset/request")
async def request_admin_password_reset(payload: AdminPasswordResetRequestPayload, request: Request) -> dict[str, str]:
    client_ip = request.client.host if request.client else ""
    account_key = hashlib.sha256(payload.username.strip().casefold().encode("utf-8")).hexdigest()[:16]
    ip_allowed = await _rate_limit_allowed(f"password-reset:ip:{client_ip}", 12, 3600)
    account_allowed = await _rate_limit_allowed(f"password-reset:account:{account_key}", 3, 3600)
    if not ip_allowed or not account_allowed:
        return {"message": "If recovery is configured for this account, reset instructions will be sent."}
    admin_auth.audit(
        None,
        "auth.password_reset_requested",
        "user",
        payload.username.casefold(),
        ip_address=client_ip,
    )
    smtp_config = operations.get_email_settings(include_secret=True)
    reset = admin_auth.create_password_reset(payload.username) if smtp_config.get("enabled") else None
    if reset:
        reset_url = _admin_password_reset_url(request, reset["token"])
        try:
            await asyncio.to_thread(_send_password_reset_email, smtp_config, reset, reset_url)
        except Exception:
            pass
    return {"message": "If recovery is configured for this account, reset instructions will be sent."}


@app.post("/api/admin/auth/password-reset/confirm")
async def confirm_admin_password_reset(payload: AdminPasswordResetConfirmPayload, request: Request) -> dict[str, str]:
    client_ip = request.client.host if request.client else ""
    token_key = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()[:16]
    ip_allowed = await _rate_limit_allowed(f"password-reset-confirm:ip:{client_ip}", 30, 3600)
    token_allowed = await _rate_limit_allowed(f"password-reset-confirm:token:{token_key}", 10, 3600)
    if not ip_allowed or not token_allowed:
        raise HTTPException(status_code=429, detail="Too many password reset attempts. Try again later.")
    try:
        admin_auth.consume_password_reset(payload.token, payload.new_password)
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "password_reset", "message": "Password updated. You can now sign in."}


@app.get("/api/admin/auth/me")
async def current_admin(request: Request) -> dict[str, Any]:
    return {"user": _admin_principal(request).public_dict()}


@app.post("/api/admin/auth/logout")
async def admin_logout(request: Request, response: Response) -> dict[str, str]:
    admin_auth.logout(_admin_principal(request))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@app.post("/api/admin/auth/change-password")
async def change_admin_password(payload: AdminPasswordChangePayload, request: Request) -> dict[str, str]:
    try:
        admin_auth.change_password(_admin_principal(request), payload.current_password, payload.new_password)
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "password_changed"}


@app.get("/api/admin/permissions")
async def list_admin_permissions() -> dict[str, Any]:
    return {"permissions": [{"key": key, "name": value} for key, value in PERMISSIONS.items()]}


@app.get("/api/admin/roles")
async def list_admin_roles(request: Request) -> dict[str, Any]:
    return {"roles": admin_auth.list_roles(_admin_principal(request))}


@app.post("/api/admin/roles")
async def create_admin_role(payload: AdminRolePayload, request: Request) -> dict[str, Any]:
    try:
        role = admin_auth.save_role(payload.model_dump(), _admin_principal(request))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    return {"role": role}


@app.put("/api/admin/roles/{role_id}")
async def update_admin_role(role_id: str, payload: AdminRolePayload, request: Request) -> dict[str, Any]:
    try:
        role = admin_auth.save_role(payload.model_dump(), _admin_principal(request), role_id=role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    return {"role": role}


@app.delete("/api/admin/roles/{role_id}")
async def delete_admin_role(role_id: str, request: Request) -> dict[str, str]:
    try:
        admin_auth.delete_role(role_id, _admin_principal(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=422 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    return {"status": "deleted"}


@app.get("/api/admin/users")
async def list_admin_users(request: Request) -> dict[str, Any]:
    return {"users": admin_auth.list_users(_admin_principal(request))}


@app.post("/api/admin/users")
async def create_admin_user(payload: AdminUserCreatePayload, request: Request) -> dict[str, Any]:
    try:
        user = admin_auth.create_user(payload.model_dump(), _admin_principal(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"user": user}


@app.put("/api/admin/users/{user_id}")
async def update_admin_user(user_id: str, payload: AdminUserUpdatePayload, request: Request) -> dict[str, Any]:
    try:
        user = admin_auth.update_user(user_id, payload.model_dump(exclude_none=True), _admin_principal(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"user": user}


@app.delete("/api/admin/users/{user_id}")
async def delete_admin_user(user_id: str, request: Request) -> dict[str, str]:
    try:
        admin_auth.delete_user(user_id, _admin_principal(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted"}


@app.post("/api/admin/users/{user_id}/reset-password")
async def reset_admin_user_password(user_id: str, payload: AdminPasswordResetPayload, request: Request) -> dict[str, str]:
    try:
        admin_auth.reset_password(user_id, payload.password, payload.force_password_change, _admin_principal(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "password_reset"}


@app.post("/api/admin/users/{user_id}/revoke-sessions")
async def revoke_admin_user_sessions(user_id: str, request: Request) -> dict[str, Any]:
    try:
        count = admin_auth.revoke_sessions(user_id, _admin_principal(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "sessions_revoked", "count": count}


@app.get("/api/admin/audit")
async def list_admin_audit(
    request: Request,
    username: str = "",
    property_id: str = "",
    role: str = "",
    action: str = "",
    resource: str = "",
    start_at: int | None = None,
    end_at: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    return {
        "events": admin_auth.list_audit(
            _admin_principal(request),
            {
                "username": username,
                "property_id": property_id,
                "role_name": role,
                "action": action,
                "resource": resource,
                "start_at": start_at,
                "end_at": end_at,
            },
            limit=limit,
        )
    }


@app.get("/api/admin/properties")
async def list_properties(request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    records = properties.list()
    if not principal.can("properties.all"):
        records = [record for record in records if record.property_id == principal.property_id]
    else:
        records.sort(key=lambda record: record.hotel_name.lower())
    return {"properties": [_property_admin_payload(record, principal) for record in records]}


@app.get("/api/admin/properties/{property_id}")
async def get_property(property_id: str, request: Request) -> dict[str, Any]:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return _property_admin_payload(record, _admin_principal(request))


@app.get("/api/admin/properties/{property_id}/dashboard")
async def property_dashboard(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    ai_settings = ai_provider_store.get_settings(property_id)
    ai_providers = ai_provider_store.list_connections(property_id)
    enabled = [provider for provider in ai_providers if provider.get("enabled")]
    return {
        **store.metrics(property_id),
        **hospitality.request_metrics(property_id),
        "application": {"name": settings.app_name, "version": app.version, "environment": settings.app_environment},
        "ai": {
            "default_provider": ai_settings.get("default_provider"),
            "enabled_providers": len(enabled),
            "credentialed_providers": sum(1 for provider in enabled if provider.get("credentials") or provider.get("provider_id") == "local"),
        },
        "antlabs": antlabs.configuration_status(),
        "usage": store.operational_metrics(property_id, 7),
    }


def _dashboard_profile(principal: AdminPrincipal) -> str:
    return {
        "super-admin": "platform",
        "property-administrator": "property_operations",
        "property-manager": "management",
        "department-manager": "department",
        "concierge-front-desk": "service_operations",
        "content-manager": "content_operations",
        "viewer-auditor": "read_only",
    }.get(principal.role_slug, "read_only")


def _analytics_for_principal(property_id: str, period: str, principal: AdminPrincipal, start_at: int | None = None, end_at: int | None = None) -> dict[str, Any]:
    department_id = principal.department_id if principal.role_slug == "department-manager" else None
    try:
        return observability.property_analytics(property_id, period, department_id, start_at, end_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _report_analytics_for_principal(property_id: str, period: str, principal: AdminPrincipal) -> dict[str, Any]:
    analytics = _analytics_for_principal(property_id, period, principal)
    summary = analytics["summary"]
    if principal.role_slug == "department-manager":
        summary["guests_assisted"] = None
        summary["ai_conversations"] = None
        summary["ai_resolution_rate_percent"] = None
        summary["fallback_rate_percent"] = None
        analytics["guest_auth"] = {"attempts": None, "success_rate": None, "availability": "restricted"}
    if not principal.can("guest_sessions.view"):
        summary["guests_assisted"] = None
    if not principal.can("requests.view"):
        analytics["raw_requests"] = []
    if not principal.can("analytics.view"):
        for key in ("guests_assisted", "ai_conversations", "request_change_percent"):
            summary[key] = None
        analytics["request_volume"] = []
        analytics["requests_by_department"] = []
        analytics["busiest_periods"] = []
        analytics["top_services"] = []
        analytics["top_questions"] = []
        analytics["guest_auth"] = {"attempts": None, "success_rate": None, "availability": "restricted"}
    if not principal.can("requests.view") and not principal.can("analytics.view"):
        for key in ("service_requests", "open_requests", "overdue_requests", "average_resolution_seconds", "sla_performance_percent"):
            summary[key] = None
    if not principal.can("ai.view"):
        analytics["ai"] = {
            "requests": None, "errors": None, "error_rate_percent": None,
            "average_latency_ms": None, "first_token_latency_ms": None,
            "first_token_latency_availability": "restricted", "tokens": None,
            "provider_usage": {}, "provider_model_usage": [], "request_volume": [],
            "estimated_cost": None, "availability": "restricted",
        }
    return analytics


def _component_state(states: list[str]) -> str:
    ranking = {"healthy": 0, "simulation": 0, "warning": 1, "unavailable": 2, "critical": 3}
    return max(states or ["unavailable"], key=lambda item: ranking.get(item, 2))


def _build_operations_dashboard(property_id: str, period: str, principal: AdminPrincipal, start_at: int | None = None, end_at: int | None = None) -> dict[str, Any]:
    if period not in PERIODS and period != "custom":
        raise HTTPException(status_code=422, detail="Unsupported reporting period.")
    record = _require_property_record(property_id)
    analytics_full = _analytics_for_principal(property_id, period, principal, start_at, end_at)
    summary = analytics_full["summary"]
    ai_summary = analytics_full["ai"]
    department_scoped = principal.role_slug == "department-manager"
    analytics_allowed = principal.can("analytics.view")
    requests_allowed = principal.can("requests.view")
    sessions_allowed = principal.can("guest_sessions.view")
    infrastructure_allowed = principal.can("infrastructure.view")
    ai_allowed = principal.can("ai.view")
    integrations_allowed = principal.can("integrations.view")
    audit_allowed = principal.can("audit.view")
    knowledge_allowed = principal.can("knowledge.view")
    session_metrics = {"active_guests": 0} if department_scoped else store.metrics(property_id)
    if not department_scoped:
        for metric, value, unit in (
            ("service_requests", summary["service_requests"], "request"),
            ("overdue_requests", summary["overdue_requests"], "request"),
            ("ai_errors", ai_summary["errors"], "error"),
            ("ai_latency_ms", ai_summary["average_latency_ms"], "ms"),
            ("guest_auth_success_rate", analytics_full["guest_auth"]["success_rate"], "%"),
            ("active_sessions", session_metrics.get("active_guests", 0), "session"),
        ):
            observability.record(property_id, metric, value, unit, "available" if value is not None else "unavailable", "application")

    system_metrics = observability.collect_system(property_id) if infrastructure_allowed else {
        metric: {"value": None, "unit": "", "availability": "restricted"}
        for metric in ("cpu_utilization", "memory_utilization", "disk_utilization", "network_rx_bytes", "network_tx_bytes", "application_uptime_seconds")
    }
    database = observability.database_health() if infrastructure_allowed else {
        "state": "unavailable", "latency_ms": None, "size_bytes": None,
        "evidence": "Infrastructure telemetry is not available to this role.",
    }
    ai_settings = ai_provider_store.get_settings(property_id) if ai_allowed else {}
    providers = ai_provider_store.list_connections(property_id) if ai_allowed else []
    enabled_providers = [item for item in providers if item.get("enabled")]
    configured_providers = [item for item in enabled_providers if item.get("provider_id") == "local" or item.get("credentials")]
    provider_states = []
    provider_health = []
    for provider in enabled_providers:
        last_test = provider.get("last_test") or {}
        if last_test.get("ok") is True or provider.get("provider_id") == "local":
            state = "healthy"
            evidence = "Local provider is enabled." if provider.get("provider_id") == "local" else "Most recent connection test succeeded."
        elif provider.get("status") in {"connected", "configured"}:
            state = "warning"
            evidence = "Provider is configured but has no verified successful connection test."
        else:
            state = "unavailable"
            evidence = "Provider is enabled but credentials or a verified connection are unavailable."
        provider_states.append(state)
        provider_health.append({"id": provider["provider_id"], "name": provider["name"], "state": state, "evidence": evidence, "last_test": last_test.get("tested_at")})
    ai_state = _component_state(provider_states) if enabled_providers else "unavailable"
    antlabs_status = antlabs.configuration_status() if integrations_allowed else {"mode": "restricted", "status": "restricted", "configured": False}
    antlabs_state = ("simulation" if antlabs_status["status"] == "simulation" else ("healthy" if antlabs_status["configured"] else "unavailable")) if integrations_allowed else "restricted"
    request_state = ("warning" if summary["overdue_requests"] else "healthy") if requests_allowed or analytics_allowed else "restricted"
    auth_rate = analytics_full["guest_auth"]["success_rate"] if analytics_allowed else None
    auth_state = ("unavailable" if auth_rate is None else ("warning" if auth_rate < 90 else "healthy")) if analytics_allowed else "restricted"
    knowledge_count = len(operations.list_knowledge(property_id)) if knowledge_allowed else None
    recent_errors = observability.recent_errors(property_id, period) if audit_allowed else []
    application_state = "warning" if recent_errors else "healthy"
    components = [
        {"id": "application", "name": "Application", "state": application_state, "evidence": f"The API is responding; {len(recent_errors)} recorded integration or AI error(s) were found in this period." if audit_allowed else "The admin API is responding; detailed diagnostics are restricted for this role."},
        {"id": "database", "name": "Database", "state": database["state"], "evidence": database["evidence"]},
        {"id": "ai_providers", "name": "AI providers", "state": ai_state if ai_allowed else "restricted", "evidence": f"{len(configured_providers)} of {len(enabled_providers)} enabled providers have credentials or local execution." if ai_allowed else "AI provider status is restricted for this role."},
        {"id": "antlabs", "name": "ANTlabs gateway", "state": antlabs_state, "evidence": f"Mode: {antlabs_status['mode']}; status: {antlabs_status['status']}." if integrations_allowed else "Integration status is restricted for this role."},
        {"id": "guest_auth", "name": "Guest authentication", "state": auth_state, "evidence": ("No authentication attempts in this period." if auth_rate is None else f"{auth_rate}% of attempts succeeded.") if analytics_allowed else "Guest authentication analytics are restricted for this role."},
        {"id": "request_queue", "name": "Service request queue", "state": request_state, "evidence": f"{summary['open_requests']} open; {summary['overdue_requests']} overdue." if requests_allowed or analytics_allowed else "Request queue details are restricted for this role."},
        {"id": "knowledge", "name": "Knowledge index", "state": ("healthy" if knowledge_count else "warning") if knowledge_count is not None else "restricted", "evidence": f"{knowledge_count} indexed knowledge item(s)." if knowledge_count is not None else "Knowledge status is restricted for this role."},
    ]
    overall = _component_state([item["state"] for item in components])
    analytics = {key: value for key, value in analytics_full.items() if key != "raw_requests"}
    selected_provider = next((item for item in providers if item["provider_id"] == ai_settings.get("default_provider")), None)
    if department_scoped:
        analytics["summary"]["guests_assisted"] = None
        analytics["summary"]["ai_conversations"] = None
        analytics["summary"]["ai_resolution_rate_percent"] = None
        analytics["summary"]["fallback_rate_percent"] = None
        analytics["guest_auth"] = {"attempts": None, "success_rate": None, "availability": "restricted"}
    analytics["summary"]["active_sessions"] = session_metrics.get("active_guests") if sessions_allowed and not department_scoped else None
    analytics["ai"]["selected_provider"] = ai_settings.get("default_provider") if ai_allowed else None
    analytics["ai"]["selected_model"] = selected_provider.get("selected_model") if selected_provider and ai_allowed else None
    if not analytics_allowed:
        analytics["summary"]["guests_assisted"] = None
        analytics["summary"]["ai_conversations"] = None
        analytics["summary"]["request_change_percent"] = None
        analytics["guest_auth"] = {"attempts": None, "success_rate": None, "availability": "restricted"}
        analytics["request_volume"] = []
        analytics["requests_by_department"] = []
        analytics["busiest_periods"] = []
        analytics["top_services"] = []
        analytics["top_questions"] = []
        analytics["ai"]["request_volume"] = []
    if not requests_allowed and not analytics_allowed:
        for key in ("service_requests", "open_requests", "overdue_requests", "average_resolution_seconds", "sla_performance_percent"):
            analytics["summary"][key] = None
    if analytics["summary"]["service_requests"] == 0:
        analytics["summary"]["sla_performance_percent"] = None
    if analytics["summary"]["ai_conversations"] == 0:
        analytics["summary"]["ai_resolution_rate_percent"] = None
        analytics["summary"]["fallback_rate_percent"] = None
    if not ai_allowed:
        analytics["ai"] = {
            "requests": None, "errors": None, "error_rate_percent": None,
            "average_latency_ms": None, "first_token_latency_ms": None,
            "first_token_latency_availability": "restricted", "tokens": None,
            "provider_usage": {}, "provider_model_usage": [], "request_volume": [],
            "estimated_cost": None, "selected_provider": None, "selected_model": None,
            "availability": "restricted",
        }
    history_metrics = ("api_latency_ms", "http_errors", "request_queue_depth", "active_sessions", "service_requests", "overdue_requests", "ai_latency_ms", "ai_errors", "guest_auth_success_rate", "cpu_utilization", "memory_utilization", "disk_utilization", "network_rx_bytes", "network_tx_bytes")
    histories = (
        {metric: [] for metric in history_metrics}
        if department_scoped
        else {metric: observability.history(property_id, metric, period, start_at, end_at) for metric in history_metrics}
    )
    infrastructure_metrics = {"cpu_utilization", "memory_utilization", "disk_utilization", "network_rx_bytes", "network_tx_bytes", "request_queue_depth", "http_errors", "api_latency_ms"}
    history_availability = {metric: "available" for metric in histories}
    if department_scoped:
        history_availability = {metric: "restricted" for metric in histories}
    if not infrastructure_allowed:
        for metric in infrastructure_metrics:
            histories[metric] = []
            history_availability[metric] = "restricted"
    if not ai_allowed:
        for metric in ("ai_latency_ms", "ai_errors"):
            histories[metric] = []
            history_availability[metric] = "restricted"
    if not sessions_allowed or department_scoped:
        histories["active_sessions"] = []
        history_availability["active_sessions"] = "restricted"
    if not analytics_allowed:
        histories["guest_auth_success_rate"] = []
        history_availability["guest_auth_success_rate"] = "restricted"
    if not requests_allowed and not analytics_allowed:
        for metric in ("service_requests", "overdue_requests"):
            histories[metric] = []
            history_availability[metric] = "restricted"
    deployment = _deployment_status(record) if principal.can("domains.view") else {"availability": "restricted"}
    deliveries = operations.list_webhook_deliveries(property_id) if principal.can("integrations.view") else []
    payload_integrations = {
        "antlabs": antlabs_status,
        "external_api_connectivity": {"configured_webhooks": len(operations.list_webhooks(property_id)) if principal.can("integrations.view") else None, "failed_deliveries": sum(1 for item in deliveries if item.get("status") != "delivered") if principal.can("integrations.view") else None, "availability": "available" if principal.can("integrations.view") else "restricted"},
        "deployment": deployment,
    }
    payload = {
        "property": {"id": property_id, "name": record.hotel_name},
        "period": period,
        "profile": _dashboard_profile(principal),
        "role": {"name": principal.role_name, "slug": principal.role_slug, "department_id": principal.department_id},
        "health": {"state": overall, "components": components, "providers": provider_health},
        "system": system_metrics,
        "database": database,
        "integrations": payload_integrations,
        "analytics": analytics,
        "histories": histories,
        "history_availability": history_availability,
        "generated_at": int(time.time()),
        "data_notes": [
            "Charts contain recorded application telemetry only; missing history is shown as unavailable.",
            "Estimated AI cost is unavailable until verified billable usage and provider pricing are configured.",
        ],
    }
    allowed_alert_components = {
        *( ["request_queue"] if requests_allowed else [] ),
        *( ["ai_providers"] if ai_allowed else [] ),
        *( ["database"] if infrastructure_allowed else [] ),
    }
    evaluated_alerts = observability.evaluate_alerts(property_id, payload, allowed_alert_components)
    payload["alerts"] = [item for item in evaluated_alerts if item["component"] in allowed_alert_components]
    recommendation = next(
        (item for item in _recommendations(analytics, payload["alerts"]) if not item.startswith("No evidence-backed corrective action")),
        None,
    )
    payload["insight"] = {
        "message": recommendation,
        "source": f"Based on recorded data for {period}.",
    } if analytics_allowed and recommendation else None
    return payload


def _recommendations(analytics: dict[str, Any], alerts: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    summary = analytics["summary"]
    if summary["overdue_requests"]:
        recommendations.append(f"Review the {summary['overdue_requests']} overdue request(s) and rebalance the busiest department queue.")
    if analytics["ai"]["requests"] and analytics["ai"]["errors"]:
        recommendations.append("Review failed AI provider calls before changing routing or fallback configuration.")
    if summary["fallback_rate_percent"] is not None and summary["fallback_rate_percent"] > 10:
        recommendations.append("Review top unanswered guest questions and add verified knowledge for recurring gaps.")
    if not recommendations and not alerts:
        recommendations.append("No evidence-backed corrective action is required; continue monitoring the selected period.")
    return recommendations


@app.get("/api/admin/properties/{property_id}/operations/dashboard")
async def operations_dashboard(property_id: str, request: Request, period: str = "24h", start_at: int | None = None, end_at: int | None = None) -> dict[str, Any]:
    return _build_operations_dashboard(property_id, period, _admin_principal(request), start_at, end_at)


@app.get("/api/admin/properties/{property_id}/operations/alerts")
async def operations_alerts(property_id: str, request: Request, period: str = "24h", start_at: int | None = None, end_at: int | None = None) -> dict[str, Any]:
    dashboard = _build_operations_dashboard(property_id, period, _admin_principal(request), start_at, end_at)
    return {"period": period, "alerts": dashboard["alerts"], "generated_at": dashboard["generated_at"]}


def _diagnostic_result(
    tool: str,
    context: DiagnosticContext,
    dashboard: dict[str, Any],
    record: PropertyRecord,
    period: str,
    principal: AdminPrincipal | None = None,
) -> dict[str, Any]:
    analytics = dashboard.get("analytics", {})
    if tool == "get_system_health":
        components = dashboard["health"]["components"]
        if principal and not principal.can("dashboard.view"):
            component_permissions = {
                "application": "diagnostics.view", "database": "infrastructure.view", "ai_providers": "ai.view",
                "antlabs": "integrations.view", "guest_auth": "analytics.view", "request_queue": "requests.view",
                "knowledge": "knowledge.view",
            }
            components = [item for item in components if principal.can(component_permissions.get(item.get("id"), "dashboard.view"))]
        state = _component_state([item["state"] for item in components]) if components else "unavailable"
        return {"component": "system", "state": state, "evidence": components, "timeframe": period}
    if tool == "query_metrics":
        permitted = {key: value for key, value in dashboard["histories"].items() if dashboard["history_availability"].get(key) != "restricted"}
        return {"component": "metrics", "state": "available" if permitted else "unavailable", "evidence": permitted, "timeframe": period}
    if tool == "query_logs":
        errors = observability.recent_errors(context.property_id, period)
        return {"component": "logs", "state": "warning" if errors else "healthy", "evidence": errors, "timeframe": period}
    if tool == "get_recent_errors":
        return {"component": "errors", "state": "warning" if observability.recent_errors(context.property_id, period) else "healthy", "evidence": observability.recent_errors(context.property_id, period), "timeframe": period}
    if tool == "check_database":
        return {"component": "database", **dashboard["database"], "timeframe": "current probe"}
    if tool == "check_ai_provider":
        return {"component": "ai_providers", "state": next(item["state"] for item in dashboard["health"]["components"] if item["id"] == "ai_providers"), "evidence": dashboard["health"]["providers"], "timeframe": period}
    if tool == "check_antlabs_gateway":
        component = next(item for item in dashboard["health"]["components"] if item["id"] == "antlabs")
        return {"component": "antlabs", "state": component["state"], "evidence": component["evidence"], "timeframe": "configuration state"}
    if tool in {"check_dns", "check_ssl"}:
        deployment = _deployment_status(record)
        key = "domain" if tool == "check_dns" else "ssl"
        return {"component": key, "state": deployment[key]["status"], "evidence": deployment[key], "timeframe": deployment.get("last_checked_at") or "not yet verified"}
    if tool == "check_request_queue":
        overdue = analytics["summary"]["overdue_requests"]
        return {"component": "request_queue", "state": "warning" if overdue else "healthy", "evidence": {key: analytics["summary"][key] for key in ("service_requests", "open_requests", "overdue_requests", "sla_performance_percent")}, "likely_cause": "Open requests have passed their configured SLA due time." if overdue else None, "timeframe": period}
    if tool == "check_guest_auth":
        return {"component": "guest_auth", "state": "unavailable" if analytics["guest_auth"]["success_rate"] is None else "healthy", "evidence": analytics["guest_auth"], "timeframe": period}
    if tool == "check_knowledge_index":
        items = operations.list_knowledge(context.property_id)
        return {"component": "knowledge", "state": "healthy" if items else "warning", "evidence": {"indexed_items": len(items)}, "timeframe": "current index"}
    if tool == "compare_time_periods":
        return {"component": "operations", "state": "available", "evidence": {"current_requests": analytics["summary"]["service_requests"], "change_percent": analytics["summary"]["request_change_percent"]}, "timeframe": f"{period} versus previous {period}"}
    if tool == "analyze_business_operations":
        return {"component": "business_analytics", "state": "available", "evidence": {"summary": analytics["summary"], "departments": analytics["requests_by_department"], "top_services": analytics["top_services"], "top_questions": analytics["top_questions"], "busiest_periods": analytics["busiest_periods"]}, "timeframe": period}
    if tool == "prepare_management_report":
        summary = analytics["summary"]
        return {
            "component": "reporting",
            "state": "available",
            "evidence": {
                "scope": analytics.get("department_scope") or "Property operations",
                "formats": ["PDF", "Excel spreadsheet"],
                "summary": {
                    "guests_assisted": summary["guests_assisted"],
                    "service_requests": summary["service_requests"],
                    "open_requests": summary["open_requests"],
                    "overdue_requests": summary["overdue_requests"],
                    "average_resolution_seconds": summary["average_resolution_seconds"],
                    "sla_performance_percent": summary["sla_performance_percent"],
                    "request_change_percent": summary["request_change_percent"],
                    "guest_auth_success_percent": analytics["guest_auth"]["success_rate"],
                    "ai_requests": analytics["ai"]["requests"],
                    "ai_errors": analytics["ai"]["errors"],
                    "ai_error_rate_percent": analytics["ai"]["error_rate_percent"],
                },
                "departments": analytics["requests_by_department"][:5],
                "top_services": analytics["top_services"][:5],
                "top_guest_questions": analytics["top_questions"][:5],
                "recommendations": _recommendations(analytics, dashboard.get("alerts", [])),
            },
            "timeframe": period,
        }
    if tool == "prepare_assigned_restaurant_report":
        if principal is None:
            raise PermissionError("The assigned restaurant scope is unavailable.")
        assigned_ids = _assigned_restaurant_ids(principal, context.property_id)
        start_at, end_at, _ = period_window(period)
        restaurant_reports = []
        for restaurant_id in sorted(assigned_ids):
            restaurant = hospitality.get_restaurant(context.property_id, restaurant_id)
            if restaurant is None or restaurant.get("archived"):
                continue
            metrics = hospitality.restaurant_analytics(context.property_id, restaurant_id, start_at=start_at, end_at=end_at)
            restaurant_reports.append({
                "name": restaurant["name"],
                "metrics": {key: metrics[key] for key in ("conversations", "waiting_for_staff", "human_active", "completed", "messages")},
            })
        return {
            "component": "restaurant_reporting",
            "state": "available" if restaurant_reports else "unavailable",
            "evidence": {"scope": "Assigned restaurants", "restaurants": restaurant_reports},
            "timeframe": period,
        }
    raise KeyError("Unknown diagnostic tool.")


for _tool_name, _tool_permission in {
    "get_system_health": "diagnostics.view", "query_metrics": "dashboard.view", "query_logs": "audit.view", "get_recent_errors": "audit.view",
    "check_database": "infrastructure.view", "check_ai_provider": "ai.view",
    "check_antlabs_gateway": "integrations.view", "check_dns": "domains.view", "check_ssl": "domains.view",
    "check_request_queue": "requests.view", "check_guest_auth": "analytics.view",
    "check_knowledge_index": "knowledge.view", "compare_time_periods": "analytics.view",
    "analyze_business_operations": "analytics.view", "prepare_management_report": "reports.export",
    "prepare_assigned_restaurant_report": "restaurant.analytics.view",
}.items():
    diagnostic_tools.register(_tool_name, _tool_permission, lambda context, tool=_tool_name, **kwargs: _diagnostic_result(tool, context, **kwargs))


def _choose_diagnostic_tool(question: str, tools_allowed: list[str] | None = None) -> str:
    lowered = question.casefold()
    report_candidates = (
        "prepare_management_report",
        "prepare_assigned_restaurant_report",
        "analyze_business_operations",
        "check_request_queue",
    )
    if any(word in lowered for word in ("report", "summary", "summarize", "export")):
        if tools_allowed is None:
            return report_candidates[0]
        return next((tool for tool in report_candidates if tool in tools_allowed), "")
    choices = [
        (("database", "sqlite"), "check_database"), (("provider", "model", "ai "), "check_ai_provider"),
        (("antlabs", "gateway"), "check_antlabs_gateway"), (("dns", "domain"), "check_dns"),
        (("ssl", "certificate", "https"), "check_ssl"),
        (("department", "guests asking", "guest question", "resolution time", "busiest", "most requested"), "analyze_business_operations"),
        (("queue", "request", "sla", "delay"), "check_request_queue"),
        (("guest auth", "authentication", "login"), "check_guest_auth"), (("knowledge", "index", "answer"), "check_knowledge_index"),
        (("compare", "versus", "trend"), "compare_time_periods"), (("log",), "query_logs"), (("error", "failure"), "get_recent_errors"),
        (("latency", "metric", "utilization", "uptime", "network"), "query_metrics"),
    ]
    selected = next((tool for words, tool in choices if any(word in lowered for word in words)), "get_system_health")
    if tools_allowed is None or selected in tools_allowed:
        return selected
    return ""


def _is_assistant_greeting(question: str) -> bool:
    return bool(re.fullmatch(r"\s*(hi|hello|hey|good morning|good afternoon|good evening)[!. ,]*\s*", question, re.I))


def _fallback_tools(question: str, tools_allowed: list[str]) -> list[str]:
    lowered = question.casefold()
    requested = _choose_diagnostic_tool(question, tools_allowed)
    if any(word in lowered for word in ("system", "health", "issue", "problem", "down", "check all")):
        wanted = ["get_system_health"]
        wanted.append("get_recent_errors")
        if "check_database" in tools_allowed and any(word in lowered for word in ("database", "system", "health", "issue", "problem")):
            wanted.append("check_database")
        if "check_ai_provider" in tools_allowed and any(word in lowered for word in ("ai", "assistant", "model", "system", "health", "issue")):
            wanted.append("check_ai_provider")
        return list(dict.fromkeys(tool for tool in wanted if tool in tools_allowed))[:5]
    return [requested] if requested in tools_allowed else []


def _assistant_period_label(period: str) -> str:
    return {
        "1h": "the last hour", "6h": "the last 6 hours", "24h": "the last 24 hours",
        "7d": "the last 7 days", "30d": "the last 30 days", "today": "today", "yesterday": "yesterday",
    }.get(period, period)


def _assistant_period_from_question(question: str, selected_period: str) -> str:
    lowered = question.casefold()
    if re.search(r"\byesterday\b", lowered):
        return "yesterday"
    if re.search(r"\btoday\b", lowered):
        return "today"
    if re.search(r"\b(this week|last week|past week|last 7 days|past 7 days|7 days)\b", lowered):
        return "7d"
    if re.search(r"\b(this month|last month|past month|last 30 days|past 30 days|30 days)\b", lowered):
        return "30d"
    hour_match = re.search(r"\b(?:last|past|for)\s+(\d+)\s+hours?\b", lowered)
    if hour_match:
        hours = int(hour_match.group(1))
        return "1h" if hours <= 1 else "6h" if hours <= 6 else "24h"
    day_match = re.search(r"\b(?:last|past|for)\s+(\d+)\s+days?\b", lowered)
    if day_match:
        days = int(day_match.group(1))
        return "24h" if days <= 1 else "7d" if days <= 7 else "30d"
    if re.search(r"\b(last|past)\s+hour\b", lowered):
        return "1h"
    return selected_period


def _assistant_human_label(value: str) -> str:
    labels = {
        "guests_assisted": "Guests assisted", "service_requests": "Service requests", "open_requests": "Open requests",
        "overdue_requests": "Overdue requests", "average_resolution_seconds": "Average resolution time",
        "sla_performance_percent": "SLA performance", "request_change_percent": "Change in requests",
        "guest_auth_success_percent": "Guest authentication success", "ai_requests": "AI requests",
        "ai_errors": "AI errors", "ai_error_rate_percent": "AI error rate", "indexed_items": "Indexed knowledge items",
        "waiting_for_staff": "Waiting for staff", "human_active": "In progress with staff", "completed": "Completed",
        "conversations": "Guest conversations", "messages": "Messages", "menus": "Menus", "promotions": "Promotions",
        "current_requests": "Current requests", "change_percent": "Change", "latency_ms": "Response time",
        "size_bytes": "Database size", "error_type": "Error type", "created_at": "Recorded at",
    }
    return labels.get(value, value.replace("_", " ").strip().capitalize())


def _assistant_display_value(key: str, value: Any) -> str:
    if value is None:
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if key == "created_at" and isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).astimezone().strftime("%b %d, %Y %I:%M %p")
    if isinstance(value, (int, float)):
        if "percent" in key or key.endswith("_rate"):
            return f"{value}%"
        if key.endswith("_seconds"):
            seconds = int(value)
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m" if seconds >= 3600 else f"{seconds // 60}m {seconds % 60}s"
        if key == "latency_ms":
            return f"{value} ms"
        if key == "size_bytes":
            return f"{value / (1024 * 1024):.1f} MB"
        return f"{value:,}" if isinstance(value, int) else str(value)
    return str(value)


def _assistant_evidence_items(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    hidden_keys = {"id", "property_id", "restaurant_id", "department_id", "request_id", "last_test"}

    def add(label: str, detail: Any, state: Any = None, key: str = "") -> None:
        if len(rows) >= 18 or detail is None or isinstance(detail, (dict, list)):
            return
        text = _assistant_display_value(key, detail)
        rows.append({"label": label, "detail": text[:500], "state": str(state or "")})

    def expand(prefix: str, value: Any, depth: int = 0) -> None:
        if len(rows) >= 18 or depth > 2:
            return
        if isinstance(value, list):
            for item in value[:6]:
                if isinstance(item, dict):
                    label = str(item.get("name") or item.get("title") or item.get("question") or item.get("component") or prefix)
                    state = item.get("state")
                    detail = item.get("evidence") or item.get("error_type")
                    if detail:
                        add(label, detail, state)
                    for key, child in item.items():
                        if key in hidden_keys or key in {"name", "title", "question", "component", "state", "evidence", "error_type"}:
                            continue
                        if isinstance(child, (str, int, float, bool)):
                            add(f"{label} · {_assistant_human_label(key)}", child, state, key)
                        elif isinstance(child, (dict, list)):
                            expand(f"{label} · {_assistant_human_label(key)}", child, depth + 1)
                else:
                    add(prefix, item)
        elif isinstance(value, dict):
            for key, child in value.items():
                if key in hidden_keys or key in {"state", "component", "timeframe", "name", "evidence"}:
                    continue
                label = _assistant_human_label(key)
                if isinstance(child, (dict, list)):
                    expand(label, child, depth + 1)
                else:
                    add(label, child, key=key)
        else:
            add(prefix, value)

    for item in evidence:
        result = item.get("result", {})
        component = str(result.get("component") or item.get("tool") or "Diagnostic")
        state = result.get("state")
        if state and len(rows) < 18:
            rows.append({"label": f"{component.replace('_', ' ').title()} status", "detail": "", "state": str(state)})
        expand(_assistant_human_label(component), result.get("evidence"))
    return rows


def _assistant_fallback_summary(evidence: list[dict[str, Any]], period: str, model_unavailable: bool = True) -> tuple[str, str, list[str]]:
    period_label = _assistant_period_label(period)
    results = [item.get("result", {}) for item in evidence]
    report = next((item for item in results if item.get("component") in {"reporting", "restaurant_reporting", "business_analytics"}), None)
    health = next((item for item in results if item.get("component") == "system"), None)
    errors = next((item for item in results if item.get("component") in {"errors", "logs"}), None)
    queue = next((item for item in results if item.get("component") == "request_queue"), None)
    recommendations: list[str] = []
    if report:
        report_data = report.get("evidence", {})
        if report.get("component") == "restaurant_reporting":
            restaurants = report_data.get("restaurants", [])
            if not restaurants:
                finding = "No assigned restaurant activity is available for this period."
                answer = f"I couldn't find report data for your assigned restaurants for {period_label}. Check that a restaurant is assigned to your account."
            else:
                totals = {key: sum(item.get("metrics", {}).get(key, 0) for item in restaurants) for key in ("conversations", "waiting_for_staff", "human_active", "completed", "messages")}
                finding = f"Report ready for {len(restaurants)} assigned restaurant(s)."
                parts = [f"{totals['conversations']} guest conversations", f"{totals['waiting_for_staff']} waiting for staff", f"{totals['human_active']} being handled", f"{totals['completed']} completed", f"{totals['messages']} messages"]
                restaurant_lines = [f"{item['name']}: {item['metrics']['conversations']} conversations, {item['metrics']['waiting_for_staff']} waiting, {item['metrics']['completed']} completed." for item in restaurants[:5]]
                answer = f"Restaurant activity for {period_label}: {', '.join(parts)}.\n\n" + "\n".join(restaurant_lines)
                if totals["waiting_for_staff"]:
                    recommendations.append("Review conversations waiting for staff and assign them to an available team member.")
        else:
            summary = report_data.get("summary", {})
            finding = f"Operations report ready for {period_label}."
            parts = [
                f"{summary.get('service_requests', 0)} service requests",
                f"{summary.get('open_requests', 0)} open",
                f"{summary.get('overdue_requests', 0)} overdue",
                f"{summary.get('guests_assisted', 0)} guests assisted",
            ]
            if summary.get("sla_performance_percent") is not None:
                parts.append(f"{summary['sla_performance_percent']}% SLA performance")
            if summary.get("guest_auth_success_percent") is not None:
                parts.append(f"{summary['guest_auth_success_percent']}% guest authentication success")
            if summary.get("average_resolution_seconds") is not None:
                parts.append(f"average resolution {_assistant_display_value('average_resolution_seconds', summary['average_resolution_seconds'])}")
            if summary.get("request_change_percent") is not None:
                direction = "up" if summary["request_change_percent"] > 0 else "down" if summary["request_change_percent"] < 0 else "unchanged"
                parts.append(f"requests {direction} {abs(summary['request_change_percent'])}% versus the previous period")
            if summary.get("ai_error_rate_percent"):
                parts.append(f"AI error rate {summary['ai_error_rate_percent']}%")
            answer = f"Operations report for {period_label}: {', '.join(parts)}."
            top_services = report_data.get("top_services", [])
            if top_services:
                answer += "\nMost requested: " + ", ".join(f"{item['name']} ({item['value']})" for item in top_services[:3]) + "."
            recommendations = [str(item) for item in report_data.get("recommendations", [])[:4]]
    elif queue:
        metrics = queue.get("evidence", {})
        overdue = int(metrics.get("overdue_requests", 0) or 0)
        finding = f"{'Request queue needs attention' if overdue else 'Request queue is on track'} for {period_label}."
        answer = (
            f"Request summary for {period_label}: {metrics.get('service_requests', 0)} total, "
            f"{metrics.get('open_requests', 0)} open, {overdue} overdue."
        )
        if metrics.get("sla_performance_percent") is not None:
            answer += f" SLA performance is {metrics['sla_performance_percent']}%."
        if overdue:
            recommendations.append("Review overdue requests and confirm each has an owner and an updated status.")
    elif health:
        components = health.get("evidence", []) if isinstance(health.get("evidence"), list) else []
        issues = [item for item in components if item.get("state") in {"warning", "critical"}]
        unavailable = [item for item in components if item.get("state") == "unavailable"]
        if issues:
            finding = f"{len(issues)} system component(s) need attention."
            details = [f"{item.get('name', 'Component')}: {item.get('evidence', item.get('state'))}" for item in issues[:5]]
            answer = f"I checked system health for {period_label}. The following components need attention:\n" + "\n".join(f"• {line}" for line in details)
            recommendations = [f"Open System Health and review {item.get('name', 'the affected component').lower()}." for item in issues[:3]]
        elif health.get("state") in {"critical", "warning"}:
            finding = f"System health is {health.get('state')}."
            answer = f"System health is {health.get('state')} for {period_label}, but the available checks did not identify a component detail. Review the System Health page for the latest signals."
            recommendations = ["Open System Health to review the latest component checks."]
        else:
            finding = "No active system-health warnings were found."
            answer = f"I checked the system components available to your role for {period_label}. No active warnings or critical failures were reported."
        if unavailable:
            unavailable_names = ", ".join(item.get("name", "a component") for item in unavailable[:3])
            answer += f"\nNot configured or unavailable: {unavailable_names}."
            recommendations.extend(f"Review the configuration for {item.get('name', 'the unavailable component').lower()}." for item in unavailable[:2])
        if errors:
            error_items = errors.get("evidence", [])
            if error_items:
                answer += f"\nI also found {len(error_items)} recent integration or AI error(s). See the evidence list for details."
            elif errors.get("state") == "healthy":
                answer += "\nNo recent integration or AI errors were recorded."
    else:
        result = results[0] if results else {}
        component = str(result.get("component") or "diagnostics").replace("_", " ")
        raw_evidence = result.get("evidence")
        state = str(result.get("state") or "available").replace("_", " ")
        finding = f"{component.title()} check: {state}."
        if isinstance(raw_evidence, str):
            detail = raw_evidence
        elif isinstance(raw_evidence, dict):
            detail = "; ".join(f"{_assistant_human_label(key)}: {_assistant_display_value(key, value)}" for key, value in raw_evidence.items() if not isinstance(value, (dict, list)) and key not in {"id", "property_id"})
        else:
            detail = f"{len(raw_evidence)} record(s) returned." if isinstance(raw_evidence, list) else "No additional evidence was returned."
        answer = f"I checked {component} for {period_label}. {detail}"
        if result.get("likely_cause"):
            answer += f"\nLikely cause: {result['likely_cause']}"
            recommendations.append("Review the related operational queue and confirm whether the issue is resolved.")
    if model_unavailable:
        answer = "I couldn't get a response from the configured AI model, so I used the available read-only checks to answer.\n\n" + answer
    if not recommendations:
        recommendations.append("Continue monitoring; the available checks do not indicate a corrective action.")
    return finding, answer, recommendations[:5]


def _is_configuration_request(question: str) -> bool:
    normalized = question.casefold()
    verbs = r"\b(?:create|make|generate|build|set|change|update|modify|edit|adjust|add|publish|approve|configure|replace)\b"
    targets = r"\b(?:guest landing page|landing page|guest design|design|management access|management network|management CIDRs?|guest access|guest network|guest CIDRs?|network settings|trusted prox(?:y|ies)|guest domain|ANTlabs(?: settings| gateway)?|session polic(?:y|ies)|session timeout|restaurant|menu|menus|operating hours|opening hours|hours|promotion|promotions|service catalog|facility|facilities|events?|hotel information|hotel description|property information|property description|welcome text|personality|(?:ai|openai) (?:provider|model|settings)|faq|knowledge draft)\b"
    return bool(re.search(verbs, normalized) and re.search(targets, normalized))


def _restricted_ai_action_reason(question: str, principal: AdminPrincipal) -> str | None:
    normalized = question.casefold()
    if re.search(r"\b(?:netplan|firewall(?:\s+rules?)?|shell commands?|(?:run|execute)\s+(?:a\s+)?command(?:s)?|(?:operating[- ]system|os)\s+(?:IP|DNS)|host OS IP|machine IP|database (?:records?|tables?|operations?)|SQL|backup deletion|delete (?:all )?(?:the )?backups?|encryption secrets?|encryption keys?|API keys?|password resets?|user deletion|delete (?:all )?(?:the )?(?:users?|accounts?)|Super Admin(?: role)?|RBAC privilege|make .*public|expose (?:the )?Admin publicly)\b", normalized, re.I):
        return "This security-sensitive operation cannot be performed through Admin AI. Use the supported security settings workflow or contact a platform administrator."
    if re.search(r"\bmanagement (?:access|network|CIDR|CIDRs)\b", normalized, re.I) and principal.role_slug != "super-admin":
        return "Management Access is installation-wide and is available to Super Admins only. No change was made."
    if re.search(r"\b(?:(?:ai|openai) provider|(?:ai|openai) model|provider settings)\b", normalized) and not principal.can("ai.configure"):
        return "Your account does not have permission to change AI provider settings. No change was made."
    return None


def _assistant_action_targets(principal: AdminPrincipal, property_id: str) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for restaurant_id in sorted(_assistant_assigned_restaurant_ids(principal, property_id)):
        restaurant = hospitality.get_restaurant(property_id, restaurant_id)
        if not restaurant or restaurant.get("archived") or restaurant.get("status") in {"disabled", "archived"}:
            continue
        menus = hospitality.restaurant_menus(property_id, restaurant_id)
        targets.append({
            "restaurant_id": restaurant_id,
            "name": restaurant.get("name", ""),
            "opening_hours": restaurant.get("opening_hours", {}),
            "menus": [{"menu_id": menu.get("menu_id"), "name": menu.get("name"), "meal_period": menu.get("meal_period")} for menu in menus],
        })
    return targets


def _assistant_assigned_restaurant_ids(principal: AdminPrincipal, property_id: str) -> set[str]:
    try:
        return _assigned_restaurant_ids(principal, property_id)
    except sqlite3.Error:
        if principal.can("properties.all") or principal.can("properties.edit"):
            try:
                return {item["restaurant_id"] for item in hospitality.overview(property_id).get("restaurants", [])}
            except Exception:
                return set()
        return set()


def _explicit_assistant_scope_denial(question: str, principal: AdminPrincipal, property_id: str) -> str | None:
    normalized = question.casefold()
    if re.search(r"\b(?:another|different|other) restaurant\b", normalized) and principal.role_slug == "restaurant-manager":
        return "I can only prepare restaurant changes for restaurants assigned to your account. No change was made."
    assigned_ids = _assistant_assigned_restaurant_ids(principal, property_id)
    try:
        all_restaurants = hospitality.overview(property_id).get("restaurants", [])
    except Exception:
        all_restaurants = []
    for restaurant in all_restaurants:
        name = str(restaurant.get("name") or "").strip()
        if len(name) >= 3 and name.casefold() in normalized and restaurant.get("restaurant_id") not in assigned_ids:
            return "I can only prepare restaurant changes for restaurants assigned to your account. No change was made."

    try:
        all_properties = properties.list()
    except Exception:
        all_properties = []
    for record in all_properties:
        name = str(record.hotel_name or "").strip()
        if record.property_id != property_id and len(name) >= 4 and name.casefold() in normalized:
            return "This proposal is scoped to the currently selected property. Select the intended property and try again. No change was made."
    return None


def _action_context(principal: AdminPrincipal, property_id: str, request: Request, conversation_id: str) -> ActionContext:
    configuration_action_services.update({
        "properties": properties,
        "hospitality": hospitality,
        "operations": operations,
        "knowledge_management": knowledge_management,
        "ai_provider_store": ai_provider_store,
        "require_restaurant_access": _require_restaurant_access,
        "management_access_guard": management_access_guard,
    })
    return ActionContext(principal, property_id, request, conversation_id, _request_id(request), configuration_action_services)


def _action_safe_value(value: Any, field_name: str = "") -> Any:
    if re.search(r"password|secret|credential|api.?key|token|private.?key", field_name, re.I):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(key): _action_safe_value(item, str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_action_safe_value(item, field_name) for item in value]
    if isinstance(value, str):
        text = re.sub(r"(?i)\b(api[_ -]?key|password|secret|token)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", value)
        if field_name.casefold() in {"content", "document", "raw_document"}:
            import hashlib
            return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "length": len(text)}
        return text[:6000]
    return value


def _audit_assistant_action(
    principal: AdminPrincipal,
    event: str,
    property_id: str,
    action_name: str,
    *,
    conversation_id: str,
    request_id: str,
    restaurant_id: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    permission: str | None = None,
    risk_level: str | None = None,
    confirmed_at: int | None = None,
    result: Any = None,
    error_type: str | None = None,
) -> None:
    metadata: dict[str, Any] = {
        "assistant_conversation_id": conversation_id,
        "request_id": request_id,
        "action_name": action_name,
        "role": principal.role_slug,
    }
    if restaurant_id:
        metadata["restaurant_id"] = restaurant_id
    if old_value is not None:
        metadata["old_value"] = _action_safe_value(old_value)
    if new_value is not None:
        metadata["new_value"] = _action_safe_value(new_value)
    if permission:
        metadata["permission_used"] = permission
    if risk_level:
        metadata["risk_level"] = risk_level
    if confirmed_at is not None:
        metadata["confirmation_timestamp"] = confirmed_at
    if result is not None:
        metadata["result"] = _action_safe_value(result)
    if error_type:
        metadata["error_type"] = error_type
    admin_auth.audit(principal, event, "assistant_action", action_name, property_id=property_id, ip_address="", metadata=metadata)


def _public_action_proposal(row: dict[str, Any], action: Any) -> dict[str, Any]:
    current = json.loads(row["current_json"])
    stored_proposed = json.loads(row["proposed_json"])
    proposed = stored_proposed.get("proposed", stored_proposed)
    scope: dict[str, Any] = {"property_id": row["property_id"]}
    record = properties.get(row["property_id"])
    if record:
        scope["property_name"] = record.hotel_name
    restaurant_id = stored_proposed.get("restaurant_id") or (proposed.get("restaurant_id") if isinstance(proposed, dict) else None)
    if restaurant_id:
        scope["restaurant_id"] = restaurant_id
        scope["restaurant_name"] = stored_proposed.get("restaurant_name", "")
    short_code = row["proposal_id"][:6].upper()
    if row["action_name"].startswith("network."):
        open_panel = "network-access"
    elif row["action_name"].startswith("design."):
        open_panel = "appearance"
    elif row["action_name"].startswith("ai."):
        open_panel = "ai"
    elif row["action_name"].startswith("restaurant.") or row["action_name"].startswith("menu.") or row["action_name"].startswith("promotion."):
        open_panel = "restaurants"
    elif row["action_name"].startswith("facility."):
        open_panel = "facilities"
    elif row["action_name"].startswith("service_catalog."):
        open_panel = "service-catalog"
    elif row["action_name"].startswith("faq."):
        open_panel = "faqs"
    elif row["action_name"].startswith("knowledge."):
        open_panel = "knowledge"
    elif row["action_name"].startswith("property.update_personality"):
        open_panel = "ai-personality"
    else:
        open_panel = "hotel-information"
    return {
        "proposal_id": row["proposal_id"],
        "action": row["action_name"],
        "description": action.description,
        "current": _action_safe_value(current),
        "proposed": _action_safe_value(proposed),
        "impact": row["impact"],
        "permission_used": row["permission_used"],
        "risk_level": row["risk_level"],
        "confirmation_requirement": row["confirmation_requirement"],
        "confirmation_phrase": f"APPLY {short_code}" if row["confirmation_requirement"] == "strong" else None,
        "scope": scope,
        "open_panel": open_panel,
        "expires_at": row["expires_at"],
        "status": row["status"],
    }


def _assistant_action_reply(question: str, conversation_id: str, answer: str, proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "question": question,
        "conversation_id": conversation_id,
        "answer": answer,
        "finding": "Configuration proposal" if proposal else "Configuration request",
        "component": "configuration assistant",
        "timeframe": "",
        "evidence": [],
        "evidence_items": [],
        "recommendations": [],
        "links": [{"label": "Open Settings", "panel": proposal["open_panel"]}] if proposal else [],
        "downloads": [],
        "tool_activity": [],
        "confirmation_required": bool(proposal),
        "action_status": "No change has been applied. Review and confirm this proposal." if proposal else "No changes were made.",
        "configuration_proposal": proposal,
        "request_id": proposal.get("request_id") if proposal else None,
    }


def _store_assistant_action_proposal(
    principal: AdminPrincipal,
    context: ActionContext,
    action: Any,
    parameters: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    row = assistant_action_proposals.create({
        "property_id": context.property_id,
        "user_id": principal.user_id,
        "role_slug": principal.role_slug,
        "conversation_id": context.conversation_id,
        "action_name": action.name,
        "parameters_json": encode_json(parameters),
        "current_json": encode_json(_action_safe_value(preview.get("current"))),
        "proposed_json": encode_json(_action_safe_value({key: value for key, value in preview.items() if key not in {"current", "impact", "warnings"}} | {"proposed": preview.get("proposed")})),
        "impact": str(preview.get("impact") or "Review the proposed configuration change.")[:2000],
        "permission_used": action.required_permission,
        "risk_level": action.risk_level,
        "confirmation_requirement": action.confirmation_requirement,
        "request_id": context.request_id,
    })
    proposal = _public_action_proposal(row, action)
    _audit_assistant_action(
        principal, "assistant.action.proposed", context.property_id, action.name,
        conversation_id=context.conversation_id, request_id=context.request_id,
        restaurant_id=proposal["scope"].get("restaurant_id"),
        old_value=preview.get("current"), new_value=preview.get("proposed"),
        permission=action.required_permission, risk_level=action.risk_level,
    )
    return proposal


async def _prepare_admin_configuration_proposal(
    property_id: str,
    question: str,
    conversation_id: str,
    history: list[dict[str, str]],
    principal: AdminPrincipal,
    request: Request,
    *,
    untrusted_source_text: str | None = None,
    only_action_names: set[str] | None = None,
) -> dict[str, Any]:
    request_id = _request_id(request)
    denied = _restricted_ai_action_reason(question, principal)
    if denied:
        _audit_assistant_action(principal, "assistant.action.denied", property_id, "restricted_or_unavailable", conversation_id=conversation_id, request_id=request_id)
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, denied, "operations")
        return _assistant_action_reply(question, conversation_id, denied)

    scope_denial = _explicit_assistant_scope_denial(question, principal, property_id)
    if scope_denial:
        _audit_assistant_action(principal, "assistant.action.denied", property_id, "scope_violation", conversation_id=conversation_id, request_id=request_id)
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, scope_denial, "operations")
        return _assistant_action_reply(question, conversation_id, scope_denial)

    actions = configuration_action_registry.available(principal, property_id)
    if only_action_names is not None:
        actions = [action for action in actions if action.name in only_action_names]
    if not actions:
        answer = "Your account does not have permission to make configuration changes through Admin AI. No changes were made."
        _audit_assistant_action(principal, "assistant.action.denied", property_id, "no_authorized_actions", conversation_id=conversation_id, request_id=request_id)
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, answer, "operations")
        return _assistant_action_reply(question, conversation_id, answer)
    targets = _assistant_action_targets(principal, property_id)
    allowed_names = [item.name for item in actions]
    try:
        planned = await asyncio.wait_for(ai_models.concierge_chat(
            property_id=property_id,
            user_message=action_planner_prompt(
                question, [item.public_dict() for item in actions], history, targets,
                untrusted_source_text=untrusted_source_text,
            ),
            hotel_name="Configuration Assistant",
            context=[],
            requested_mode="advanced",
            conversation_history=history,
            system_prompt_override=ADMIN_ACTION_POLICY,
        ), timeout=8.0)
    except Exception as exc:
        admin_auth.audit(principal, "assistant.copilot_provider_failure", "assistant", "configured_provider", property_id=property_id, metadata={"stage": "action_planning", "error_type": exc.__class__.__name__})
        answer = "I couldn't prepare a configuration proposal with the configured AI service. No changes were made. You can use the relevant Settings screen instead."
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, answer, "operations")
        return _assistant_action_reply(question, conversation_id, answer)

    action_name, parameters = parse_action_plan(planned.text, allowed_names)
    if action_name is None:
        try:
            raw_plan = json.loads(planned.text)
        except (TypeError, json.JSONDecodeError):
            raw_plan = {}
        requested_name = raw_plan.get("action") if isinstance(raw_plan, dict) else None
        if requested_name:
            _audit_assistant_action(principal, "assistant.action.denied", property_id, str(requested_name)[:100], conversation_id=conversation_id, request_id=request_id)
            answer = "That configuration action is not available to your account. No changes were made."
        else:
            answer = "I can prepare that change for review. Please include the property or assigned restaurant, the item to change, and the exact new values. No changes were made."
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, answer, "operations")
        return _assistant_action_reply(question, conversation_id, answer)

    context = _action_context(principal, property_id, request, conversation_id)
    try:
        action, validated_parameters, preview = configuration_action_registry.prepare(action_name, parameters, context)
    except (ActionDenied, ActionValidationError, ValueError, HTTPException) as exc:
        status = getattr(exc, "status_code", 403 if isinstance(exc, ActionDenied) else 422)
        _audit_assistant_action(principal, "assistant.action.denied", property_id, action_name, conversation_id=conversation_id, request_id=request_id)
        detail = getattr(exc, "detail", str(exc))
        answer = str(detail) + " No changes were made."
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, answer, "operations")
        response = _assistant_action_reply(question, conversation_id, answer)
        response["action_error_status"] = status
        return response

    # Persist the original validated allowlisted input. Normalized values can
    # contain complete schemas/defaults and are recomputed on confirmation.
    proposal = _store_assistant_action_proposal(principal, context, action, parameters, preview)
    answer = f"I prepared a {action.name.replace('.', ' ')} proposal. Review the current and proposed values below. No changes have been applied."
    admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, answer, "operations")
    response = _assistant_action_reply(question, conversation_id, answer, proposal)
    response["request_id"] = request_id
    return response


@app.post("/api/admin/properties/{property_id}/assistant/query")
async def operations_assistant(property_id: str, payload: AssistantQueryPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use"):
        raise HTTPException(status_code=403, detail="You do not have permission to use the assistant.")
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    record = _require_property_record(property_id)
    question = AIInputSanitizer.sanitize_text(payload.question)
    routing_question = question
    if payload.intent == "report":
        routing_question = f"Prepare an operations report. {question}"
    elif payload.intent == "health":
        routing_question = f"Check system health and current issues. {question}"
    period = _assistant_period_from_question(question, payload.period)
    conversation_id = payload.conversation_id or admin_copilot_store.new_conversation_id()
    history = admin_copilot_store.history(conversation_id, property_id, principal.user_id, _assistant_history_permissions(principal))
    if _is_assistant_greeting(question):
        capabilities = []
        if "diagnostics.view" in principal.permissions:
            capabilities.append("check the system health signals available to your role")
        if principal.can("reports.export") or principal.can("restaurant.analytics.view") or principal.can("analytics.view"):
            capabilities.append("summarize operational activity and prepare reports you are allowed to access")
        if principal.can("requests.view"):
            capabilities.append("review the service request queue")
        if not capabilities:
            capabilities.append("answer general operations questions using information available to your role")
        answer = "Hi! I can help " + ", ".join(capabilities) + ". Try asking for a system health check or an operations report."
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, answer, "operations")
        return {
            "question": question, "conversation_id": conversation_id, "answer": answer,
            "finding": "Ready to help with hotel operations.", "component": "assistant", "timeframe": "",
            "evidence": [], "evidence_items": [], "recommendations": [], "links": [], "downloads": [],
            "tool_activity": [], "confirmation_required": False, "action_status": "No changes were made.",
        }

    if payload.intent == "auto" and (_is_configuration_request(question) or _restricted_ai_action_reason(question, principal)):
        long_menu_request = len(question) > 1200 and bool(re.search(r"\b(?:menu|breakfast|lunch|dinner)\b", question, re.I))
        return await _prepare_admin_configuration_proposal(
            property_id, question[:1200] if long_menu_request else question,
            conversation_id, history, principal, request,
            untrusted_source_text=question if long_menu_request else None,
        )

    tools_allowed = available_tools(diagnostic_tools, principal.permissions)
    if not tools_allowed:
        raise HTTPException(status_code=403, detail="Your account does not have access to operational checks. Ask an administrator to review your assistant access.")
    requested_tool = _choose_diagnostic_tool(routing_question, tools_allowed)
    if not requested_tool and "get_system_health" in tools_allowed and any(word in routing_question.casefold() for word in ("system", "health", "issue", "problem", "down")):
        requested_tool = "get_system_health"
    if not requested_tool:
        if payload.intent == "report" or any(word in routing_question.casefold() for word in ("report", "summary", "summarize", "export")):
            detail = "Your role does not have access to this report. Ask an administrator for report access scoped to your area."
        else:
            detail = "Your role does not have access to this system check. Ask an administrator to review your diagnostic access."
        raise HTTPException(status_code=403, detail=detail)
    destructive = bool(re.search(r"\b(restart|delete|disable|enable|change|rotate|reset|deploy|update|remove|configure|publish)\b", question, re.I))
    context = DiagnosticContext(property_id, principal.role_slug, principal.department_id, principal.permissions, _request_id(request))
    model_unavailable = False
    selected_tools: list[str] = []
    report_request = payload.intent == "report" or any(word in routing_question.casefold() for word in ("report", "summary", "summarize", "export"))
    health_request = payload.intent == "health" or any(word in routing_question.casefold() for word in ("system", "health", "issue", "problem", "down", "check all"))
    if report_request:
        selected_tools = [requested_tool]
    elif health_request:
        # Run deterministic, permission-scoped health checks before asking the model
        # to interpret them. A slow/unavailable provider must not block diagnostics.
        selected_tools = _fallback_tools(routing_question, tools_allowed)
    else:
        try:
            planned = await asyncio.wait_for(ai_models.concierge_chat(
                property_id=property_id, user_message=planner_prompt(question, tools_allowed, history),
                hotel_name="Operations Copilot", context=[], requested_mode="advanced",
                conversation_history=history, system_prompt_override=ADMIN_POLICY + " Return only the requested JSON object when selecting tools.",
            ), timeout=8.0)
            selected_tools = parse_tool_plan(planned.text, tools_allowed)
        except Exception as exc:
            model_unavailable = True
            admin_auth.audit(principal, "assistant.copilot_provider_failure", "assistant", "configured_provider", property_id=property_id, metadata={"stage": "planning", "error_type": exc.__class__.__name__})
        if model_unavailable or not selected_tools:
            selected_tools = _fallback_tools(routing_question, tools_allowed)
        elif health_request:
            selected_tools = list(dict.fromkeys([*selected_tools, *_fallback_tools(routing_question, tools_allowed)]))[:5]
    if not selected_tools:
        raise HTTPException(status_code=403, detail="No checks are available for this request under your role. Ask an administrator to review your assistant access.")

    # Assigned-restaurant reports use only that user's assignments and do not need a property-wide dashboard.
    dashboard = _build_operations_dashboard(property_id, period, principal) if any(tool != "prepare_assigned_restaurant_report" for tool in selected_tools) else {}
    evidence = []
    try:
        for tool_name in selected_tools:
            # Registry.run checks the principal's permission again on every tool call.
            result = diagnostic_tools.run(tool_name, context, dashboard=dashboard, record=record, period=period, principal=principal)
            evidence.append({"tool": tool_name, "result": result})
    except Exception as exc:
        logger.exception("Operations assistant diagnostic failed", extra={"request_id": context.request_id, "property_id": property_id})
        raise HTTPException(status_code=503, detail="I couldn't complete that check. Please try again or open the related operations screen.") from exc

    finding, deterministic_answer, recommendations = _assistant_fallback_summary(evidence, period, model_unavailable=False)
    if destructive:
        synthesis = "I can explain the recommended change, but changes must be confirmed in the relevant settings workflow. I made no changes."
    elif model_unavailable:
        synthesis = deterministic_answer
    else:
        try:
            synthesized = await asyncio.wait_for(ai_models.concierge_chat(
                property_id=property_id, user_message=synthesis_prompt(question, evidence, history),
                hotel_name="Operations Copilot", context=[], requested_mode="advanced",
                conversation_history=history, system_prompt_override=ADMIN_POLICY,
            ), timeout=8.0)
            synthesis = AIOutputValidator.validate(synthesized.text)
        except Exception as exc:
            model_unavailable = True
            admin_auth.audit(principal, "assistant.copilot_provider_failure", "assistant", "configured_provider", property_id=property_id, metadata={"stage": "synthesis", "error_type": exc.__class__.__name__})
            _, synthesis, recommendations = _assistant_fallback_summary(evidence, period, model_unavailable=True)

    primary = evidence[0]["result"] if evidence else {"component": "diagnostics", "state": "unavailable", "evidence": []}
    tool = evidence[0]["tool"] if len(evidence) == 1 else "multi_tool_investigation"
    links = [{"label": "Open system health", "panel": "system-health"}]
    report_evidence = any(item["tool"] in {"prepare_management_report", "prepare_assigned_restaurant_report", "analyze_business_operations"} for item in evidence)
    if any(item["tool"] in {"analyze_business_operations", "compare_time_periods", "check_guest_auth", "check_request_queue"} for item in evidence):
        links = [{"label": "Open analytics", "panel": "analytics"}, *links]
    if any(item["tool"] == "prepare_management_report" for item in evidence):
        links = [{"label": "Open reports", "panel": "reports"}]
    elif any(item["tool"] == "prepare_assigned_restaurant_report" for item in evidence):
        links = [{"label": "Open restaurants", "panel": "restaurants"}]
    downloads = []
    if report_evidence and principal.can("reports.export"):
        base = f"/api/admin/properties/{quote(property_id, safe='')}/reports/export"
        downloads = [
            {"label": "Download PDF report", "url": f"{base}.pdf?period={quote(period, safe='')}"},
            {"label": "Download spreadsheet", "url": f"{base}.xlsx?period={quote(period, safe='')}"},
        ]
    if model_unavailable:
        _, synthesis, recommendations = _assistant_fallback_summary(evidence, period, model_unavailable=True)
    history_type = "report" if report_request else "health" if health_request else "operations"
    admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, synthesis, history_type)
    response = {
        "question": question, "conversation_id": conversation_id, "answer": synthesis, "tool": tool, "finding": finding,
        "component": primary.get("component", "diagnostics"),
        "timeframe": _assistant_period_label(primary.get("timeframe", period)) if primary.get("timeframe", period) == period else primary.get("timeframe", period),
        "evidence": evidence, "evidence_items": _assistant_evidence_items(evidence),
        "likely_cause": primary.get("likely_cause"), "tool_activity": [item["tool"] for item in evidence],
        "recommendations": recommendations,
        "links": links,
        "downloads": downloads,
        "confirmation_required": destructive,
        "action_status": "No change was made. Explicit confirmation in the relevant configuration screen is required." if destructive else "No changes were made.",
        "request_id": context.request_id,
    }
    observability.log_diagnostic(context.request_id, property_id, principal.user_id, tool, period, finding)
    admin_auth.audit(principal, "assistant.diagnostic", "diagnostic", tool, property_id=property_id, metadata={"period": period, "tools": [item["tool"] for item in evidence], "confirmation_required": destructive})
    return response


@app.post("/api/admin/properties/{property_id}/assistant/menu-import")
async def import_admin_assistant_menu(
    property_id: str,
    payload: AssistantMenuImportPayload,
    request: Request,
) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    if not principal.can("restaurant.menu.edit"):
        raise HTTPException(status_code=403, detail="Permission required: restaurant.menu.edit")
    record = _require_property_record(property_id)
    extracted: list[str] = []
    try:
        for upload in payload.files:
            content = _decode_knowledge_upload(upload)
            filename, extension = validate_file(upload.filename, upload.content_type, content)
            blocks = parse_document(content, extension)
            extracted.append(f"Source: {filename}\n" + "\n".join(block["text"] for block in blocks))
        source_text = AIInputSanitizer.sanitize_text("\n\n".join(extracted))
        if len(source_text) > 40000:
            raise ValueError("Combined extracted menu text exceeds the 40,000 character review limit.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    conversation_id = payload.conversation_id or admin_copilot_store.new_conversation_id()
    history = admin_copilot_store.history(
        conversation_id, property_id, principal.user_id, _assistant_history_permissions(principal),
    )
    question = AIInputSanitizer.sanitize_text(payload.question)
    return await _prepare_admin_configuration_proposal(
        property_id, question, conversation_id, history, principal, request,
        untrusted_source_text=source_text, only_action_names={"menu.import_draft"},
    )


@app.post("/api/admin/properties/{property_id}/assistant/actions/{proposal_id}/confirm")
async def confirm_assistant_configuration_action(
    property_id: str,
    proposal_id: str,
    payload: AssistantActionConfirmationPayload,
    request: Request,
) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    existing = assistant_action_proposals.get(proposal_id, principal.user_id, property_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Configuration proposal not found.")
    action = configuration_action_registry.get(existing["action_name"])
    if action is None:
        raise HTTPException(status_code=409, detail="This configuration action is no longer available.")
    expected_phrase = f"APPLY {proposal_id[:6].upper()}"
    if existing["confirmation_requirement"] == "strong" and not hmac.compare_digest(
        (payload.confirmation_phrase or "").strip(), expected_phrase,
    ):
        raise HTTPException(status_code=400, detail=f"Type {expected_phrase} to confirm this higher-risk change.")

    claimed = assistant_action_proposals.claim(proposal_id, principal.user_id, property_id)
    if not claimed:
        raise HTTPException(status_code=409, detail="This proposal has expired, was already used, or is no longer pending.")
    confirmation_time = int(time.time())
    context = _action_context(principal, property_id, request, claimed["conversation_id"])
    try:
        stored_parameters = json.loads(claimed["parameters_json"])
        checked_action, checked_parameters, preview = configuration_action_registry.prepare(
            claimed["action_name"], stored_parameters, context,
        )
        if checked_action.name != action.name:
            raise ActionDenied("This action is no longer available.")
        expected_current = encode_json(json.loads(claimed["current_json"]))
        actual_current = encode_json(_action_safe_value(preview.get("current")))
        if expected_current != actual_current:
            assistant_action_proposals.finish(proposal_id, "stale", {"detail": "Configuration changed after proposal."}, confirmation_time)
            _audit_assistant_action(
                principal, "assistant.action.failed", property_id, action.name,
                conversation_id=claimed["conversation_id"], request_id=claimed["request_id"],
                restaurant_id=preview.get("restaurant_id"), old_value=json.loads(claimed["current_json"]),
                new_value=preview.get("proposed"), permission=action.required_permission,
                risk_level=action.risk_level, confirmed_at=confirmation_time, error_type="stale_proposal",
            )
            raise HTTPException(status_code=409, detail="The configuration changed after this proposal. Prepare a new proposal and review the latest values.")
    except HTTPException:
        raise
    except (ActionDenied, ActionValidationError, KeyError, TypeError, ValueError) as exc:
        assistant_action_proposals.finish(proposal_id, "failed", {"error_type": exc.__class__.__name__}, confirmation_time)
        _audit_assistant_action(
            principal, "assistant.action.denied", property_id, action.name,
            conversation_id=claimed["conversation_id"], request_id=claimed["request_id"],
            permission=action.required_permission, risk_level=action.risk_level,
            confirmed_at=confirmation_time, error_type=exc.__class__.__name__,
        )
        raise HTTPException(status_code=403 if isinstance(exc, ActionDenied) else 422, detail=str(exc)) from exc

    _audit_assistant_action(
        principal, "assistant.action.confirmed", property_id, action.name,
        conversation_id=claimed["conversation_id"], request_id=claimed["request_id"],
        restaurant_id=preview.get("restaurant_id"), old_value=preview.get("current"),
        new_value=preview.get("proposed"), permission=action.required_permission,
        risk_level=action.risk_level, confirmed_at=confirmation_time,
    )
    try:
        result = await configuration_action_registry.execute(checked_action, context, checked_parameters)
        assistant_action_proposals.finish(proposal_id, "executed", _action_safe_value(result), confirmation_time)
    except Exception as exc:
        assistant_action_proposals.finish(proposal_id, "failed", {"error_type": exc.__class__.__name__}, confirmation_time)
        _audit_assistant_action(
            principal, "assistant.action.failed", property_id, action.name,
            conversation_id=claimed["conversation_id"], request_id=claimed["request_id"],
            restaurant_id=preview.get("restaurant_id"), permission=action.required_permission,
            risk_level=action.risk_level, confirmed_at=confirmation_time,
            error_type=exc.__class__.__name__,
        )
        if isinstance(exc, (HTTPException, GuestHostnameConflict)):
            raise
        logger.exception("Admin AI configuration action failed", extra={"request_id": context.request_id, "property_id": property_id, "action": action.name})
        raise HTTPException(status_code=422, detail="The configuration service rejected this change. The proposal cannot be reused.") from exc

    _audit_assistant_action(
        principal, action.audit_event, property_id, action.name,
        conversation_id=claimed["conversation_id"], request_id=claimed["request_id"],
        restaurant_id=preview.get("restaurant_id"), old_value=preview.get("current"),
        new_value=preview.get("proposed"), permission=action.required_permission,
        risk_level=action.risk_level, confirmed_at=confirmation_time, result=result,
    )
    followup_proposal = None
    if action.name in {"menu.create_draft", "menu.import_draft"} and principal.can("restaurant.menu.approve") and isinstance(result, dict) and result.get("menu_id"):
        followup_name = "menu.approve_and_publish"
        followup_parameters = {"restaurant_id": result.get("restaurant_id"), "menu_id": result["menu_id"]}
    elif action.name == "promotion.create_draft" and principal.can("restaurant.promotions.approve") and isinstance(result, dict) and result.get("promotion_id"):
        followup_name = "promotion.approve_and_publish"
        followup_parameters = {"restaurant_id": result.get("restaurant_id"), "promotion_id": result["promotion_id"]}
    else:
        followup_name = ""
        followup_parameters = {}
    if followup_name:
        try:
            followup_action, followup_validated, followup_preview = configuration_action_registry.prepare(
                followup_name, followup_parameters, context,
            )
            followup_proposal = _store_assistant_action_proposal(
                principal, context, followup_action, followup_parameters, followup_preview,
            )
        except (ActionDenied, ActionValidationError, HTTPException, ValueError) as exc:
            admin_auth.audit(principal, "assistant.action.denied", "assistant_action", followup_name, property_id=property_id, metadata={"assistant_conversation_id": claimed["conversation_id"], "request_id": context.request_id, "error_type": exc.__class__.__name__})
    return {
        "status": "executed",
        "proposal_id": proposal_id,
        "action": action.name,
        "result": _action_safe_value(result),
        "next_proposal": followup_proposal,
        "confirmation_timestamp": confirmation_time,
        "request_id": context.request_id,
    }


@app.delete("/api/admin/properties/{property_id}/assistant/actions/{proposal_id}")
async def cancel_assistant_configuration_action(property_id: str, proposal_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    existing = assistant_action_proposals.get(proposal_id, principal.user_id, property_id)
    if not existing or not assistant_action_proposals.cancel(proposal_id, principal.user_id, property_id):
        raise HTTPException(status_code=409, detail="This proposal is no longer pending.")
    _audit_assistant_action(
        principal, "assistant.action.cancelled", property_id, existing["action_name"],
        conversation_id=existing["conversation_id"], request_id=_request_id(request),
        permission=existing["permission_used"], risk_level=existing["risk_level"],
    )
    return {"status": "cancelled", "proposal_id": proposal_id}


@app.delete("/api/admin/properties/{property_id}/assistant/conversation")
async def clear_operations_assistant(property_id: str, payload: AssistantConversationPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    admin_copilot_store.clear(payload.conversation_id, property_id, principal.user_id)
    return {"status": "cleared"}


def _assistant_history_permissions(principal: AdminPrincipal) -> set[str]:
    allowed = {"operations"}
    if principal.can("knowledge.view"):
        allowed.add("hotel")
    if principal.can("reports.export") or principal.can("analytics.view") or principal.can("restaurant.analytics.view"):
        allowed.add("report")
    if any(principal.can(permission) for permission in (
        "diagnostics.view", "infrastructure.view", "ai.view", "integrations.view", "domains.view", "requests.view",
    )):
        allowed.add("health")
    return allowed


@app.get("/api/admin/properties/{property_id}/assistant/conversations")
async def list_admin_assistant_conversations(property_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use"):
        raise HTTPException(status_code=403, detail="You do not have permission to use the assistant.")
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    conversations = admin_copilot_store.conversations(property_id, principal.user_id, _assistant_history_permissions(principal))
    return {"conversations": conversations, "retention_days": 30}


@app.get("/api/admin/properties/{property_id}/assistant/conversations/{conversation_id}")
async def get_admin_assistant_conversation(property_id: str, conversation_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use"):
        raise HTTPException(status_code=403, detail="You do not have permission to use the assistant.")
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    messages = admin_copilot_store.messages(conversation_id, property_id, principal.user_id, _assistant_history_permissions(principal))
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found or no longer available to your role.")
    return {"conversation_id": conversation_id, "messages": messages}


@app.post("/api/admin/properties/{property_id}/assistant/hotel-chat")
async def admin_hotel_assistant(property_id: str, payload: HotelAssistantPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use"):
        raise HTTPException(status_code=403, detail="You do not have permission to use the assistant.")
    if not principal.can("knowledge.view"):
        raise HTTPException(status_code=403, detail="Permission required: knowledge.view")
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    record = _require_property_record(property_id)
    question = AIInputSanitizer.sanitize_text(payload.question or "")
    attached_files = [AIInputSanitizer.sanitize_text(name)[:240] for name in payload.attached_files if str(name).strip()]
    if not question and not attached_files:
        raise HTTPException(status_code=422, detail="Ask a hotel knowledge question or attach a document for review.")
    conversation_id = payload.conversation_id or admin_copilot_store.new_conversation_id()
    history = admin_copilot_store.history(conversation_id, property_id, principal.user_id, _assistant_history_permissions(principal))
    history_question = question or "Uploaded knowledge documents"
    if attached_files:
        history_question += "\nAttached files: " + ", ".join(attached_files)

    def remembered(answer: str, **details: Any) -> dict[str, Any]:
        admin_copilot_store.append(conversation_id, property_id, principal.user_id, history_question, answer, "hotel")
        return {"question": question, "conversation_id": conversation_id, "answer": answer, **details}

    if not question:
        answer = "The document(s) are in the property's knowledge review queue. Processing may take a short time; nothing is published to guest chat until a reviewer approves it."
        return remembered(answer, provider="knowledge_tools", model="deterministic", sources=[])
    lower_question = question.casefold()
    if not question.endswith("?") and (lower_question.startswith("our ") or lower_question.startswith("the hotel ")) and any(token in lower_question for token in (" is ", " are ", " opens ", " closes ")):
        category = next((category for category in CATEGORIES if category.casefold() in lower_question), "Other")
        if "pool" in lower_question: category = "Pool"
        elif "gym" in lower_question: category = "Gym"
        elif "restaurant" in lower_question or "breakfast" in lower_question: category = "Dining"
        proposal = {"title": question.split(" is ", 1)[0][:100].strip(" ."), "content": question, "category": category, "visibility": "admin"}
        answer = f"I can save this as a {category} knowledge draft. Review the wording and visibility before approving or publishing it."
        return remembered(answer, provider="knowledge_tools", model="deterministic", sources=[], proposed_draft=proposal)
    if any(phrase in lower_question for phrase in ("knowledge health", "missing knowledge", "knowledge coverage")):
        health = knowledge_management.health(property_id)
        answer = f"Knowledge coverage is {health['coverage_percent']}%. Missing categories: {', '.join(health['missing_categories']) or 'none'}. Missing core facts: {', '.join(health['missing_fields']) or 'none'}. Pending review: {health['pending_review']}; open conflicts: {health['open_conflicts']}. {health['methodology']}"
        return remembered(answer, provider="knowledge_tools", model="deterministic", sources=[])
    if any(phrase in lower_question for phrase in ("find conflicts", "contradictory information", "show conflicts")):
        conflicts = [item for item in knowledge_management.conflicts(property_id) if item["status"] == "open"]
        answer = f"{len(conflicts)} unresolved knowledge conflict(s). Review them in Knowledge Management."
        return remembered(answer, provider="knowledge_tools", model="deterministic", sources=[])
    if any(phrase in lower_question for phrase in ("pending review", "waiting for approval")):
        pending = knowledge_management.list_items(property_id, status="ready_review")
        pending = [item for item in pending if _knowledge_item_allowed(item, principal)]
        answer = f"{len(pending)} knowledge item(s) are waiting for review."
        return remembered(answer, provider="knowledge_tools", model="deterministic", sources=[{"item_id": item["item_id"], "title": item["title"]} for item in pending[:20]])
    managed_context = knowledge_management.search(property_id, question, guest=False, role_slug=principal.role_slug)
    context = managed_context + operations.search_knowledge(property_id, question, include_documents=False)
    context.extend(_property_ai_context(record))
    try:
        result = await ai_models.concierge_chat(
            property_id=property_id,
            user_message=question,
            hotel_name=record.hotel_name,
            context=AIInputSanitizer.sanitize_context(context),
            requested_mode="auto",
            conversation_history=history,
            system_prompt_override=ADMIN_KNOWLEDGE_POLICY,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The configured AI provider could not answer. Check AI Models and provider status, then try again.") from exc
    answer = AIOutputValidator.validate(result.text)
    admin_auth.audit(principal, "assistant.hotel_chat", "assistant", result.provider, property_id=property_id, metadata={"model": result.model})
    return remembered(answer, provider=result.provider, model=result.model, sources=[{"title": item["title"], "source": item["source"], "source_id": item["source_id"], "item_id": item["item_id"], "location": item["location"], "status": item["status"]} for item in managed_context])


@app.middleware("http")
async def enforce_guest_origin(request: Request, call_next):
    path = request.url.path
    normalized_path = path.rstrip("/") or "/"
    if request.url.scheme != "https":
        forwarded_scheme = _trusted_forwarded_scheme(request, normalized_path)
        if forwarded_scheme:
            request.scope["scheme"] = forwarded_scheme
            # Starlette caches Request.url after the initial path lookup above.
            if hasattr(request, "_url"):
                del request._url
    secure_environment = settings.app_environment in SECURE_ENVIRONMENTS
    if secure_environment:
        if not getattr(request.state, "request_id", None):
            request.state.request_id = uuid.uuid4().hex
        host_header = request.headers.get("host", "")
        try:
            normalized_host = normalize_host_header(host_header)
        except ValueError:
            normalized_host = ""
        local_loopback_origin = _trusted_loopback_origin(request, normalized_host)
        loopback_health_probe = False
        if path in {"/health", "/health/live", "/health/ready"}:
            try:
                loopback_health_probe = bool(request.client and ipaddress.ip_address(request.client.host).is_loopback)
            except ValueError:
                pass
        recognized_hosts = {_normalize_hostname(host) for host in settings.canonical_hosts}
        for record in properties.list():
            recognized_hosts.update(property_guest_hostnames(record))
        recognized_hosts.discard("")
        if local_loopback_origin:
            recognized_hosts.update({"localhost", "127.0.0.1", "::1"})
        if not loopback_health_probe and normalized_host not in recognized_hosts:
            response = JSONResponse({"detail": "Unrecognized host."}, status_code=400)
            return _apply_security_headers(request, response)
        if request.url.scheme != "https" and not local_loopback_origin and path not in {"/health", "/health/live", "/health/ready"}:
            response = JSONResponse({"detail": "HTTPS is required."}, status_code=426)
            return _apply_security_headers(request, response)

    protected_management_path = (
        normalized_path == "/admin"
        or normalized_path.startswith("/admin/")
        or normalized_path == "/api/admin"
        or normalized_path.startswith("/api/admin/")
        or normalized_path in {"/metrics", "/health/details"}
    )
    if protected_management_path:
        policy = _effective_management_access_settings()
        decision = management_access_guard.evaluate(
            request.client.host if request.client else "",
            request.headers,
            policy,
            excluded_cidrs=_active_guest_network_ranges(),
        )
        if not decision.allowed:
            security_audit.record(
                _request_id(request),
                _path_property_id(path),
                "management_access_denied",
                "denied",
                decision.client_ip,
                resource=normalized_path,
                actor="unknown",
                metadata={"method": request.method, "reason": "network_policy"},
            )
            logger.warning(
                "management_access_denied request_id=%s path=%s reason=network_policy",
                _request_id(request),
                normalized_path,
            )
            response = JSONResponse({"detail": "Management access is restricted to approved networks."}, status_code=403)
            return _apply_security_headers(request, response)

    if (normalized_path == "/" or _is_guest_request_path(normalized_path)) and _guest_access_is_disabled(request):
        response = JSONResponse({"detail": "Guest access is disabled."}, status_code=403)
        return _apply_security_headers(request, response)
    guest_mutation = request.method not in {"GET", "HEAD", "OPTIONS"} and (
        path.startswith("/api/guest/") or path in {"/api/session/start", "/api/session/resume", "/api/authenticate", "/api/chat"}
    )
    # Browser guest mutations must come from a configured property/canonical
    # origin. A matching Origin and Host alone is not enough: both can be
    # attacker-controlled when an installation accepts an unmapped Host.
    # Requests with no Origin/Referer remain supported for native and
    # server-to-server clients; browser Fetch Metadata still rejects cross-site
    # requests. Gateway-backed session starts independently validate their HMAC.
    if guest_mutation and not _guest_mutation_origin_allowed(request):
        security_audit.record(_request_id(request), None, "guest_origin_blocked", "denied", request.client.host if request.client else "", metadata={"path": path})
        response = JSONResponse({"detail": "Cross-origin guest mutation denied."}, status_code=403)
        return _apply_security_headers(request, response)
    response = await call_next(request)
    return _refresh_guest_cookie_response(request, response)


def _normalize_hostname(hostname: str | None) -> str:
    try:
        return normalize_guest_hostname(hostname)
    except ValueError:
        return ""


def _origin_tuple(value: str, *, allow_path: bool) -> tuple[str, str, int] | None:
    if not value or len(value) > 2048 or any(character in value for character in "\\\r\n"):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if not allow_path and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            return None
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError:
        return None
    hostname = _normalize_hostname(parsed.hostname)
    if not hostname or not 1 <= port <= 65535:
        return None
    return parsed.scheme.casefold(), hostname, port


def _guest_mutation_origin_allowed(request: Request) -> bool:
    fetch_site = request.headers.get("sec-fetch-site", "").strip().casefold()
    if fetch_site == "cross-site":
        return False

    origin_header = request.headers.get("origin")
    referer_header = request.headers.get("referer")
    source_header = origin_header or referer_header
    if not source_header:
        # Browsers that send Fetch Metadata must not omit the origin while
        # making a cross-origin or sibling-origin request. Older native clients
        # and signed gateway integrations may not send either header.
        return fetch_site not in {"cross-site", "same-site"}

    source = _origin_tuple(source_header, allow_path=not bool(origin_header))
    host_header = request.headers.get("host", "")
    try:
        parsed_host = urlsplit(f"//{host_header}")
        if parsed_host.path or parsed_host.query or parsed_host.fragment or parsed_host.username or parsed_host.password:
            return False
        request_host = _normalize_hostname(parsed_host.hostname)
        request_port = (
            parsed_host.port
            if parsed_host.port is not None
            else (443 if request.url.scheme.casefold() == "https" else 80)
        )
    except ValueError:
        return False
    request_origin = (request.url.scheme.casefold(), request_host, request_port)
    if source is None or source != request_origin:
        return False

    configured_hosts = {_normalize_hostname(host) for host in settings.canonical_hosts}
    configured_hosts.discard("")
    for record in properties.list():
        configured_hosts.update(property_guest_hostnames(record))
    if settings.app_environment not in SECURE_ENVIRONMENTS:
        configured_hosts.update({"localhost", "127.0.0.1", "::1"})
    return source[1] in configured_hosts


def _source_ip_allowed(source_ip: str, allowed_cidrs: tuple[str, ...] | list[str]) -> bool:
    if source_ip == "testclient":
        source_ip = "127.0.0.1"
    try:
        address = ipaddress.ip_address(source_ip)
        return any(address in ipaddress.ip_network(value, strict=False) for value in allowed_cidrs)
    except ValueError:
        return False


def _default_management_access_settings() -> dict[str, Any]:
    configured_proxies = [item.strip() for item in settings.forwarded_allow_ips.split(",") if item.strip() and item.strip() != "*"]
    allowed = settings.admin_allowed_cidrs or DEFAULT_MANAGEMENT_CIDRS
    try:
        return normalize_management_access(
            {
                "management_access_enabled": True,
                "management_allowed_cidrs": list(allowed),
                "management_trusted_proxy_ranges": configured_proxies,
            },
            default_allowed_cidrs=(),
            default_trusted_proxy_ranges=(),
        )
    except (TypeError, ValueError):
        # Bad deployment bootstrap values must not create an unrestricted fallback.
        return {
            "management_access_enabled": True,
            "management_allowed_cidrs": [],
            "management_trusted_proxy_ranges": [],
        }


def _management_access_settings() -> dict[str, Any]:
    defaults = _default_management_access_settings()
    try:
        stored = operations.get_network_access_settings(defaults)
        return normalize_management_access(stored, default_allowed_cidrs=(), default_trusted_proxy_ranges=())
    except Exception:
        logger.exception("Management network policy could not be loaded; denying management access.")
        return {"management_access_enabled": True, "management_allowed_cidrs": [], "management_trusted_proxy_ranges": []}


def _effective_management_access_settings() -> dict[str, Any]:
    try:
        config = operations.get_network_access_settings(_default_management_access_settings())
        deadline = config.get("_rollback_deadline")
        previous = config.get("_rollback_config")
        if deadline and previous and int(deadline) <= int(time.time()):
            normalized = normalize_management_access(previous, default_allowed_cidrs=(), default_trusted_proxy_ranges=())
            operations.save_network_access_settings(normalized)
            security_audit.record(
                uuid.uuid4().hex,
                None,
                "management_access_auto_rollback",
                "success",
                resource="network_access",
                actor="system",
                metadata={"reason": "administrator_confirmation_window_expired"},
            )
            return normalized
        return normalize_management_access(config, default_allowed_cidrs=(), default_trusted_proxy_ranges=())
    except Exception:
        logger.exception("Management network policy could not be loaded; denying management access.")
        return {"management_access_enabled": True, "management_allowed_cidrs": [], "management_trusted_proxy_ranges": []}


def _active_guest_network_ranges() -> list[str]:
    """Exclude configured guest-only networks from management access, even if ranges overlap."""
    ranges: list[str] = []
    for record in properties.list():
        try:
            guest_policy = normalize_guardrails(record.guardrails)
        except (TypeError, ValueError):
            continue
        if not guest_policy.get("guest_network_only", True):
            continue
        for value in guest_policy.get("allowed_cidrs", []):
            network = ipaddress.ip_network(value, strict=False)
            # Loopback ranges are local application/testing addresses, never a
            # hotel guest network, and must not disable local administrator access.
            if network.is_loopback or value in ranges:
                continue
            ranges.append(value)
    return ranges


def _is_guest_request_path(path: str) -> bool:
    return path.startswith("/api/guest/") or path in {"/api/session/start", "/api/session/resume", "/api/authenticate", "/api/chat"}


def _request_is_loopback(request: Request) -> bool:
    direct_ip = request.client.host if request.client else ""
    if direct_ip == "testclient":
        return True
    try:
        return ipaddress.ip_address(direct_ip).is_loopback
    except ValueError:
        return False


def _trusted_loopback_origin(request: Request, hostname: str) -> bool:
    """Permit HTTP localhost only over a direct loopback socket or our localhost-only proxy."""
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False
    if _request_is_loopback(request):
        return True
    if request.headers.get("x-concierge-loopback-origin") != "1":
        return False
    direct_ip = request.client.host if request.client else ""
    try:
        peer = ipaddress.ip_address(direct_ip)
    except ValueError:
        return False
    path = request.url.path
    management_path = (
        path == "/admin"
        or path.startswith("/admin/")
        or path == "/api/admin"
        or path.startswith("/api/admin/")
        or path in {"/metrics", "/health", "/health/live", "/health/ready", "/health/details"}
    )
    if management_path:
        ranges = _effective_management_access_settings().get("management_trusted_proxy_ranges", [])
    else:
        ranges = _guest_trusted_proxy_ranges(request)
    return bool(management_access_guard._matching_network(peer, ranges))


def _trusted_forwarded_scheme(request: Request, path: str) -> str:
    management_path = (
        path == "/admin"
        or path.startswith("/admin/")
        or path == "/api/admin"
        or path.startswith("/api/admin/")
        or path in {"/metrics", "/health/details"}
    )
    if management_path:
        trusted_ranges = _effective_management_access_settings().get("management_trusted_proxy_ranges", [])
    elif path == "/" or _is_guest_request_path(path):
        trusted_ranges = _guest_trusted_proxy_ranges(request)
    else:
        trusted_ranges = []
    direct_ip = request.client.host if request.client else ""
    try:
        peer = ipaddress.ip_address(direct_ip)
    except ValueError:
        return ""
    if not management_access_guard._matching_network(peer, trusted_ranges):
        return ""
    forwarded = request.headers.get("x-forwarded-proto", "").strip().lower()
    return forwarded if forwarded in {"http", "https"} else ""


def _guest_deployment_settings(request: Request) -> dict[str, Any]:
    record = _guest_record_for_request(request)
    return dict(((record.app_settings or {}).get("deployment") or {}) if record else {})


def _guest_trusted_proxy_ranges(request: Request) -> list[str]:
    record = _guest_record_for_request(request)
    if record is None:
        return []
    guardrails = normalize_guardrails(record.guardrails)
    ranges = list(guardrails.get("trusted_proxy_ranges", []))
    legacy_proxy = str(((record.app_settings or {}).get("deployment") or {}).get("trusted_proxy") or "").strip()
    if legacy_proxy:
        try:
            normalized = normalize_cidrs([legacy_proxy], "trusted_proxy")
            ranges.extend(item for item in normalized if item not in ranges)
        except ValueError:
            return ranges
    return ranges


def _guest_record_for_request(request: Request) -> PropertyRecord | None:
    records = properties.list()
    try:
        record = PropertyGuard.host_record(records, request.headers.get("host", ""))
    except (PermissionError, ValueError):
        return None
    if record is not None:
        return record
    if settings.property_id:
        record = next((item for item in records if item.property_id == settings.property_id), None)
    if record is None and len(records) == 1:
        record = records[0]
    return record


def _guest_access_is_disabled(request: Request) -> bool:
    deployment = _guest_deployment_settings(request)
    return deployment.get("guest_access_enabled") is False


def _guest_https_is_required(request: Request) -> bool:
    return _guest_deployment_settings(request).get("https_required", True) is not False


def _admin_password_reset_url(request: Request, token: str) -> str:
    del request  # Reset links must never inherit the request Host header.
    origin = settings.public_base_url
    if not origin:
        raise RuntimeError("PUBLIC_BASE_URL must be configured before sending password reset links.")
    return f"{origin}/admin/login#reset_token={quote(token, safe='')}"


@app.get("/api/admin/properties/{property_id}/reports/export.xlsx")
async def export_operations_xlsx(property_id: str, request: Request, period: str = "7d") -> Response:
    principal = _admin_principal(request)
    record = _require_property_record(property_id)
    analytics = _report_analytics_for_principal(property_id, period, principal)
    dashboard = _build_operations_dashboard(property_id, period, principal)
    content = report_service.workbook(record.hotel_name, analytics, _recommendations(analytics, dashboard["alerts"]))
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{property_id}-{period}-operations.xlsx"'})


@app.get("/api/admin/properties/{property_id}/reports/export.pdf")
async def export_operations_pdf(property_id: str, request: Request, period: str = "7d") -> Response:
    principal = _admin_principal(request)
    record = _require_property_record(property_id)
    analytics = _report_analytics_for_principal(property_id, period, principal)
    dashboard = _build_operations_dashboard(property_id, period, principal)
    content = report_service.management_pdf(record.hotel_name, analytics, dashboard["alerts"], _recommendations(analytics, dashboard["alerts"]))
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{property_id}-{period}-management.pdf"'})


@app.get("/api/admin/properties/{property_id}/personalization")
async def get_personalization_policy(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return personalization.policy(property_id)


@app.put("/api/admin/properties/{property_id}/personalization")
async def save_personalization_policy(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return personalization.save_policy(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}")
async def upsert_property(property_id: str, payload: PropertyPayload, request: Request) -> dict[str, Any]:
    if property_id != payload.property_id:
        raise HTTPException(status_code=400, detail="Property ID must match the request path.")
    if not payload.hotel_name.strip():
        raise HTTPException(status_code=422, detail="Property name is required.")
    if not payload.timezone.strip():
        raise HTTPException(status_code=422, detail="Timezone is required.")
    record = payload.to_record()
    record.hotel_name = payload.hotel_name.strip()
    record.timezone = payload.timezone.strip()
    try:
        record.domain = _validated_guest_domain(record.domain)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing = properties.get(property_id)
    principal = _admin_principal(request)
    if existing and not principal.can("network.manage"):
        if "guest_access_hosts" not in record.guardrails:
            record.guardrails["guest_access_hosts"] = normalize_guardrails(existing.guardrails)["guest_access_hosts"]
        elif normalize_guardrails(record.guardrails)["guest_access_hosts"] != normalize_guardrails(existing.guardrails)["guest_access_hosts"]:
            raise HTTPException(status_code=403, detail="Permission required: network.manage")
        if _guest_network_settings(existing) != _guest_network_settings(record):
            raise HTTPException(status_code=403, detail="Permission required: network.manage")
        if _deployment_network_settings(existing) != _deployment_network_settings(record) or existing.domain != record.domain:
            raise HTTPException(status_code=403, detail="Permission required: network.manage")
    if existing and not record.guardrails.get("antlabs_signature_secret"):
        record.guardrails["antlabs_signature_secret"] = (existing.guardrails or {}).get("antlabs_signature_secret", "")
    try:
        record.guardrails = normalize_guardrails(record.guardrails)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if existing:
        record.design_draft = existing.design_draft
        record.design_published = existing.design_published
        record.design_versions = existing.design_versions
        record.design_revision = existing.design_revision
    else:
        record.design_draft = default_design_config(
            hotel_name=record.hotel_name,
            concierge_name=record.concierge_name,
            welcome=record.welcome,
            quick_actions=record.quick_actions,
        )
        record.design_published = record.design_draft
    saved = properties.upsert(record)
    return _property_admin_payload(saved, principal)


@app.put("/api/admin/properties/{property_id}/logo")
async def update_property_logo(property_id: str, payload: PropertyLogoPayload) -> dict[str, str]:
    logo_url = payload.logo_url
    if logo_url:
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]*={0,2})", logo_url)
        if not match:
            raise HTTPException(status_code=422, detail="Upload a PNG, JPEG, or WebP image under 500 KB.")
        try:
            image_bytes = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="The logo image is not valid base64 data.") from exc
        if not image_bytes or len(image_bytes) > 500 * 1024:
            raise HTTPException(status_code=413, detail="Logo images must be smaller than 500 KB.")
        signatures = {
            "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
            "image/webp": len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP",
        }
        if not signatures.get(match.group(1), False):
            raise HTTPException(status_code=422, detail="The file contents do not match the selected image type.")
    record = _require_property_record(property_id)
    record.logo_url = logo_url
    saved = properties.upsert(record)
    return {"logo_url": saved.logo_url}


@app.get("/api/admin/properties/{property_id}/guardrails")
async def get_property_guardrails(property_id: str, request: Request) -> dict[str, Any]:
    record = _require_property_record(property_id)
    config = public_guardrails(record.guardrails)
    if not _admin_principal(request).can("network.manage"):
        config.pop("guest_access_hosts", None)
    return {"config": config}


@app.put("/api/admin/properties/{property_id}/guardrails")
async def update_property_guardrails(property_id: str, payload: GuardrailConfigPayload, request: Request) -> dict[str, Any]:
    record = _require_property_record(property_id)
    principal = _admin_principal(request)
    secret = str((record.guardrails or {}).get("antlabs_signature_secret") or "")
    incoming = dict(payload.config)
    if not principal.can("network.manage"):
        existing_hosts = normalize_guardrails(record.guardrails)["guest_access_hosts"]
        if "guest_access_hosts" in incoming:
            try:
                requested_hosts = normalize_guest_access_hosts(incoming["guest_access_hosts"])
            except ValueError as exc:
                raise HTTPException(status_code=403, detail="Permission required: network.manage") from exc
            if requested_hosts != existing_hosts:
                raise HTTPException(status_code=403, detail="Permission required: network.manage")
        incoming["guest_access_hosts"] = existing_hosts
    if not incoming.get("antlabs_signature_secret"):
        incoming["antlabs_signature_secret"] = secret
    try:
        normalized = normalize_guardrails(incoming)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if _guest_network_settings(record.guardrails) != _guest_network_settings(normalized) and not principal.can("network.manage"):
        raise HTTPException(status_code=403, detail="Permission required: network.manage")
    record.guardrails = normalized
    properties.upsert(record)
    security_audit.record(_request_id(request), property_id, "network_policy_changed", "success", request.client.host if request.client else "", actor=principal.username)
    config = public_guardrails(record.guardrails)
    if not principal.can("network.manage"):
        config.pop("guest_access_hosts", None)
    return {"config": config}


@app.get("/api/admin/properties/{property_id}/guardrails/diagnostics")
async def property_guardrail_diagnostics(property_id: str, request: Request) -> dict[str, Any]:
    record = _require_property_record(property_id)
    decision = network_guard.evaluate(property_id, record.guardrails, request.client.host if request.client else "", request.headers, _request_id(request))
    active = sum(1 for item in store.sessions(property_id) if item["session_status"] == "active")
    return {
        "detected_client_ip": decision.client_ip,
        "matched_network": decision.matched_network or None,
        "property_id": property_id,
        "trusted_proxy": decision.trusted_proxy,
        "network_policy_result": "allowed" if decision.allowed else "denied",
        "active_guest_sessions": active,
        "recent_security_events": security_audit.list(property_id, 20),
    }


@app.get("/api/admin/properties/{property_id}/knowledge")
async def list_property_knowledge(property_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    items = operations.list_knowledge(property_id)
    return {
        "items": [item for item in items if item["kind"] == "entry"],
        "documents": [item for item in items if item["kind"] == "document"] if _admin_principal(request).can("knowledge.edit") else [],
        "faqs": [item for item in items if item["kind"] == "faq"],
    }


def _decode_knowledge_upload(payload: UploadPayload) -> bytes:
    if len(payload.content_base64) > (settings.knowledge_max_file_bytes + 2) * 4 // 3 + 16:
        raise HTTPException(status_code=413, detail="File exceeds the configured upload limit.")
    try:
        return base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="File content is not valid base64.") from exc


def _knowledge_item_allowed(item: dict[str, Any] | None, principal: AdminPrincipal) -> bool:
    if item is None:
        return False
    if principal.role_slug == "super-admin":
        return True
    visibility = item["visibility"]
    if visibility == "guest" or visibility == "staff":
        return True
    if visibility == "admin":
        return principal.role_slug in {"property-administrator", "content-manager"}
    if visibility == "manager":
        return principal.role_slug in {"property-administrator", "property-manager"}
    if visibility == "engineering":
        return principal.role_slug == "engineering"
    return visibility == "role" and item["role_slug"] == principal.role_slug


@app.get("/api/admin/properties/{property_id}/knowledge/managed")
async def managed_knowledge(property_id: str, request: Request, source_id: str | None = None, status: str | None = None, q: str = "") -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    items = [item for item in knowledge_management.list_items(property_id, source_id=source_id, status=status, query=q) if _knowledge_item_allowed(item, principal)]
    return {"items": items, "sources": knowledge_management.list_sources(property_id), "categories": list(CATEGORIES), "limits": {"max_file_bytes": settings.knowledge_max_file_bytes, "max_files_per_upload": settings.knowledge_max_files_per_upload, "max_files_per_property": settings.knowledge_max_files_per_property, "storage_quota_bytes": settings.knowledge_storage_quota_bytes}}


@app.post("/api/admin/properties/{property_id}/knowledge/items")
async def create_managed_knowledge_draft(property_id: str, payload: KnowledgeDraftPayload, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    try:
        item = knowledge_management.create_draft(property_id, payload.title, payload.content, payload.category, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    admin_auth.audit(principal, "knowledge.draft_created", "knowledge_item", item["item_id"], property_id=property_id, metadata={"category": item["category"]})
    return item


@app.get("/api/admin/properties/{property_id}/knowledge/health")
async def knowledge_health(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return knowledge_management.health(property_id)


@app.get("/api/admin/properties/{property_id}/knowledge/conflicts")
async def knowledge_conflicts(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {"conflicts": knowledge_management.conflicts(property_id)}


@app.post("/api/admin/properties/{property_id}/knowledge/conflicts/{conflict_id}/resolve")
async def resolve_knowledge_conflict(property_id: str, conflict_id: str, payload: ConflictResolutionPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    conflict = next((item for item in knowledge_management.conflicts(property_id) if item["conflict_id"] == conflict_id), None)
    if conflict and any(not _knowledge_item_allowed(knowledge_management.get_item(property_id, item_id), principal) for item_id in (conflict["item_a"], conflict["item_b"])):
        raise HTTPException(status_code=403, detail="Knowledge visibility denied.")
    try:
        result = knowledge_management.resolve_conflict(property_id, conflict_id, payload.winner_id, payload.note, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    admin_auth.audit(principal, "knowledge.conflict_resolved", "conflict", conflict_id, property_id=property_id, metadata={"winner_id": payload.winner_id})
    return result


@app.post("/api/admin/properties/{property_id}/knowledge/sources")
async def create_knowledge_source(property_id: str, payload: UploadPayload, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    try:
        source = knowledge_management.upload(property_id, payload.filename, payload.content_type, _decode_knowledge_upload(payload), principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(knowledge_management.process, property_id, source["source_id"])
    admin_auth.audit(principal, "knowledge.source_uploaded", "knowledge_source", source["source_id"], property_id=property_id, metadata={"filename": source["filename"], "bytes": source["file_bytes"]})
    return source


@app.get("/api/admin/properties/{property_id}/knowledge/sources/{source_id}")
async def get_knowledge_source(property_id: str, source_id: str, request: Request) -> dict[str, Any]:
    source = knowledge_management.get_source(property_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Document not found.")
    principal = _admin_principal(request)
    items = [item for item in knowledge_management.list_items(property_id, source_id=source_id) if _knowledge_item_allowed(item, principal)]
    return {"source": source, "items": items}


@app.get("/api/admin/properties/{property_id}/knowledge/sources/{source_id}/versions")
async def get_knowledge_source_versions(property_id: str, source_id: str) -> dict[str, Any]:
    if not knowledge_management.get_source(property_id, source_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    sources = knowledge_management.list_sources(property_id)
    lineage = {source_id}
    changed = True
    while changed:
        changed = False
        for source in sources:
            if source["source_id"] in lineage and source["previous_source_id"] and source["previous_source_id"] not in lineage:
                lineage.add(source["previous_source_id"]); changed = True
            if source["previous_source_id"] in lineage and source["source_id"] not in lineage:
                lineage.add(source["source_id"]); changed = True
    return {"versions": sorted((source for source in sources if source["source_id"] in lineage), key=lambda source: source["version"])}


@app.get("/api/admin/properties/{property_id}/knowledge/sources/{source_id}/download")
async def download_knowledge_source(property_id: str, source_id: str, request: Request) -> FileResponse:
    principal = _admin_principal(request)
    if not principal.can("knowledge.edit") or principal.role_slug not in {"super-admin", "property-administrator", "content-manager"}:
        raise HTTPException(status_code=403, detail="Original source download requires administrator access.")
    source = knowledge_management.get_source(property_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(knowledge_management._file_path(property_id, source_id), media_type=source["content_type"], filename=source["filename"])


@app.post("/api/admin/properties/{property_id}/knowledge/sources/{source_id}/retry")
async def retry_knowledge_source(property_id: str, source_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    source = knowledge_management.get_source(property_id, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Document not found.")
    if source["status"] != "processing_failed":
        raise HTTPException(status_code=409, detail="Only failed documents can be retried.")
    background_tasks.add_task(knowledge_management.process, property_id, source_id)
    return {"status": "queued", "source_id": source_id}


@app.post("/api/admin/properties/{property_id}/knowledge/sources/{source_id}/replace")
async def replace_knowledge_source(property_id: str, source_id: str, payload: UploadPayload, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    principal = _admin_principal(request)
    if any(not _knowledge_item_allowed(item, principal) for item in knowledge_management.list_items(property_id, source_id=source_id)):
        raise HTTPException(status_code=403, detail="Knowledge visibility denied.")
    if any(item["status"] == "published" for item in knowledge_management.list_items(property_id, source_id=source_id)) and not principal.can("knowledge.publish"):
        raise HTTPException(status_code=403, detail="Permission required: knowledge.publish")
    try:
        source = knowledge_management.replace(property_id, source_id, payload.filename, payload.content_type, _decode_knowledge_upload(payload), principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(knowledge_management.process, property_id, source["source_id"])
    admin_auth.audit(principal, "knowledge.source_replaced", "knowledge_source", source["source_id"], property_id=property_id, metadata={"previous_source_id": source_id})
    return source


@app.post("/api/admin/properties/{property_id}/knowledge/sources/{source_id}/supersede")
async def supersede_knowledge_source(property_id: str, source_id: str, request: Request) -> dict[str, str]:
    principal = _admin_principal(request)
    if any(not _knowledge_item_allowed(item, principal) for item in knowledge_management.list_items(property_id, source_id=source_id)):
        raise HTTPException(status_code=403, detail="Knowledge visibility denied.")
    try:
        knowledge_management.supersede(property_id, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    admin_auth.audit(principal, "knowledge.source_superseded", "knowledge_source", source_id, property_id=property_id)
    return {"status": "superseded"}


@app.delete("/api/admin/properties/{property_id}/knowledge/sources/{source_id}")
async def delete_knowledge_source(property_id: str, source_id: str, request: Request) -> dict[str, str]:
    if not knowledge_management.delete_source(property_id, source_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    principal = _admin_principal(request)
    admin_auth.audit(principal, "knowledge.source_deleted", "knowledge_source", source_id, property_id=property_id)
    return {"status": "deleted"}


@app.get("/api/admin/properties/{property_id}/knowledge/items/{item_id}")
async def get_managed_knowledge_item(property_id: str, item_id: str, request: Request) -> dict[str, Any]:
    item = knowledge_management.get_item(property_id, item_id)
    if not item or not _knowledge_item_allowed(item, _admin_principal(request)):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    return item


@app.patch("/api/admin/properties/{property_id}/knowledge/items/{item_id}")
async def edit_managed_knowledge_item(property_id: str, item_id: str, payload: KnowledgeItemUpdatePayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    current = knowledge_management.get_item(property_id, item_id)
    if not current or not _knowledge_item_allowed(current, principal):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    try:
        updated = knowledge_management.update_item(property_id, item_id, payload.model_dump(exclude_unset=True), principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    admin_auth.audit(principal, "knowledge.item_edited", "knowledge_item", item_id, property_id=property_id, metadata={"fields": list(payload.model_fields_set), "before": {key: current[key] for key in ("category", "visibility", "effective_at", "expires_at")}, "after": {key: updated[key] for key in ("category", "visibility", "effective_at", "expires_at")}})
    return updated


@app.post("/api/admin/properties/{property_id}/knowledge/items/{item_id}/approve")
@app.post("/api/admin/properties/{property_id}/knowledge/items/{item_id}/publish")
@app.post("/api/admin/properties/{property_id}/knowledge/items/{item_id}/unpublish")
@app.post("/api/admin/properties/{property_id}/knowledge/items/{item_id}/archive")
async def transition_managed_knowledge_item(property_id: str, item_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    current = knowledge_management.get_item(property_id, item_id)
    if not current or not _knowledge_item_allowed(current, principal):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    action = request.url.path.rsplit("/", 1)[-1]
    if action == "archive" and not principal.can("knowledge.publish"):
        raise HTTPException(status_code=403, detail="Permission required: knowledge.publish")
    status = {"approve": "approved", "publish": "published", "unpublish": "ready_review", "archive": "archived"}[action]
    try:
        item = knowledge_management.set_status(property_id, item_id, status, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    admin_auth.audit(principal, f"knowledge.item_{action}", "knowledge_item", item_id, property_id=property_id, metadata={"visibility": item["visibility"], "before_status": current["status"], "after_status": item["status"]})
    return item


@app.put("/api/admin/properties/{property_id}/knowledge")
async def save_property_knowledge(property_id: str, payload: KnowledgePayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return operations.save_knowledge(property_id, payload.model_dump(), payload.item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/knowledge/documents")
async def upload_knowledge_document(property_id: str, payload: UploadPayload, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    return await create_knowledge_source(property_id, payload, request, background_tasks)


@app.delete("/api/admin/properties/{property_id}/knowledge/{item_id}")
async def delete_property_knowledge(property_id: str, item_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not operations.delete_knowledge(property_id, item_id):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    return {"status": "deleted"}


@app.get("/api/admin/properties/{property_id}/webhooks")
async def list_property_webhooks(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {
        "webhooks": operations.list_webhooks(property_id),
        "deliveries": operations.list_webhook_deliveries(property_id),
        "supported_events": [
            "guest.session.started",
            "guest.request.created",
            "guest.request.updated",
        ],
    }


@app.put("/api/admin/properties/{property_id}/webhooks")
async def save_property_webhook(property_id: str, payload: WebhookPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        clean = payload.model_dump()
        clean["endpoint_url"] = InternetGuard.validate_url(payload.endpoint_url)
        return operations.save_webhook(property_id, clean, payload.webhook_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/webhooks/{webhook_id}")
async def delete_property_webhook(property_id: str, webhook_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not operations.delete_webhook(property_id, webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found.")
    return {"status": "deleted"}


@app.post("/api/admin/properties/{property_id}/webhooks/{webhook_id}/test")
async def test_property_webhook(property_id: str, webhook_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    webhook = operations.get_webhook(property_id, webhook_id, include_secret=True)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    try:
        endpoint_url = InternetGuard.validate_url(webhook["endpoint_url"])
    except ValueError as exc:
        security_audit.record(_request_id(request), property_id, "ssrf_blocked", "denied", request.client.host if request.client else "", resource="webhook")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    body = json.dumps({"event": "concierge.webhook.test", "property_id": property_id, "timestamp": int(time.time())}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Concierge.Ai-Webhooks/1.0"}
    if webhook.get("secret"):
        headers["X-Concierge-Signature"] = "sha256=" + hmac.new(webhook["secret"].encode("utf-8"), body, hashlib.sha256).hexdigest()
    try:
        response = await _outbound_broker(property_id, _request_id(request)).post(endpoint_url, content=body, headers=headers)
        status = "delivered" if 200 <= response.status_code < 300 else "failed"
        error = "" if status == "delivered" else f"Endpoint returned HTTP {response.status_code}."
        return operations.record_webhook_delivery(property_id, webhook_id, "concierge.webhook.test", status, response.status_code, error)
    except OutboundRequestError as exc:
        return operations.record_webhook_delivery(property_id, webhook_id, "concierge.webhook.test", "failed", error=str(exc))


@app.get("/api/admin/properties/{property_id}/deployment/status")
async def property_deployment_status(property_id: str) -> dict[str, Any]:
    record = _require_property_record(property_id)
    return _deployment_status(record)


@app.post("/api/admin/properties/{property_id}/deployment/verify")
async def verify_property_deployment(property_id: str) -> dict[str, Any]:
    record = _require_property_record(property_id)
    result = await _verify_deployment(record)
    app_settings = dict(record.app_settings or {})
    deployment = dict(app_settings.get("deployment") or {})
    deployment["last_verification"] = result
    app_settings["deployment"] = deployment
    record.app_settings = app_settings
    properties.upsert(record)
    return result


@app.get("/api/admin/properties/{property_id}/network-access/status")
async def network_access_status(property_id: str, request: Request) -> dict[str, Any]:
    record = _require_property_record(property_id)
    principal = _admin_principal(request)
    return _network_access_status(record, principal)


@app.put("/api/admin/properties/{property_id}/network-access/management")
async def save_management_network_access(
    property_id: str,
    payload: ManagementAccessPayload,
    request: Request,
) -> dict[str, Any]:
    record = _require_property_record(property_id)
    principal = _admin_principal(request)
    if principal.role_slug != "super-admin":
        raise HTTPException(status_code=403, detail="Installation-wide management networks require a Super Admin.")

    try:
        candidate = normalize_management_access(
            payload.model_dump(),
            default_allowed_cidrs=(),
            default_trusted_proxy_ranges=(),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    current_raw = _effective_management_access_settings()
    current = normalize_management_access(current_raw, default_allowed_cidrs=(), default_trusted_proxy_ranges=())
    guest_ranges = normalize_guardrails(record.guardrails).get("allowed_cidrs", [])
    unsafe = unsafe_management_networks(candidate["management_allowed_cidrs"])
    overlaps = find_network_overlaps(guest_ranges, candidate["management_allowed_cidrs"])
    current_source = management_access_guard.evaluate(
        request.client.host if request.client else "",
        request.headers,
        candidate,
    )
    lockout = candidate["management_access_enabled"] and not current_source.allowed
    required: list[str] = []
    warnings: list[str] = []
    if unsafe:
        required.append("confirm_unsafe")
        warnings.append("A /0 or public management network can expose Admin outside the hotel's private networks.")
    if not candidate["management_access_enabled"]:
        required.append("confirm_public_exposure")
        warnings.append("Disabling Management Access removes the network restriction from Admin and metrics endpoints.")
    if overlaps:
        required.append("confirm_overlap")
        warnings.append("Management and guest networks overlap: " + ", ".join(f"{management} overlaps {guest}" for guest, management in overlaps) + ".")
    if lockout:
        required.append("confirm_lockout")
        warnings.append("The current administrator source IP is outside the new management allow list. Saving will block this administrator after this response.")
    missing = [key for key in required if not getattr(payload, key)]
    if missing:
        raise HTTPException(
            status_code=409,
            detail={"code": "network_access_confirmation_required", "confirmations": missing, "warnings": warnings},
        )

    if lockout:
        candidate["_rollback_config"] = current
        candidate["_rollback_deadline"] = int(time.time()) + 600
    operations.save_network_access_settings(candidate)
    _audit_management_network_changes(
        principal,
        property_id,
        request,
        current,
        normalize_management_access(candidate, default_allowed_cidrs=(), default_trusted_proxy_ranges=()),
    )
    return {
        "management": _network_access_status(record, principal)["management"],
        "warnings": warnings,
        "rollback_pending": bool(lockout),
    }


@app.post("/api/admin/properties/{property_id}/network-access/management/finalize")
async def finalize_management_network_access(property_id: str, request: Request) -> dict[str, bool]:
    _require_property_record(property_id)
    principal = _admin_principal(request)
    if principal.role_slug != "super-admin":
        raise HTTPException(status_code=403, detail="Installation-wide management networks require a Super Admin.")
    current = operations.get_network_access_settings(_default_management_access_settings())
    current.pop("_rollback_config", None)
    current.pop("_rollback_deadline", None)
    operations.save_network_access_settings(current)
    admin_auth.audit(principal, "management_access_change_finalized", "network_access", property_id, property_id=property_id, ip_address=request.client.host if request.client else "")
    return {"rollback_pending": False}


@app.put("/api/admin/properties/{property_id}/network-access/guest")
async def save_guest_network_access(
    property_id: str,
    payload: GuestNetworkAccessPayload,
    request: Request,
) -> dict[str, Any]:
    record = _require_property_record(property_id)
    principal = _admin_principal(request)
    old_guardrails = normalize_guardrails(record.guardrails)
    old_deployment = dict((record.app_settings or {}).get("deployment") or {})
    try:
        domain = _validated_guest_domain(payload.guest_domain)
        guest_hosts = (
            normalize_guest_access_hosts(payload.guest_access_hosts)
            if "guest_access_hosts" in payload.model_fields_set
            else old_guardrails["guest_access_hosts"]
        )
        cidrs = normalize_cidrs(payload.allowed_cidrs, "allowed_cidrs")
        proxies = normalize_cidrs(payload.trusted_proxy_ranges, "trusted_proxy_ranges")
        antlabs_ranges = normalize_cidrs(payload.antlabs_gateway_ranges, "antlabs_gateway_ranges")
        if payload.session_network_revalidation not in {"suspend", "expire"}:
            raise ValueError("session_network_revalidation must be 'suspend' or 'expire'.")
        guest_url = _validated_guest_url(payload.guest_url, domain, payload.guest_https_required)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    management = _effective_management_access_settings()
    overlaps = find_network_overlaps(cidrs, management.get("management_allowed_cidrs", []))
    if overlaps and not payload.confirm_overlap:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "network_access_confirmation_required",
                "confirmations": ["confirm_overlap"],
                "warnings": ["Guest and management networks overlap: " + ", ".join(f"{guest} overlaps {admin}" for guest, admin in overlaps) + "."],
            },
        )

    next_guardrails = dict(record.guardrails or {})
    next_guardrails.update(
        {
            "guest_network_only": payload.guest_network_only,
            "guest_access_hosts": guest_hosts,
            "allowed_cidrs": cidrs,
            "trusted_proxy_ranges": proxies,
            "session_network_revalidation": payload.session_network_revalidation,
            "guest_session_timeout": payload.guest_session_timeout,
            "antlabs_gateway_enabled": payload.antlabs_gateway_enabled,
            "antlabs_gateway_ranges": antlabs_ranges,
        }
    )
    try:
        next_guardrails = normalize_guardrails(next_guardrails)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    app_settings = dict(record.app_settings or {})
    deployment = dict(old_deployment)
    previous_domain = str(record.domain or "")
    deployment.update(
        {
            "guest_access_enabled": payload.guest_access_enabled,
            "public_base_url": guest_url,
            "reverse_proxy": payload.reverse_proxy,
            "https_required": payload.guest_https_required,
            # Keep the historical single-proxy field synchronized for older deployments.
            "trusted_proxy": proxies[0] if proxies else "",
        }
    )
    if domain != previous_domain:
        deployment.pop("last_verification", None)
    app_settings["deployment"] = deployment
    record.domain = domain
    record.guardrails = next_guardrails
    record.app_settings = app_settings
    properties.upsert(record)
    _audit_guest_network_changes(
        principal,
        property_id,
        request,
        previous_domain,
        domain,
        old_guardrails,
        next_guardrails,
        old_deployment,
        deployment,
    )
    return _network_access_status(record, principal)


@app.get("/api/admin/system/email")
async def get_system_email_settings() -> dict[str, Any]:
    return operations.get_email_settings()


@app.put("/api/admin/system/email")
async def save_system_email_settings(payload: EmailSettingsPayload) -> dict[str, Any]:
    try:
        return operations.save_email_settings(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/system/email/test")
async def test_system_email_settings() -> dict[str, Any]:
    config = operations.get_email_settings(include_secret=True)
    if not config.get("enabled"):
        return {"status": "not_configured", "detail": "Enable SMTP and save the required settings first."}
    try:
        await asyncio.to_thread(_smtp_probe, config)
        return {"status": "connected", "detail": "SMTP connection and authentication succeeded."}
    except Exception as exc:
        return {"status": "failed", "detail": str(exc)[:500]}


@app.get("/api/admin/properties/{property_id}/design")
async def get_property_design(property_id: str) -> dict[str, Any]:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return {
        "property_id": property_id,
        "draft": record.design_draft,
        "published": record.design_published,
        "revision": record.design_revision,
        "component_registry": COMPONENT_REGISTRY,
        "versions": [
            {
                "version": item.get("version"),
                "published_at": item.get("published_at"),
                "published_by": item.get("published_by"),
            }
            for item in record.design_versions
        ],
    }


@app.get("/api/admin/properties/{property_id}/ai")
async def get_property_ai(property_id: str) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return {
        "settings": ai_provider_store.get_settings(property_id),
        "providers": ai_provider_store.list_connections(property_id),
    }


@app.put("/api/admin/properties/{property_id}/ai/settings")
async def save_property_ai_settings(property_id: str, payload: AISettingsPayload) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    try:
        settings_payload = ai_provider_store.save_settings(property_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"settings": settings_payload, "providers": ai_provider_store.list_connections(property_id)}


@app.put("/api/admin/properties/{property_id}/ai/providers/{provider_id}")
async def save_property_ai_provider(property_id: str, provider_id: str, payload: AIProviderPayload) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    try:
        provider = ai_provider_store.save_connection(property_id, provider_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"provider": provider}


@app.post("/api/admin/properties/{property_id}/ai/providers/{provider_id}/credentials")
async def save_property_ai_credential(property_id: str, provider_id: str, payload: CredentialPayload) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    ai_provider_store.save_credential(property_id, provider_id, payload.credential_type, payload.value)
    return {"provider": ai_provider_store.get_connection(property_id, provider_id)}


@app.delete("/api/admin/properties/{property_id}/ai/providers/{provider_id}/credentials/{credential_type}")
async def delete_property_ai_credential(property_id: str, provider_id: str, credential_type: str) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    ai_provider_store.remove_credential(property_id, provider_id, credential_type)
    return {"provider": ai_provider_store.get_connection(property_id, provider_id)}


@app.post("/api/admin/properties/{property_id}/ai/providers/{provider_id}/models/refresh")
async def refresh_property_ai_models(property_id: str, provider_id: str) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    try:
        models = await ai_models.list_models(property_id, provider_id)
        ai_provider_store.save_discovered_models(property_id, provider_id, models)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"models": models}


@app.post("/api/admin/properties/{property_id}/ai/providers/{provider_id}/test")
async def test_property_ai_provider(property_id: str, provider_id: str) -> dict[str, Any]:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return await ai_models.test_connection(property_id, provider_id)


@app.put("/api/admin/properties/{property_id}/design/draft")
async def save_property_design_draft(property_id: str, payload: DesignConfigPayload) -> dict[str, Any]:
    try:
        record = properties.save_design_draft(property_id, payload.config, payload.expected_revision)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.") from None
    except ValueError as exc:
        if isinstance(exc, DesignRevisionConflict):
            raise HTTPException(status_code=409, detail={"message": str(exc), "current_revision": exc.current_revision}) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "draft_saved", "draft": record.design_draft, "revision": record.design_revision}


@app.post("/api/admin/properties/{property_id}/design/publish")
async def publish_property_design(property_id: str, payload: DesignPublishPayload | None = None) -> dict[str, Any]:
    try:
        record = properties.publish_design(property_id, expected_revision=payload.expected_revision if payload else None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.") from None
    except ValueError as exc:
        if isinstance(exc, DesignRevisionConflict):
            raise HTTPException(status_code=409, detail={"message": str(exc), "current_revision": exc.current_revision}) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    latest = record.design_versions[-1] if record.design_versions else {}
    return {
        "status": "published",
        "published": record.design_published,
        "version": latest.get("version"),
        "published_at": latest.get("published_at"),
        "revision": record.design_revision,
    }


@app.post("/api/admin/properties/{property_id}/design/discard")
async def discard_property_design(property_id: str, payload: DesignPublishPayload | None = None) -> dict[str, Any]:
    try:
        record = properties.discard_design(property_id, payload.expected_revision if payload else None)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.")
    except ValueError as exc:
        if isinstance(exc, DesignRevisionConflict):
            raise HTTPException(status_code=409, detail={"message": str(exc), "current_revision": exc.current_revision}) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "discarded", "draft": record.design_draft, "revision": record.design_revision}


@app.post("/api/admin/properties/{property_id}/design/restore")
async def restore_property_design(property_id: str, payload: RestoreDesignPayload) -> dict[str, Any]:
    try:
        record = properties.restore_design_version(property_id, payload.version, payload.expected_revision)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.") from None
    except ValueError as exc:
        if isinstance(exc, DesignRevisionConflict):
            raise HTTPException(status_code=409, detail={"message": str(exc), "current_revision": exc.current_revision}) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "restored_to_draft", "draft": record.design_draft, "revision": record.design_revision}


@app.delete("/api/admin/properties/{property_id}")
async def delete_property(property_id: str) -> dict[str, Any]:
    if settings.property_id and property_id == settings.property_id:
        raise HTTPException(status_code=400, detail="The configured property cannot be deleted.")
    deleted = properties.delete(property_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Property not found.")
    return {"status": "deleted", "property_id": property_id}


@app.get("/api/admin/properties/{property_id}/zones")
async def admin_zones(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return zones.overview(property_id)


@app.post("/api/admin/properties/{property_id}/buildings")
async def create_building(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_building(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/floors")
async def create_floor(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_floor(property_id, payload.data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/floors/{floor_id}/maps")
async def upload_floor_map(property_id: str, floor_id: str, payload: UploadPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.save_floor_map(property_id, floor_id, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/floor-maps/{map_id}/asset")
async def floor_map_asset(property_id: str, map_id: str) -> FileResponse:
    _require_property(property_id)
    try:
        return _floor_map_file_response(zones.floor_map_path(property_id, map_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/zones")
async def save_zone(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.upsert_zone(property_id, payload.data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/zones/{zone_id}")
async def delete_zone(property_id: str, zone_id: str) -> dict[str, Any]:
    _require_property(property_id)
    deleted = zones.delete_zone(property_id, zone_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Zone not found.")
    return {"status": "deleted", "zone_id": zone_id}


@app.post("/api/admin/properties/{property_id}/facilities")
async def create_facility(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_facility(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/facilities/{facility_id}")
async def update_facility(property_id: str, facility_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.update_facility(property_id, facility_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/facilities/{facility_id}")
async def delete_facility(property_id: str, facility_id: str) -> dict[str, Any]:
    _require_property(property_id)
    if not zones.delete_map_record(property_id, "facility", facility_id):
        raise HTTPException(status_code=404, detail="Facility not found.")
    return {"status": "deleted", "facility_id": facility_id}


@app.post("/api/admin/properties/{property_id}/access-points")
async def create_access_point(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_access_point(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/access-points/{access_point_id}")
async def update_access_point(property_id: str, access_point_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.update_access_point(property_id, access_point_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/access-points/{access_point_id}")
async def delete_access_point(property_id: str, access_point_id: str) -> dict[str, Any]:
    _require_property(property_id)
    if not zones.delete_map_record(property_id, "access_point", access_point_id):
        raise HTTPException(status_code=404, detail="Access point not found.")
    return {"status": "deleted", "access_point_id": access_point_id}


@app.post("/api/admin/properties/{property_id}/navigation/nodes")
async def create_navigation_node(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_node(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/navigation/nodes/{node_id}")
async def update_navigation_node(property_id: str, node_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.update_node(property_id, node_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/navigation/nodes/{node_id}")
async def delete_navigation_node(property_id: str, node_id: str) -> dict[str, Any]:
    _require_property(property_id)
    if not zones.delete_map_record(property_id, "navigation_node", node_id):
        raise HTTPException(status_code=404, detail="Navigation point not found.")
    return {"status": "deleted", "node_id": node_id}


@app.post("/api/admin/properties/{property_id}/navigation/edges")
async def create_navigation_edge(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_edge(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/navigation/edges/{edge_id}")
async def update_navigation_edge(property_id: str, edge_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.update_edge(property_id, edge_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/navigation/edges/{edge_id}")
async def delete_navigation_edge(property_id: str, edge_id: str) -> dict[str, Any]:
    _require_property(property_id)
    if not zones.delete_map_record(property_id, "navigation_edge", edge_id):
        raise HTTPException(status_code=404, detail="Navigation route not found.")
    return {"status": "deleted", "edge_id": edge_id}


@app.get("/api/admin/properties/{property_id}/navigation/route")
async def admin_route(property_id: str, from_node_id: str, to_node_id: str) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.route(property_id, from_node_id, to_node_id, guest=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/sessions")
async def admin_sessions(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {
        "sessions": store.sessions(property_id),
        "stays": guest_identities.list_stays(property_id),
        "guest_sessions": guest_identities.list_guest_sessions(property_id),
        "devices": guest_identities.list_devices(property_id),
    }


@app.get("/api/admin/properties/{property_id}/conversations")
async def property_conversations(property_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    if not principal.can("conversations.view") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Permission required: conversations.view")
    restaurant_ids = None if principal.can("properties.all") or principal.can("properties.edit") else _assigned_restaurant_ids(principal, property_id)
    conversations = store.conversations(property_id, restaurant_ids)
    for conversation in conversations:
        restaurant_id = conversation.get("restaurant_id")
        restaurant = hospitality.get_restaurant(property_id, restaurant_id) if restaurant_id else None
        conversation["restaurant_name"] = restaurant["name"] if restaurant else "Hotel team"
        assigned = admin_auth.get_user(conversation["assigned_user_id"]) if conversation.get("assigned_user_id") else None
        conversation["assigned_user_name"] = assigned["display_name"] if assigned else ""
        # Guest chat is private. A restaurant escalation exposes only the reason
        # the guest explicitly submitted, along with staff replies.
        conversation["messages"] = [message for message in conversation.get("messages", []) if message.get("role") == "staff"]
        conversation["message_count"] = len(conversation["messages"]) + int(bool(conversation.get("escalation_reason")))
    return {"conversations": conversations, "retention": store.retention(property_id)}


@app.get("/api/admin/properties/{property_id}/conversations/retention")
async def get_conversation_retention(property_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("guest_sessions.view") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Permission required: guest_sessions.view")
    _require_property(property_id)
    return store.retention(property_id)


@app.put("/api/admin/properties/{property_id}/conversations/retention")
async def set_conversation_retention(property_id: str, payload: ConversationRetentionPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("guest_sessions.manage") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Permission required: guest_sessions.manage")
    _require_property(property_id)
    return store.set_retention(property_id, payload.retention_days)


@app.put("/api/admin/properties/{property_id}/conversations/{session_id}")
async def update_conversation_state(property_id: str, session_id: str, payload: ConversationStatePayload, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="This account cannot access that property.")
    state = store.conversation_state(session_id, property_id)
    if state["restaurant_id"]:
        permission = (
            "conversations.takeover" if payload.human_takeover else
            "conversations.resolve" if payload.status == "closed" else
            "conversations.return_to_ai"
        )
        _require_restaurant_access(principal, property_id, state["restaurant_id"], permission, allow_archived=True)
        try:
            if payload.human_takeover:
                if principal.can("properties.all") or principal.can("properties.edit"):
                    return store.set_conversation_state(session_id, property_id, payload.status, True, actor_user_id=principal.user_id)
                return store.accept_conversation(session_id, property_id, principal.user_id)
            if payload.status == "closed":
                return store.resolve_conversation(session_id, property_id, principal.user_id, allow_unassigned=principal.can("properties.all") or principal.can("properties.edit") or principal.can("conversations.assign"))
            return store.return_conversation_to_ai(session_id, property_id, principal.user_id, allow_unassigned=principal.can("properties.all") or principal.can("properties.edit") or principal.can("conversations.assign"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not (principal.can("properties.all") or principal.can("properties.edit")):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    try:
        return store.set_conversation_state(session_id, property_id, payload.status, payload.human_takeover, actor_user_id=principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/conversations/{session_id}/messages")
async def staff_conversation_reply(property_id: str, session_id: str, payload: StaffReplyPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_property(property_id)
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="This account cannot access that property.")
    session = store.get(session_id)
    if session is None or session.property_id != property_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    state = store.conversation_state(session_id, property_id)
    if state["restaurant_id"]:
        _require_restaurant_access(principal, property_id, state["restaurant_id"], "conversations.reply", allow_archived=True)
    elif not (principal.can("properties.all") or principal.can("properties.edit")):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    try:
        return store.reply_to_conversation(session_id, property_id, principal.user_id, payload.message, allow_unassigned=principal.can("properties.all") or principal.can("properties.edit") or principal.can("conversations.assign"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/conversations/{session_id}/accept")
async def accept_restaurant_conversation(property_id: str, session_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    state = store.conversation_state(session_id, property_id)
    if not state["restaurant_id"]:
        raise HTTPException(status_code=404, detail="Restaurant conversation not found.")
    _require_restaurant_access(principal, property_id, state["restaurant_id"], "conversations.takeover")
    try:
        return store.accept_conversation(session_id, property_id, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/conversations/{session_id}/assign")
async def assign_restaurant_conversation(property_id: str, session_id: str, payload: ConversationAssignPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    state = store.conversation_state(session_id, property_id)
    restaurant_id = state["restaurant_id"]
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Restaurant conversation not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "conversations.assign")
    user = admin_auth.get_user(payload.user_id)
    role = admin_auth.get_role(user["role_id"]) if user else None
    if (
        not user or user["status"] != "active" or user["property_id"] != property_id or not role
        or "conversations.takeover" not in role["permissions"] or restaurant_id not in user["restaurant_ids"]
    ):
        raise HTTPException(status_code=422, detail="The selected staff member is not assigned to this restaurant.")
    try:
        return store.assign_conversation(session_id, property_id, payload.user_id, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc


@app.post("/api/admin/properties/{property_id}/conversations/{session_id}/resolve")
async def resolve_restaurant_conversation(property_id: str, session_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    state = store.conversation_state(session_id, property_id)
    if not state["restaurant_id"]:
        raise HTTPException(status_code=404, detail="Restaurant conversation not found.")
    _require_restaurant_access(principal, property_id, state["restaurant_id"], "conversations.resolve", allow_archived=True)
    try:
        return store.resolve_conversation(session_id, property_id, principal.user_id, allow_unassigned=principal.can("properties.all") or principal.can("properties.edit") or principal.can("conversations.assign"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/conversations/{session_id}/return-to-ai")
async def return_restaurant_conversation_to_ai(property_id: str, session_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    state = store.conversation_state(session_id, property_id)
    if not state["restaurant_id"]:
        raise HTTPException(status_code=404, detail="Restaurant conversation not found.")
    _require_restaurant_access(principal, property_id, state["restaurant_id"], "conversations.return_to_ai", allow_archived=True)
    try:
        return store.return_conversation_to_ai(session_id, property_id, principal.user_id, allow_unassigned=principal.can("properties.all") or principal.can("properties.edit") or principal.can("conversations.assign"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/ai/usage")
async def property_ai_usage(property_id: str, days: int = 7) -> dict[str, Any]:
    _require_property(property_id)
    return store.operational_metrics(property_id, days)


@app.get("/api/admin/properties/{property_id}/antlabs/status")
async def antlabs_status(property_id: str) -> dict[str, Any]:
    record = _require_property_record(property_id)
    status = antlabs.configuration_status()
    authentication = record.public_profile.get("authentication", {})
    return {
        **status,
        "property_authentication_enabled": bool(authentication.get("enabled")),
        "property_authentication_types": [
            item.get("id") for item in authentication.get("enabled_types", [])
        ],
    }


@app.post("/api/admin/properties/{property_id}/antlabs/test")
async def test_antlabs_connection(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return await antlabs.test_connection()


@app.post("/api/admin/properties/{property_id}/sessions/reconnect")
async def reconnect_session(property_id: str, payload: DeviceSessionPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        device_id = guest_identities.observe_device(property_id, payload.raw_mac)
        stay = guest_identities.reconnect_or_create_stay(
            property_id,
            device_id,
            concierge_session_id=payload.concierge_session_id,
            antlabs_session_id=payload.antlabs_session_id,
            browser_session_id=payload.browser_session_id,
            room=payload.room,
            pms_guest_id=payload.pms_guest_id,
            retention_days=payload.retention_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"device_id": device_id, "stay": stay}


@app.put("/api/admin/properties/{property_id}/stays/{stay_id}/memory")
async def update_stay_memory(property_id: str, stay_id: str, payload: MemoryPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return guest_identities.update_memory(property_id, stay_id, payload.memory)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/stays/{stay_id}/checkout")
async def checkout_stay(property_id: str, stay_id: str) -> dict[str, Any]:
    _require_property(property_id)
    try:
        linked_sessions = guest_identities.sessions_for_stay(property_id, stay_id)
        result = guest_identities.checkout(property_id, stay_id, anonymize=True)
        policy = personalization.policy(property_id)
        personalization.checkout(property_id, linked_sessions, delete_profile=bool(policy["delete_profile_at_checkout"]))
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/location/observations")
async def record_location_observation(property_id: str, payload: ObservationPayload) -> dict[str, Any]:
    _require_property(property_id)
    zone = zones.zone_for_ap(property_id, payload.access_point_identifier)
    if zone is None:
        raise HTTPException(status_code=404, detail="Access point is not mapped to a zone.")
    if payload.device_id:
        device_id = payload.device_id
    elif payload.raw_mac:
        try:
            device_id = guest_identities.observe_device(property_id, payload.raw_mac)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=422, detail="raw_mac or device_id is required.")
    return location_analytics.record_observation(
        property_id,
        device_id,
        zone["zone_id"],
        payload.access_point_identifier,
        stay_id=payload.stay_id,
        observed_at=payload.observed_at,
    )


@app.get("/api/admin/properties/{property_id}/location/live")
async def live_location_analytics(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return location_analytics.live(property_id)


@app.post("/api/admin/properties/{property_id}/location/report")
async def location_report(property_id: str, payload: AnalyticsQuery) -> dict[str, Any]:
    _require_property(property_id)
    return location_analytics.aggregate(property_id, payload.start_at, payload.end_at, payload.filters)


@app.get("/api/admin/properties/{property_id}/intro")
async def get_intro(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return intro_experiences.get(property_id)


@app.put("/api/admin/properties/{property_id}/intro")
async def save_intro(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return intro_experiences.save(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/intro/upload")
async def upload_intro(property_id: str, payload: UploadPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return intro_experiences.upload_asset(property_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/intro/asset")
async def remove_intro_asset(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return intro_experiences.remove_asset(property_id)


@app.get("/api/admin/properties/{property_id}/intro/assets/{filename}")
async def intro_asset(property_id: str, filename: str) -> FileResponse:
    _require_property(property_id)
    try:
        return FileResponse(intro_experiences.asset_path(property_id, filename))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/intro/assets/{filename}")
async def delete_intro_asset_file(property_id: str, filename: str) -> dict[str, Any]:
    _require_property(property_id)
    try:
        deleted = intro_experiences.delete_asset_file(property_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Intro asset not found.")
    return {"status": "deleted", "filename": Path(filename).name}


@app.get("/api/admin/properties/{property_id}/hospitality")
async def hospitality_overview(property_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    all_restaurants = principal.can("properties.all") or principal.can("properties.edit")
    assigned_ids = None if all_restaurants else _assigned_restaurant_ids(principal, property_id)
    department_id = principal.department_id if principal.role_slug == "department-manager" else None
    overview = hospitality.overview(property_id, assigned_ids, department_id)
    if department_id is not None:
        catalog = hospitality.catalog(property_id, department_id=department_id)
        return {
            "service_requests": overview.get("service_requests", []),
            "departments": catalog["departments"],
            "services": catalog["services"],
        }
    if not all_restaurants:
        allowed_facilities = {item.get("facility_id") for item in overview.get("restaurants", []) if item.get("facility_id")}
        facilities = [item for item in overview.get("facilities", []) if item.get("facility_id") in allowed_facilities]
        for restaurant in overview.get("restaurants", []):
            restaurant.pop("internal_notes", None)
        overview = {
            "facilities": facilities,
            "restaurants": overview.get("restaurants", []),
            "menus": overview.get("menus", {}),
            "promotions": overview.get("promotions", []),
        }
    if not principal.can("requests.view"):
        overview.pop("service_requests", None)
        overview.pop("notification_rules", None)
    return overview


@app.get("/api/admin/properties/{property_id}/service-catalog")
async def admin_service_catalog(property_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    department_id = principal.department_id if principal.role_slug == "department-manager" else None
    return hospitality.catalog(property_id, department_id=department_id)


@app.put("/api/admin/properties/{property_id}/departments")
async def save_department(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.upsert_department(property_id, payload.data)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/departments/{department_id}")
async def delete_department(property_id: str, department_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not hospitality.delete_department(property_id, department_id):
        raise HTTPException(status_code=404, detail="Department not found.")
    return {"status": "deleted"}


@app.put("/api/admin/properties/{property_id}/service-catalog")
async def save_catalog_service(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.upsert_service(property_id, payload.data)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/service-catalog/{service_id}/duplicate")
async def duplicate_catalog_service(property_id: str, service_id: str) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.duplicate_service(property_id, service_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, KeyError) else 422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/service-catalog/{service_id}")
async def delete_catalog_service(property_id: str, service_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not hospitality.delete_service(property_id, service_id):
        raise HTTPException(status_code=404, detail="Service not found.")
    return {"status": "deleted"}


@app.get("/api/admin/properties/{property_id}/recommendations")
async def admin_recommendations(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {"recommendations": hospitality.recommendations(property_id)}


@app.put("/api/admin/properties/{property_id}/recommendations")
async def save_recommendation(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.upsert_recommendation(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/recommendations/{recommendation_id}")
async def delete_recommendation(property_id: str, recommendation_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not hospitality.delete_recommendation(property_id, recommendation_id):
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return {"status": "deleted"}


@app.put("/api/admin/properties/{property_id}/hospitality/facilities")
async def upsert_facility_profile(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.upsert_facility_profile(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/restaurants")
async def list_restaurants(property_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    restaurant_ids = None if principal.can("properties.all") or principal.can("properties.edit") else _assigned_restaurant_ids(principal, property_id)
    overview = hospitality.overview(property_id, restaurant_ids)
    if restaurant_ids is not None:
        for item in overview["restaurants"]:
            item.pop("internal_notes", None)
    return {"restaurants": overview["restaurants"]}


@app.get("/api/admin/properties/{property_id}/restaurants/{restaurant_id}")
async def get_restaurant(property_id: str, restaurant_id: str, request: Request) -> dict[str, Any]:
    return _require_restaurant_access(_admin_principal(request), property_id, restaurant_id)


@app.put("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/hours")
async def update_restaurant_hours(property_id: str, restaurant_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.hours.edit")
    updates = {key: payload.data[key] for key in ("opening_hours", "meal_periods") if key in payload.data}
    try:
        return hospitality.update_restaurant(property_id, restaurant_id, updates, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/restaurants")
async def create_restaurant(property_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    if not principal.can("properties.edit"):
        raise HTTPException(status_code=403, detail="Only property administrators can create restaurants.")
    try:
        return hospitality.create_restaurant(property_id, payload.data, actor_user_id=principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/restaurants/{restaurant_id}")
async def update_restaurant(property_id: str, restaurant_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.manage")
    if payload.data.get("status") == "archived" and not principal.can("properties.edit"):
        raise HTTPException(status_code=403, detail="Only property administrators can archive restaurants.")
    try:
        return hospitality.update_restaurant(property_id, restaurant_id, payload.data, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/staff")
async def list_restaurant_staff(property_id: str, restaurant_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "conversations.assign")
    with admin_auth._connect() as db:
        rows = db.execute(
            """SELECT DISTINCT u.user_id,u.display_name,u.username
            FROM admin_users u
            JOIN user_restaurants ur ON ur.user_id=u.user_id AND ur.property_id=u.property_id
            JOIN admin_role_permissions rp ON rp.role_id=u.role_id AND rp.permission='conversations.takeover'
            WHERE u.property_id=? AND ur.restaurant_id=? AND u.status='active'
            ORDER BY u.display_name""",
            (property_id, restaurant_id),
        ).fetchall()
    return {"staff": [dict(row) for row in rows]}


@app.get("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/menus")
async def list_restaurant_menus(property_id: str, restaurant_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.view")
    return {"menus": hospitality.restaurant_menus(property_id, restaurant_id, guest=not principal.can("restaurant.menu.edit"))}


@app.get("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/analytics")
async def restaurant_analytics(property_id: str, restaurant_id: str, request: Request) -> dict[str, Any]:
    _require_restaurant_access(_admin_principal(request), property_id, restaurant_id, "restaurant.analytics.view")
    return hospitality.restaurant_analytics(property_id, restaurant_id)


@app.post("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/menus")
async def create_menu(property_id: str, restaurant_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.edit")
    try:
        return hospitality.create_menu(
            property_id, restaurant_id, payload.data,
            actor_user_id=principal.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/menus/{menu_id}")
async def update_restaurant_menu(property_id: str, menu_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_menu(property_id, menu_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Menu not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.edit")
    try:
        return hospitality.update_menu(property_id, menu_id, payload.data, actor_user_id=principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/menus/{menu_id}/items")
async def create_menu_item(property_id: str, menu_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_menu(property_id, menu_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Menu not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.edit")
    try:
        return hospitality.create_menu_item(
            property_id, menu_id, payload.data,
            actor_user_id=principal.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/menu-items/{item_id}")
async def update_menu_item(property_id: str, item_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_menu_item(property_id, item_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Menu item not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.edit")
    try:
        return hospitality.update_menu_item(property_id, item_id, payload.data, actor_user_id=principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/menus/{menu_id}/approve")
async def approve_restaurant_menu(property_id: str, menu_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_menu(property_id, menu_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Menu not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.approve")
    try:
        return hospitality.approve_menu(property_id, menu_id, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/menus/{menu_id}/publish")
async def publish_restaurant_menu(property_id: str, menu_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_menu(property_id, menu_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Menu not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.menu.approve")
    try:
        return hospitality.publish_menu(property_id, menu_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/promotions")
async def list_restaurant_promotions(property_id: str, restaurant_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.promotions.view")
    return {"promotions": hospitality.restaurant_promotions(property_id, restaurant_id, guest=not principal.can("restaurant.promotions.edit"))}


@app.post("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/promotions")
async def create_restaurant_promotion(property_id: str, restaurant_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.promotions.edit")
    try:
        return hospitality.create_promotion(property_id, restaurant_id, payload.data, actor_user_id=principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/promotions/{promotion_id}")
async def update_restaurant_promotion(property_id: str, promotion_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_promotion(property_id, promotion_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Promotion not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.promotions.edit")
    try:
        return hospitality.update_promotion(property_id, promotion_id, payload.data, actor_user_id=principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/promotions/{promotion_id}/approve")
async def approve_restaurant_promotion(property_id: str, promotion_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_promotion(property_id, promotion_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Promotion not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.promotions.approve")
    try:
        return hospitality.approve_promotion(property_id, promotion_id, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/promotions/{promotion_id}/publish")
async def publish_restaurant_promotion(property_id: str, promotion_id: str, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    restaurant_id = hospitality.restaurant_id_for_promotion(property_id, promotion_id)
    if not restaurant_id:
        raise HTTPException(status_code=404, detail="Promotion not found.")
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.promotions.approve")
    try:
        return hospitality.publish_promotion(property_id, promotion_id, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/events")
async def create_hotel_event(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.create_event(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/service-requests")
async def create_service_request(property_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    department_name = _department_scope_name(principal, property_id)
    if department_name is not None:
        requested_department = str(payload.data.get("department") or "").strip()
        if requested_department and requested_department.casefold() != department_name.casefold():
            raise HTTPException(status_code=403, detail="This account is not assigned to that department.")
        if payload.data.get("service_id"):
            _require_department_service_scope(principal, property_id, str(payload.data["service_id"]))
        else:
            payload.data["department"] = department_name
    try:
        request_record = hospitality.create_service_request(property_id, payload.data)
        metrics.SERVICE_REQUESTS.labels("created").inc()
        await _dispatch_webhooks(property_id, "guest.request.created", {"request": request_record})
        return request_record
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/service-requests/{request_id}/status")
async def update_service_request_status(
    property_id: str, request_id: str, payload: ServiceStatusPayload, request: Request
) -> dict[str, Any]:
    _require_property(property_id)
    _require_department_request_scope(_admin_principal(request), property_id, request_id)
    try:
        request_record = hospitality.update_service_status(property_id, request_id, payload.status)
        await _dispatch_webhooks(property_id, "guest.request.updated", {"request": request_record})
        return request_record
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/restaurants/{restaurant_id}")
async def delete_restaurant(property_id: str, restaurant_id: str, request: Request) -> dict[str, str]:
    principal = _admin_principal(request)
    _require_restaurant_access(principal, property_id, restaurant_id, "restaurant.manage")
    if not principal.can("properties.edit"):
        raise HTTPException(status_code=403, detail="Only property administrators can archive restaurants.")
    if not hospitality.archive_restaurant(property_id, restaurant_id, principal.user_id):
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    return {"status": "archived"}


@app.delete("/api/admin/properties/{property_id}/hospitality/facilities/{facility_id}")
async def delete_facility_profile(property_id: str, facility_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not hospitality.delete_facility_profile(property_id, facility_id):
        raise HTTPException(status_code=404, detail="Facility not found.")
    return {"status": "deleted"}


@app.put("/api/admin/properties/{property_id}/service-requests/{request_id}")
async def update_service_request(
    property_id: str, request_id: str, payload: ServiceRequestUpdatePayload, request: Request
) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    _require_department_request_scope(principal, property_id, request_id)
    department_name = _department_scope_name(principal, property_id)
    if department_name is not None and payload.department and payload.department.casefold() != department_name.casefold():
        raise HTTPException(status_code=403, detail="This account is not assigned to that department.")
    if department_name is not None and payload.assigned_to:
        assigned_user = admin_auth.get_user(payload.assigned_to)
        if (
            assigned_user is None
            or assigned_user.get("property_id") != property_id
            or assigned_user.get("department_id") != principal.department_id
            or assigned_user.get("status") != "active"
        ):
            raise HTTPException(status_code=403, detail="The assignee is outside this department.")
    try:
        return hospitality.update_service_request(property_id, request_id, payload.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/service-requests/{request_id}/history")
async def service_request_history(property_id: str, request_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    _require_department_request_scope(_admin_principal(request), property_id, request_id)
    return {"history": hospitality.request_history(property_id, request_id)}


@app.post("/api/admin/properties/{property_id}/feedback")
async def add_guest_feedback(property_id: str, payload: GenericPayload, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    principal = _admin_principal(request)
    if payload.data.get("request_id"):
        _require_department_request_scope(principal, property_id, str(payload.data["request_id"]))
    elif principal.role_slug == "department-manager":
        raise HTTPException(status_code=403, detail="Department-scoped feedback must reference an assigned service request.")
    try:
        return hospitality.add_feedback(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/notifications/rules")
async def create_notification_rule(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.create_notification_rule(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/notifications/rules/{rule_id}/evaluate")
async def evaluate_notification(property_id: str, rule_id: str, payload: NotificationEvaluatePayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.evaluate_notification(
            property_id,
            rule_id,
            payload.stay_id,
            payload.verified_payload,
            payload.guest_preferences,
            payload.current_zone_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/journey-events")
async def record_journey_event(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.record_journey_event(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/improvement-loop")
async def get_improvement_loop(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return improvement_loops.snapshot(property_id)


@app.put("/api/admin/properties/{property_id}/improvement-loop")
async def save_improvement_loop_config(property_id: str, payload: ImprovementLoopConfigPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        improvement_loop_store.save_config(property_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return improvement_loops.snapshot(property_id)


@app.post("/api/admin/properties/{property_id}/improvement-loop/start")
async def start_improvement_loop(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    try:
        improvement_loops.start(property_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return improvement_loops.snapshot(property_id)


@app.post("/api/admin/properties/{property_id}/improvement-loop/resume")
async def resume_improvement_loop(property_id: str) -> dict[str, Any]:
    return await start_improvement_loop(property_id)


@app.post("/api/admin/properties/{property_id}/improvement-loop/pause")
async def pause_improvement_loop(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    improvement_loops.pause(property_id)
    return improvement_loops.snapshot(property_id)


@app.post("/api/admin/properties/{property_id}/improvement-loop/stop")
async def stop_improvement_loop(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    improvement_loops.stop(property_id)
    return improvement_loops.snapshot(property_id)


@app.post("/api/admin/properties/{property_id}/improvement-loop/satisfied")
async def satisfy_improvement_loop(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    improvement_loops.satisfy(property_id)
    return improvement_loops.snapshot(property_id)


@app.post("/api/admin/properties/{property_id}/improvement-loop/run-next")
async def run_single_improvement_loop_iteration(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return await improvement_loops.run_single(property_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/improvement-loop/decision")
async def decide_improvement_loop(property_id: str, payload: ImprovementLoopDecisionPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        improvement_loops.decide(property_id, payload.decision, payload.feedback)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return improvement_loops.snapshot(property_id)


@app.post("/api/session/start")
async def start_session(payload: StartSessionRequest, request: Request, response: Response) -> dict[str, Any]:
    property_record = _guest_property(request, payload.property_id)
    network = _enforce_guest_network(request, property_record)
    policy = normalize_guardrails(property_record.guardrails)
    gateway_context: dict[str, Any] = {}
    if policy["antlabs_gateway_enabled"]:
        raw_body = await request.body()
        if not GatewayGuard.validate(
            request.headers,
            raw_body,
            request.client.host if request.client else "",
            property_record.guardrails,
            property_id=property_record.property_id,
            nonce_consumer=store.consume_gateway_nonce,
        ):
            decision = GuardrailDecision(False, "Hotel gateway validation failed.", "antlabs_gateway", property_record.property_id, 1, False, False, _request_id(request))
            security_audit.record(decision.request_id, property_record.property_id, "antlabs_validation_failed", "denied", network.client_ip)
            raise GuardrailDenied(decision)
        gateway_context = {
            key: value for key, value in payload.gateway_context.items()
            if key in {
                "property_id", "authenticated_guest", "gateway_id", "guest_session_id",
                "client_ip", "client_mac", "location_index", "ppli", "guest_vlan", "session_state",
            }
        }
    ip_rate_key = f"session-ip:{property_record.property_id}:{network.client_ip}"
    client_rate_key = f"session-client:{property_record.property_id}:{network.client_ip}:{payload.client_id}"
    if not await _rate_limit_allowed(ip_rate_key, 240, 300) or not await _rate_limit_allowed(client_rate_key, 10, 300):
        raise HTTPException(status_code=429, detail="Too many session attempts. Please wait before trying again.")
    session = store.create(
        property_id=property_record.property_id,
        client_id=payload.client_id,
        gateway_context=gateway_context,
    )
    if policy["antlabs_gateway_enabled"] and gateway_context.get("guest_session_id"):
        # This value is stored only after GatewayGuard accepted the signed request.
        store.bind_antlabs_session(session.session_id, str(gateway_context["guest_session_id"]))
    ttl_seconds = int(policy["guest_session_timeout"]) * 60
    token, context = store.issue_guest_credentials(session.session_id, ttl_seconds=ttl_seconds)
    _set_guest_cookies(response, session.session_id, token, context, ttl_seconds)
    _clear_legacy_guest_cookies(response)
    await _dispatch_webhooks(
        property_record.property_id,
        "guest.session.started",
        {"session_id": session.session_id, "client_id": payload.client_id},
    )
    return {
        "session_id": session.session_id,
        "expires_after_minutes": policy["guest_session_timeout"],
    }


@app.post("/api/session/resume")
async def resume_session(payload: ResumeSessionRequest, request: Request, response: Response) -> dict[str, Any]:
    candidate = store.peek(payload.session_id)
    if candidate is None:
        token_cookie, context_cookie = _guest_cookie_names(payload.session_id)
        if request.cookies.get(token_cookie) or request.cookies.get(context_cookie):
            request.state.guest_cookie_cleanup_session_id = payload.session_id
        raise HTTPException(status_code=401, detail="Concierge session expired.")
    if candidate.client_id != payload.client_id:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
    if not await _rate_limit_allowed(f"session-resume:{candidate.property_id}:{candidate.session_id}", 30, 60):
        raise HTTPException(status_code=429, detail="Too many resume attempts. Please wait a moment.")
    session, property_record = _guest_session(request, payload.session_id)
    policy = normalize_guardrails(property_record.guardrails)
    _, current_token, current_context, _, _ = request.state.guest_cookie_refresh
    credentials = store.rotate_guest_credentials(
        session.session_id,
        current_token or "",
        current_context or "",
        ttl_seconds=int(policy["guest_session_timeout"]) * 60,
    )
    if credentials is None:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
    _set_guest_cookies(response, session.session_id, *credentials, int(policy["guest_session_timeout"]) * 60)
    _clear_legacy_guest_cookies(response)
    return {"session_id": session.session_id, "expires_after_minutes": policy["guest_session_timeout"]}


@app.post("/api/authenticate")
async def authenticate(payload: AuthRequest, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id)
    auth_type = payload.auth_type.strip().lower()
    if auth_type not in AUTHENTICATION_RULES:
        raise HTTPException(status_code=422, detail="Unsupported authentication type.")

    if property_record.public_profile["authentication"]["enabled"] is not True:
        raise HTTPException(status_code=403, detail="Guest Wi-Fi authentication is turned off for this hotel.")

    configured_types = property_record.antlabs_config.get("authentication_types", {})
    configured_type = configured_types.get(auth_type, {}) if isinstance(configured_types, dict) else {}
    if not isinstance(configured_type, dict) or configured_type.get("enabled") is not True:
        raise HTTPException(status_code=403, detail="This authentication method is disabled for this hotel.")
    if settings.antlabs_mode == "browser_handoff":
        gateway_status = antlabs.configuration_status()
        if not gateway_status["configured"]:
            raise HTTPException(status_code=503, detail=gateway_status["detail"])
        if auth_type not in gateway_status["supported_authentication_types"]:
            raise HTTPException(status_code=422, detail="This authentication method is not supported by the configured ANTlabs built-in processor.")

    credentials = dict(payload.credentials)
    if auth_type == "pms":
        credentials.setdefault("room", payload.room or "")
        credentials.setdefault("last_name", payload.last_name or "")

    result = antlabs.authenticate(
        auth_type=auth_type,
        credentials=credentials,
        concierge_session_id=session.session_id,
        gateway_context=session.gateway_context,
    )

    if result.status == "authenticated":
        store.mark_authenticated(session.session_id)
    store.record_authentication(session.session_id, session.property_id, result.status == "authenticated")

    return {
        "status": result.status,
        "message": result.message,
        "handoff": result.handoff,
    }


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id)
    if await _chat_rate_limited(payload.session_id):
        raise HTTPException(status_code=429, detail="Too many messages. Please wait a moment.")

    requested_mode = payload.mode if settings.ai_guest_mode_switch else settings.ai_default_mode
    conversation_state = store.conversation_state(session.session_id, session.property_id)
    if conversation_state["state"] in {"human_active", "resolved"}:
        human_active = conversation_state["state"] == "human_active"
        return {
            "answer": "",
            "source": "human_queue" if human_active else "conversation_resolved",
            "provider": "human" if human_active else "none",
            "model": "staff" if human_active else "none",
            "mode": requested_mode,
            "escalated": human_active,
            "human_takeover": human_active,
            "ai_paused": True,
        }
    auth_types = property_record.public_profile.get("authentication", {}).get("enabled_types", []) if property_record else []
    sanitized_message = AIInputSanitizer.sanitize_text(payload.message)
    conversation_history = [
        {"role": item.role, "content": AIInputSanitizer.sanitize_text(item.content)}
        for item in payload.conversation_history
        if item.content.strip()
    ][-10:]
    contextual_query = _contextual_query(sanitized_message, conversation_history)
    personalization.cleanup_expired()
    personalization_policy = personalization.policy(session.property_id)
    command, command_detail = preference_commands(sanitized_message)
    if command:
        try:
            if command == "disable":
                personalization.set_guest_state(session.property_id, session.session_id, False)
                answer = "Personalization is off. I won't use or add saved preferences until you turn it back on."
            elif command == "enable":
                personalization.set_guest_state(session.property_id, session.session_id, True, "stay")
                answer = "Stay personalization is on. I can remember useful preferences until your session expires; you can review or remove them from Personalization / Memory."
            elif command == "clear":
                deleted = personalization.clear_preferences(session.property_id, session.session_id)
                answer = "I've cleared your saved preferences." if deleted else "There weren't any saved preferences to clear."
            elif command == "forget_last":
                answer = "I've removed that preference." if personalization.delete_last_preference(session.property_id, session.session_id) else "I didn't have a recent saved preference to remove."
            elif command == "forget_category":
                categories = {"food", "budget"} if command_detail == "restaurant" else {str(command_detail)}
                deleted = personalization.delete_category(session.property_id, session.session_id, categories)
                answer = "I've forgotten those preferences." if deleted else "I didn't have a saved preference in that category."
            elif command == "show":
                known = personalization.list_preferences(session.property_id, session.session_id)
                if not personalization_policy["enabled"]:
                    answer = "Personalization is disabled for this hotel, so I don't use a saved guest profile."
                elif known:
                    lines = [f"- {PREFERENCE_CATEGORIES.get(item['category'], item['category'])}: {item['value']}" for item in known]
                    answer = "Here's what I currently remember:\n" + "\n".join(lines)
                else:
                    answer = "I'm not storing any personal preferences. You can keep this private or turn on stay personalization from the menu."
            elif command == "remember":
                if not personalization_policy["enabled"]:
                    answer = "Personalization is disabled for this hotel, so I can't save that preference."
                else:
                    detail = command_detail or ""
                    extracted = extract_preferences(detail)
                    if not extracted:
                        answer = "I couldn't identify a preference to save. You can add or edit one in Personalization / Memory."
                    else:
                        target_level = "personal" if any(item["category"] == "preferred_name" for item in extracted) else "stay"
                        if target_level == "personal" and not personalization_policy["allow_guest_profile"]:
                            answer = "This hotel hasn't enabled optional guest profiles. I can still remember non-name preferences during your stay."
                            extracted = [item for item in extracted if item["category"] != "preferred_name"]
                            target_level = "stay"
                        personalization.set_guest_state(session.property_id, session.session_id, True, target_level)
                        for item in extracted:
                            if item["persistence"] == "profile" and target_level != "personal":
                                item["persistence"] = "stay"
                            personalization.save_preference(session.property_id, session.session_id, **item)
                        if extracted:
                            answer = "I'll keep that in mind during this stay. You can review or remove it in Personalization / Memory."
            else:
                answer = "I couldn't update personalization just now."
        except ValueError as exc:
            answer = str(exc)
        store.record_ai_activity(session.session_id, session.property_id, provider="personalization", model="memory-controls")
        return {"answer": answer, "source": "personalization", "provider": "none", "model": "memory-controls", "mode": "fast", "escalated": False}

    if personalization_policy["enabled"] and personalization_policy["allow_preference_learning"]:
        initial_state = personalization.guest_state(session.property_id, session.session_id)
        if initial_state["enabled"] and initial_state["level"] != "private":
            last_assistant = next((str(item.get("content") or "") for item in reversed(conversation_history) if item.get("role") == "assistant"), "")
            personalization.reinforce_feedback(session.property_id, session.session_id, sanitized_message, last_assistant)
            for item in extract_preferences(sanitized_message):
                if item["category"] == "preferred_name" and initial_state["level"] != "personal":
                    continue
                if initial_state["level"] == "personal" and item["persistence"] == "stay":
                    item["persistence"] = "profile"
                try:
                    personalization.save_preference(session.property_id, session.session_id, **item)
                except ValueError:
                    continue
    personalization_context = personalization.context_for(session.property_id, session.session_id, sanitized_message)
    recommendation_text = sanitized_message.casefold()
    dining_request = any(token in recommendation_text for token in ("restaurant", "eat", "food", "dinner", "lunch", "breakfast", "cafe", "café"))
    activity_request = any(token in recommendation_text for token in ("activity", "things to do", "plan", "attraction", "visit", "tour", "surprise", "do this", "do today", "afternoon", "free tonight", "hours free", "free before", "free for", "what should i do"))
    dining_preferences = {"food", "dietary", "budget", "travel_party", "transportation", "accessibility"}
    activity_preferences = {"interests", "activities", "travel_party", "budget", "transportation", "accessibility", "activity_time", "trip_purpose"}
    uses_guest_recommendations = any(
        item["category"] in ((dining_preferences if dining_request else set()) | (activity_preferences if activity_request else set()))
        for item in personalization_context["preferences"]
    )
    started_at = time.perf_counter()
    safety_reason = PrivacyGuard.classify(sanitized_message)
    if safety_reason:
        security_audit.record(_request_id(request), session.property_id, safety_reason, "blocked", getattr(request.state, "guardrail_decision").client_ip)
    # Fast answers must match the current turn. Using contextual_query here let
    # a previous topic hijack an unrelated follow-up or greeting.
    fast_answer = (PrivacyGuard.safe_response(safety_reason) if safety_reason else None) or _safety_fast_answer(sanitized_message) or _property_fast_answer(property_record, sanitized_message)
    if fast_answer and (safety_reason or (requested_mode != "advanced" and not uses_guest_recommendations)):
        answer = fast_answer
        if _is_authentication_question(sanitized_message):
            answer = f"{answer}\n\n{_authentication_guidance(auth_types)}"
        contact_concierge = safety_reason == "privacy" or CALL_CONCIERGE_MARKER in answer
        answer = answer.replace(CALL_CONCIERGE_MARKER, "").strip()
        store.record_ai_activity(
            session.session_id, session.property_id, provider="fast_path", model="none",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )
        return {
            "answer": answer,
            "source": "fast_path",
            "provider": "none",
            "model": "none",
            "mode": "fast",
            "escalated": False,
            "contact_concierge": contact_concierge,
            "concierge_phone": _concierge_phone(property_record) if contact_concierge else "",
        }

    context = knowledge_management.search(session.property_id, contextual_query, guest=True) + operations.search_knowledge(session.property_id, contextual_query, include_documents=False)
    context.extend(_property_ai_context(property_record))
    if auth_types:
        context.append(
            {
                "title": "Enabled hotel authentication methods",
                "answer": _authentication_guidance(auth_types),
            }
        )
    stay_state = StayContextEngine().build(
        property_record, session, hospitality, guest_identities, personalization, store,
    )
    guest_context = build_guest_context(session.property_id, session, guest_identities, hospitality, conversation_history).prompt_data()
    try:
        local_now = datetime.now(ZoneInfo(property_record.timezone or "UTC"))
    except Exception:
        local_now = datetime.now(timezone.utc)
    guest_context["current_context"] = {
        "local_datetime": local_now.isoformat(timespec="minutes"),
        "local_day": local_now.strftime("%A"),
        "time_zone": local_now.tzname() or "UTC",
    }
    request_text = sanitized_message.casefold()
    needs_room_context = any(token in request_text for token in ("my room", "room number", "in my room", "room service"))
    needs_request_context = any(token in request_text for token in ("my request", "service request status", "where is my", "has my", "did you send", "request status"))
    guest_context["room"] = guest_context.get("room") if needs_room_context and personalization_policy["allow_pms_personalization"] else None
    if not needs_request_context:
        guest_context["open_requests"] = []
        guest_context["recent_requests"] = []
    # The current message history is already passed separately. Never replay an
    # old free-text stay summary as if it were a guest-approved profile.
    guest_context["conversation_summary"] = ""
    # Legacy stay memory was written without guest consent. It is hidden unless the
    # current guest has explicitly enabled personalization for this session.
    if personalization_context["personalization_level"] == "private":
        guest_context["preferences"] = []
    else:
        relevant = personalization_context["preferences"]
        guest_context["preferences"] = [
            f"{PREFERENCE_CATEGORIES.get(item['category'], item['category'])}: {item['value']} ({item['source']}, confidence {float(item['confidence']):.2f})"
            for item in relevant
        ]
    guest_context["personalization_level"] = personalization_context["personalization_level"]
    guest_context["personalization"] = {"level": personalization_context["personalization_level"], "preferences": personalization_context["preferences"]}
    guest_context["stay_context"] = StayContextEngine.prompt_context(stay_state)
    context.append({"title": "Guest stay context", "answer": json.dumps(guest_context, ensure_ascii=False)[:5000]})
    context = AIInputSanitizer.sanitize_context(context)
    policy = normalize_guardrails(property_record.guardrails)
    location = {
        "latitude": property_record.latitude if personalization_policy["allow_location_aware_recommendations"] else None,
        "longitude": property_record.longitude if personalization_policy["allow_location_aware_recommendations"] else None,
    }
    place_results = []
    allow_personalized_places = personalization_policy["enabled"] and personalization_policy["allow_internet_recommendations"]
    place_query = sanitized_message
    search_hints = personalization.search_hints(session.property_id, session.session_id, sanitized_message) if allow_personalized_places else ""
    dining_search = any(token in sanitized_message.casefold() for token in ("restaurant", "eat", "food", "dinner", "lunch", "breakfast", "cafe", "café"))
    activity_search = any(token in sanitized_message.casefold() for token in ("activity", "things to do", "plan", "attraction", "visit", "tour", "surprise", "do this", "do today", "afternoon", "free tonight", "hours free", "free before", "free for", "what should i do"))
    if search_hints and dining_search:
        place_query = f"{sanitized_message} {search_hints}"
    elif search_hints and activity_search:
        place_query = f"things to do near the hotel {search_hints}"
    future_schedule_request = any(
        token in sanitized_message.casefold()
        for token in ("tonight", "tomorrow", "later", "this weekend", "next week", "saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "free before", "hours free")
    )
    prefer_open_now = not future_schedule_request
    if policy["internet_search_enabled"] and personalization_policy["allow_internet_recommendations"] and any(policy[key] for key in ("restaurant_search_enabled", "attractions_enabled")):
        place_results = await places.search(place_query, location.get("latitude"), location.get("longitude"), open_now=prefer_open_now)
        place_results = rank_places(place_results, personalization_context.get("preferences"), conversation_history, prefer_open_now=prefer_open_now)
    live_context = format_places_for_ai(place_results)

    try:
        model_result = await ai_models.concierge_chat(
            property_id=session.property_id,
            user_message=sanitized_message,
            hotel_name=property_record.hotel_name if property_record else knowledge.data["name"],
            context=context,
            live_context=live_context,
            requested_mode=requested_mode,
            conversation_history=conversation_history,
            guest_context=guest_context,
        )
        provider = model_result.provider
        model = model_result.model
        answer = model_result.text
    except Exception as exc:
        # Only the property-scoped provider service may route guest content.
        # A separate legacy router would bypass local-only and fallback settings.
        store.record_ai_activity(
            session.session_id, session.property_id, provider="unavailable", model="none",
            latency_ms=int((time.perf_counter() - started_at) * 1000), error="provider_unavailable",
        )
        return {
            "answer": _concierge_fallback(property_record), "source": "concierge_contact",
            "provider": "none", "model": "contact_fallback", "mode": requested_mode,
            "contact_concierge": True, "concierge_phone": _concierge_phone(property_record),
        }

    answer = AIOutputValidator.validate(answer)
    contact_concierge = CALL_CONCIERGE_MARKER in answer
    answer = answer.replace(CALL_CONCIERGE_MARKER, "").strip()
    store.record_ai_activity(
        session.session_id, session.property_id, provider=provider, model=model,
        latency_ms=int((time.perf_counter() - started_at) * 1000),
    )
    return {
        "answer": answer,
        "source": "ai",
        "provider": provider,
        "model": model,
        "mode": requested_mode,
        "escalated": False,
        "contact_concierge": contact_concierge,
        "concierge_phone": _concierge_phone(property_record) if contact_concierge else "",
        "live_places_used": bool(place_results),
        "personalized_recommendations": uses_guest_recommendations,
        "places": place_results,
        "context_titles": [item.get("title") for item in context],
    }


def _is_authentication_question(message: str) -> bool:
    normalized = message.lower()
    return any(token in normalized for token in ("wi-fi", "wifi", "internet", "connect", "login", "auth"))


def _contextual_query(message: str, history: list[dict[str, Any]]) -> str:
    normalized = message.lower()
    follow_up_tokens = ("it", "there", "that", "they", "what time", "how much", "how long", "does it", "can they")
    if not any(token in normalized for token in follow_up_tokens):
        return message
    recent = " ".join(str(item.get("content") or "") for item in history[-4:]).lower()
    for subject in ("pool", "gym", "spa", "breakfast", "restaurant", "rooftop bar", "business center", "airport", "wi-fi", "wifi"):
        if subject in recent and subject not in normalized:
            return f"{message} (follow-up about {subject})"
    return message


def _safety_fast_answer(message: str) -> str | None:
    normalized = message.lower()
    emergencies = ("fire", "smell smoke", "chest pain", "can't breathe", "cannot breathe", "collapsed", "bleeding badly", "stroke", "child is missing", "security immediately", "trying to enter my room")
    if any(term in normalized for term in emergencies):
        return "This sounds urgent. Please call local emergency services now and alert the hotel Front Desk or Security immediately. Move to a safe location if you can, and do not delay for a chat response."
    protected = ("what room is", "is staying at this hotel", "name of the guest", "another guest's", "cctv footage", "staff wi-fi password", "admin password", "master key code", "bypass the safe", "disable the room lock", "credit card number")
    if any(term in normalized for term in protected):
        return "I can’t provide private guest information, credentials, surveillance footage, payment details, or instructions that bypass hotel security. Please call the hotel concierge or Front Desk for a properly verified request. [[CALL_CONCIERGE]]"
    return None


def _facility_direct_answer(facility: dict[str, Any]) -> str:
    name = str(facility.get("name") or "Facility")
    status = str(facility.get("live_status") or facility.get("status") or "open").casefold().replace(" ", "_")
    unavailable = {
        "full": "currently at capacity",
        "closed": "currently closed",
        "temporarily_closed": "temporarily closed",
        "maintenance": "temporarily unavailable for maintenance",
        "private_event": "unavailable during a private event",
    }.get(status)
    location = str(facility.get("location") or facility.get("status_note") or facility.get("description") or "").strip()
    opening_hours = facility.get("opening_hours") or {}
    hours = facility.get("hours") or (opening_hours.get("display", "") if isinstance(opening_hours, dict) else "")
    if unavailable:
        answer = f"{name} is {unavailable}."
        return answer + (f" Location: {location}." if location else "")
    facts = [value for value in (location, _display_hours(str(hours or "").strip())) if value]
    return f"{name}: {'; '.join(facts)}." if facts else f"{name} information is available from the concierge."


def _property_fast_answer(property_record: PropertyRecord | None, message: str) -> str | None:
    if property_record is None:
        return None
    lowered = message.lower()
    contact = property_record.contact_details or {}
    if "breakfast" in lowered and contact.get("breakfast"):
        return str(contact["breakfast"])
    if "breakfast" in lowered:
        restaurants = [
            item for item in hospitality.guest_facilities(property_record.property_id).get("restaurants", [])
            if any("breakfast" in str(period).casefold() for period in item.get("meal_periods", []))
        ]
        if restaurants:
            venues = []
            hours_available = True
            for item in restaurants:
                hours = (item.get("opening_hours") or {}).get("display", "")
                hours_available = hours_available and bool(hours)
                location = str(item.get("location") or "").strip()
                details = [str(item.get("name") or "Dining venue"), location, f"hours: {hours}" if hours else ""]
                venues.append(" — ".join(value for value in details if value))
            answer = "Breakfast is listed at " + "; ".join(venues) + "."
            if not hours_available:
                answer += " Verified breakfast hours are not available; please confirm them with the Front Desk."
            return answer
    if any(term in lowered for term in ("checkout", "check out", "departure")) and contact.get("checkout"):
        return f"Standard checkout is {contact['checkout']}."
    if any(term in lowered for term in ("wifi", "wi-fi", "internet")) and contact.get("wifi_guidance"):
        return str(contact["wifi_guidance"])
    requested_facilities: list[dict[str, Any]] = []
    configured_facilities = {
        "pool": property_record.pool,
        "gym": property_record.gym,
        "spa": property_record.spa,
    }
    saved_facilities: list[dict[str, Any]] | None = None
    for term, facility in configured_facilities.items():
        if term not in lowered:
            continue
        if facility:
            requested_facilities.append(facility)
            continue
        if saved_facilities is None:
            saved_facilities = hospitality.overview(property_record.property_id).get("facilities", [])
        aliases = {
            "pool": ("pool", "swimming"),
            "gym": ("gym", "fitness"),
            "spa": ("spa", "wellness"),
        }[term]
        saved = next(
            (
                item for item in saved_facilities
                if any(alias in f"{item.get('name', '')} {item.get('facility_type', '')}".casefold() for alias in aliases)
            ),
            None,
        )
        if saved:
            requested_facilities.append({
                "name": saved.get("name"),
                "location": saved.get("status_note") or saved.get("description"),
                "opening_hours": saved.get("opening_hours"),
                "live_status": saved.get("live_status"),
            })
    if requested_facilities:
        return " ".join(_facility_direct_answer(facility) for facility in requested_facilities)
    facility_aliases = {
        "parking": ("parking",),
        "business center": ("business center", "business"),
    }
    if any(term in lowered for term in facility_aliases):
        overview = hospitality.overview(property_record.property_id)
        for term, aliases in facility_aliases.items():
            if term not in lowered:
                continue
            facility = next((item for item in overview.get("facilities", []) if any(alias in f"{item.get('name', '')} {item.get('facility_type', '')}".lower() for alias in aliases)), None)
            if facility:
                return _facility_direct_answer(facility)
    for location in (property_record.app_settings or {}).get("locations", []):
        if location.get("guest_visible", True) and str(location.get("name", "")).lower() in lowered:
            description = str(location.get("description") or "").strip()
            location_type = str(location.get("type") or "location").replace("_", " ")
            return description or f"{location['name']} is listed as a {location_type}."
    return None


def _display_hours(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        hour = int(match.group(1))
        minute = match.group(2)
        suffix = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute} {suffix}"

    return re.sub(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", replace, value)


CALL_CONCIERGE_MARKER = "[[CALL_CONCIERGE]]"


def _concierge_phone(property_record: PropertyRecord | None) -> str:
    contact = property_record.contact_details if property_record else {}
    return " ".join(str((contact or {}).get("phone") or "").split())[:80]


def _concierge_fallback(property_record: PropertyRecord | None) -> str:
    phone = _concierge_phone(property_record)
    if phone:
        return f"I don't have a verified answer for that. Please call the hotel concierge at {phone}."
    return "I don't have a verified answer for that. Please call the hotel concierge directly from your room phone or contact the front desk."


def _authentication_guidance(auth_types: list[dict[str, Any]]) -> str:
    if not auth_types:
        return "No hotel authentication method is currently enabled. Please call the hotel concierge or front desk for help."
    return "Enabled authentication methods for this hotel: " + "; ".join(
        f"{item['label']} requires {', '.join(item.get('fields') or ['hotel validation'])}. {item.get('guest_guidance', '')}".strip()
        for item in auth_types
    )


def _property_ai_context(property_record: PropertyRecord | None) -> list[dict[str, str]]:
    if property_record is None:
        return []
    personality = property_record.personality or {}
    guardrails = property_record.guardrails or {}
    result: list[dict[str, str]] = []
    result.append(
        {
            "title": "Hotel profile",
            "answer": (
                f"{property_record.hotel_name}; {property_record.description} Address: {property_record.address}. "
                f"Timezone: {property_record.timezone}."
            )[:1800],
        }
    )
    phone = _concierge_phone(property_record)
    if phone:
        result.append({"title": "Verified concierge contact", "answer": f"Hotel concierge phone: {phone}. Use this number when a guest needs direct help."})
    if property_record.facilities:
        result.append(
            {
                "title": "Hotel facilities",
                "answer": "; ".join(
                    f"{item.get('name')}: {item.get('location', '')}, hours {item.get('hours', 'ask staff')}"
                    for item in property_record.facilities
                )[:3000],
            }
        )
    if property_record.dining:
        result.append(
            {
                "title": "Dining venues",
                "answer": "; ".join(
                    f"{item.get('name')}: {item.get('location', '')}, {', '.join(item.get('meal_periods', []))}"
                    for item in property_record.dining
                )[:2500],
            }
        )
    if property_record.rooms:
        def room_summary(item: dict[str, Any]) -> str:
            name = str(item.get("name") or "Room type").strip()
            details = []
            description = str(item.get("description") or "").strip()
            if description:
                details.append(description)
            capacity = item.get("capacity")
            if capacity not in (None, ""):
                details.append(f"maximum occupancy {capacity} guests")
            count = item.get("count")
            if count not in (None, ""):
                details.append(f"reference count {count} rooms; this is not live availability")
            floors = item.get("floors")
            if isinstance(floors, (list, tuple)):
                floors = ", ".join(str(value) for value in floors if value not in (None, ""))
            if floors not in (None, ""):
                details.append(f"floor or range {floors}")
            status = str(item.get("status") or "").strip()
            if status:
                status_label = {"available": "listed for guest reference", "unavailable": "not currently offered", "maintenance": "under maintenance"}.get(status.lower(), status)
                details.append(f"catalog status: {status_label}")
            return f"{name}: {'; '.join(details)}" if details else name

        result.append(
            {
                "title": "Room inventory",
                "answer": "Room types are descriptive reference information, not live reservation availability. " + "; ".join(room_summary(item) for item in property_record.rooms)[:1900],
            }
        )
    if personality:
        result.append(
            {
                "title": "Approved concierge response style",
                "answer": ", ".join(
                    f"{key.replace('_', ' ')}: {value}"
                    for key, value in personality.items()
                    if value not in (None, "", [], {})
                )[:1600],
            }
        )
    if guardrails:
        safe_fields = {
            key: value
            for key, value in guardrails.items()
            if key in {"allowed_topics", "restricted_topics", "sensitive_information"}
        }
        if safe_fields:
            result.append(
                {
                    "title": "Property guardrails",
                    "answer": ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in safe_fields.items())[:2000],
                }
            )
    guest_locations = [
        item for item in (property_record.app_settings or {}).get("locations", [])
        if item.get("guest_visible", True)
    ]
    if guest_locations:
        result.append(
            {
                "title": "Managed hotel locations",
                "answer": "; ".join(
                    f"{item.get('name', 'Location')} ({item.get('type', 'location')}): {item.get('description', '')}".strip()
                    for item in guest_locations
                )[:2500],
            }
        )
    return result


def _assigned_restaurant_ids(principal: AdminPrincipal, property_id: str) -> set[str]:
    if principal.can("properties.all") or principal.can("properties.edit"):
        with admin_auth._connect() as db:
            return {
                row["restaurant_id"]
                for row in db.execute(
                    "SELECT restaurant_id FROM restaurants WHERE property_id=?",
                    (property_id,),
                ).fetchall()
            }
    if not principal.can_access_property(property_id):
        return set()
    try:
        with admin_auth._connect() as db:
            rows = db.execute(
                "SELECT restaurant_id FROM user_restaurants WHERE user_id=? AND property_id=?",
                (principal.user_id, property_id),
            ).fetchall()
    except sqlite3.Error:
        return set()
    return {row["restaurant_id"] for row in rows}


def _require_restaurant_access(
    principal: AdminPrincipal,
    property_id: str,
    restaurant_id: str,
    permission: str = "restaurant.view",
    *,
    allow_archived: bool = False,
) -> dict[str, Any]:
    _require_property(property_id)
    if not principal.can(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")
    if not (principal.can("properties.all") or principal.can("properties.edit")):
        with admin_auth._connect() as db:
            row = db.execute(
                """SELECT 1 FROM user_restaurants
                WHERE user_id=? AND property_id=? AND restaurant_id=?""",
                (principal.user_id, property_id, restaurant_id),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=403, detail="This account is not assigned to that restaurant.")
    restaurant = hospitality.get_restaurant(property_id, restaurant_id)
    if not restaurant or (
        not allow_archived and (restaurant["archived"] or restaurant["status"] in {"disabled", "archived"})
    ):
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    if not (principal.can("properties.all") or principal.can("properties.edit")):
        restaurant.pop("internal_notes", None)
    return restaurant


def _require_property(property_id: str) -> None:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")


def _property_admin_payload(record: PropertyRecord, principal: AdminPrincipal) -> dict[str, Any]:
    payload = record.to_dict()
    if not principal.can("network.manage") and isinstance(payload.get("guardrails"), dict):
        payload["guardrails"].pop("guest_access_hosts", None)
    if principal.can("properties.all") or principal.can("properties.edit"):
        return payload
    for key in ("ai_settings", "antlabs_config", "knowledge_sources", "personality", "guardrails", "app_settings", "design_draft", "design_versions"):
        payload.pop(key, None)
    return payload


def _require_property_record(property_id: str) -> PropertyRecord:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return record


GUEST_NETWORK_GUARDRAIL_FIELDS = (
    "guest_network_only",
    "guest_access_hosts",
    "allowed_cidrs",
    "trusted_proxy_ranges",
    "session_network_revalidation",
    "guest_session_timeout",
    "antlabs_gateway_enabled",
    "antlabs_gateway_ranges",
)


def _guest_network_settings(value: PropertyRecord | dict[str, Any]) -> dict[str, Any]:
    config = value.guardrails if isinstance(value, PropertyRecord) else value
    normalized = normalize_guardrails(config)
    return {key: normalized[key] for key in GUEST_NETWORK_GUARDRAIL_FIELDS}


def _deployment_network_settings(record: PropertyRecord) -> dict[str, Any]:
    deployment = dict((record.app_settings or {}).get("deployment") or {})
    return {
        key: deployment.get(key)
        for key in ("guest_access_enabled", "public_base_url", "reverse_proxy", "https_required", "trusted_proxy")
    }


def _validated_guest_domain(value: str) -> str:
    domain = str(value or "").strip().casefold().rstrip(".")
    if not domain:
        return ""
    if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
        raise ValueError("Guest domain must be a valid hostname such as concierge.hotelabc.com.")
    return domain


def _validated_guest_url(value: str, domain: str, https_required: bool) -> str:
    guest_url = str(value or "").strip()
    if not guest_url:
        return f"https://{domain}" if domain else ""
    try:
        parsed = urlparse(guest_url)
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError("Guest URL is invalid.") from exc
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or (domain and hostname != domain)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Guest URL must be an HTTP(S) origin for the configured guest domain.")
    if https_required and parsed.scheme != "https":
        raise ValueError("Guest URL must use HTTPS while the HTTPS requirement is enabled.")
    if parsed_port is not None and parsed_port not in ({443} if parsed.scheme == "https" else {80}):
        return f"{parsed.scheme}://{hostname}:{parsed_port}"
    return f"{parsed.scheme}://{hostname}"


def _network_access_status(record: PropertyRecord, principal: AdminPrincipal) -> dict[str, Any]:
    raw_management = operations.get_network_access_settings(_default_management_access_settings())
    management = _effective_management_access_settings()
    host_network = detected_server_network()
    server_ip = host_network["server_ip"]
    if server_ip:
        address = ipaddress.ip_address(server_ip)
        rendered_host = f"[{server_ip}]" if address.version == 6 else server_ip
        admin_url = f"https://{rendered_host}/admin"
    else:
        admin_url = ""

    deployment = dict((record.app_settings or {}).get("deployment") or {})
    guest_config = public_guardrails(record.guardrails)
    domain = str(record.domain or "")
    verification = deployment.get("last_verification") or {}
    raw_ssl_status = str(verification.get("ssl_status") or "not_checked")
    days_remaining = verification.get("days_remaining")
    if raw_ssl_status == "valid" and days_remaining is not None and int(days_remaining) <= 30:
        ssl_status = "expiring"
    elif raw_ssl_status == "valid":
        ssl_status = "valid"
    elif raw_ssl_status in {"invalid", "expired"}:
        ssl_status = "invalid"
    else:
        ssl_status = "not_configured" if not domain else raw_ssl_status
    guest_url = deployment.get("public_base_url") or (f"https://{domain}" if domain else "")
    guest_enabled = deployment.get("guest_access_enabled", True) is not False
    management_enabled = bool(management.get("management_access_enabled", True))
    rollback_deadline = raw_management.get("_rollback_deadline")
    rollback_pending = bool(rollback_deadline and int(rollback_deadline) > int(time.time()))
    overlaps = find_network_overlaps(
        guest_config.get("allowed_cidrs", []),
        management.get("management_allowed_cidrs", []),
    )
    guest_ready = bool(
        guest_enabled
        and domain
        and verification.get("domain_status") == "verified"
        and ssl_status == "valid"
        and deployment.get("https_required", True) is not False
    )
    return {
        "management": {
            "enabled": management_enabled,
            "server_ip": server_ip or "",
            "admin_url": admin_url,
            "network_interface": host_network["network_interface"],
            "allowed_cidrs": management.get("management_allowed_cidrs", []),
            "trusted_proxy_ranges": management.get("management_trusted_proxy_ranges", []),
            "https_status": "enabled" if settings.app_environment in SECURE_ENVIRONMENTS else "not_configured",
            "port": 443,
            "access_protection": "private_network_only" if management_enabled and not unsafe_management_networks(management.get("management_allowed_cidrs", [])) else "unrestricted",
            "status": "protected" if management_enabled and management.get("management_allowed_cidrs") and not unsafe_management_networks(management.get("management_allowed_cidrs", [])) else "unprotected",
            "can_manage": principal.role_slug == "super-admin",
            "rollback_pending": rollback_pending,
            "unsafe_networks": unsafe_management_networks(management.get("management_allowed_cidrs", [])),
            "overlaps_guest_networks": [{"management": admin, "guest": guest} for guest, admin in overlaps],
        },
        "guest": {
            "enabled": guest_enabled,
            "domain": domain,
            "url": guest_url,
            "https_required": deployment.get("https_required", True) is not False,
            "ssl_status": ssl_status,
            "ssl_issuer": verification.get("issuer", ""),
            "ssl_expires_at": verification.get("expires_at"),
            "ssl_days_remaining": days_remaining,
            "ssl_error": verification.get("ssl_error", ""),
            "domain_status": verification.get("domain_status") or ("pending" if domain else "not_configured"),
            "resolved_addresses": verification.get("resolved_addresses", []),
            "last_checked_at": verification.get("checked_at"),
            "reverse_proxy": bool(deployment.get("reverse_proxy", False)),
            "guest_network_only": guest_config["guest_network_only"],
            **({"guest_access_hosts": guest_config["guest_access_hosts"]} if principal.can("network.manage") else {}),
            "allowed_cidrs": guest_config["allowed_cidrs"],
            "trusted_proxy_ranges": guest_config["trusted_proxy_ranges"],
            "session_network_revalidation": guest_config["session_network_revalidation"],
            "guest_session_timeout": guest_config["guest_session_timeout"],
            "antlabs_gateway_enabled": guest_config["antlabs_gateway_enabled"],
            "antlabs_gateway_ranges": guest_config["antlabs_gateway_ranges"],
            "status": "ready" if guest_ready else ("not_configured" if not domain else "setup_required"),
        },
    }


def _audit_network_setting(
    principal: AdminPrincipal,
    property_id: str,
    request: Request,
    action: str,
    setting: str,
    old_value: Any,
    new_value: Any,
) -> None:
    admin_auth.audit(
        principal,
        action,
        "network_access",
        setting,
        property_id=property_id,
        ip_address=request.client.host if request.client else "",
        metadata={"old_value": old_value, "new_value": new_value},
    )


def _audit_management_network_changes(
    principal: AdminPrincipal,
    property_id: str,
    request: Request,
    old: dict[str, Any],
    new: dict[str, Any],
) -> None:
    if old["management_access_enabled"] != new["management_access_enabled"]:
        action = "management_access_enabled" if new["management_access_enabled"] else "management_access_disabled"
        _audit_network_setting(principal, property_id, request, action, "management_access_enabled", old["management_access_enabled"], new["management_access_enabled"])
    old_networks, new_networks = set(old["management_allowed_cidrs"]), set(new["management_allowed_cidrs"])
    for network in sorted(new_networks - old_networks):
        _audit_network_setting(principal, property_id, request, "management_network_added", network, "", network)
    for network in sorted(old_networks - new_networks):
        _audit_network_setting(principal, property_id, request, "management_network_removed", network, network, "")
    if old["management_trusted_proxy_ranges"] != new["management_trusted_proxy_ranges"]:
        _audit_network_setting(principal, property_id, request, "management_proxy_changed", "management_trusted_proxy_ranges", old["management_trusted_proxy_ranges"], new["management_trusted_proxy_ranges"])


def _audit_guest_network_changes(
    principal: AdminPrincipal,
    property_id: str,
    request: Request,
    old_domain: str,
    new_domain: str,
    old_guardrails: dict[str, Any],
    new_guardrails: dict[str, Any],
    old_deployment: dict[str, Any],
    new_deployment: dict[str, Any],
) -> None:
    old_enabled = old_deployment.get("guest_access_enabled", True) is not False
    new_enabled = new_deployment.get("guest_access_enabled", True) is not False
    if old_enabled != new_enabled:
        action = "guest_access_enabled" if new_enabled else "guest_access_disabled"
        _audit_network_setting(principal, property_id, request, action, "guest_access_enabled", old_enabled, new_enabled)
    if old_domain != new_domain:
        _audit_network_setting(principal, property_id, request, "guest_domain_changed", "guest_domain", old_domain, new_domain)
    if old_guardrails["guest_access_hosts"] != new_guardrails["guest_access_hosts"]:
        _audit_network_setting(principal, property_id, request, "guest_access_hosts_changed", "guest_access_hosts", old_guardrails["guest_access_hosts"], new_guardrails["guest_access_hosts"])
    if old_deployment.get("https_required", True) != new_deployment.get("https_required", True):
        _audit_network_setting(principal, property_id, request, "guest_https_requirement_changed", "guest_https_required", old_deployment.get("https_required", True), new_deployment.get("https_required", True))
    old_networks, new_networks = set(old_guardrails["allowed_cidrs"]), set(new_guardrails["allowed_cidrs"])
    for network in sorted(new_networks - old_networks):
        _audit_network_setting(principal, property_id, request, "guest_network_added", network, "", network)
    for network in sorted(old_networks - new_networks):
        _audit_network_setting(principal, property_id, request, "guest_network_removed", network, network, "")
    for field in ("trusted_proxy_ranges", "antlabs_gateway_ranges", "antlabs_gateway_enabled", "guest_network_only", "session_network_revalidation", "guest_session_timeout"):
        if old_guardrails[field] != new_guardrails[field]:
            _audit_network_setting(principal, property_id, request, "guest_network_policy_changed", field, old_guardrails[field], new_guardrails[field])
    for field in ("reverse_proxy", "trusted_proxy", "public_base_url"):
        if old_deployment.get(field) != new_deployment.get(field):
            _audit_network_setting(principal, property_id, request, "guest_deployment_changed", field, old_deployment.get(field), new_deployment.get(field))


def _deployment_status(record: PropertyRecord) -> dict[str, Any]:
    deployment = dict((record.app_settings or {}).get("deployment") or {})
    domain = str(record.domain or "").strip().lower()
    valid_domain = bool(re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain))
    verification = deployment.get("last_verification") or {}
    return {
        "domain": {
            "value": domain,
            "status": "invalid" if domain and not valid_domain else (verification.get("domain_status") or ("pending" if domain else "not_configured")),
            "valid_format": valid_domain,
            "resolved_addresses": verification.get("resolved_addresses", []),
        },
        "ssl": {
            "status": verification.get("ssl_status") or ("not_configured" if not domain else "not_checked"),
            "issuer": verification.get("issuer", ""),
            "expires_at": verification.get("expires_at"),
            "days_remaining": verification.get("days_remaining"),
            "error": verification.get("ssl_error", ""),
        },
        "network": {
            "public_base_url": deployment.get("public_base_url", ""),
            "reverse_proxy": bool(deployment.get("reverse_proxy", False)),
            "https_required": bool(deployment.get("https_required", True)),
            "trusted_proxy": deployment.get("trusted_proxy", ""),
            "status": "configured" if deployment.get("public_base_url") else "configuration_required",
        },
        "last_checked_at": verification.get("checked_at"),
    }


async def _verify_deployment(record: PropertyRecord) -> dict[str, Any]:
    domain = str(record.domain or "").strip().lower()
    if not domain:
        return {"domain_status": "not_configured", "ssl_status": "not_checked", "checked_at": int(time.time()), "detail": "Configure a domain before verification."}
    if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
        return {"domain_status": "invalid", "ssl_status": "not_checked", "checked_at": int(time.time()), "detail": "The configured domain is not valid."}

    result: dict[str, Any] = {"domain_status": "pending", "ssl_status": "not_checked", "checked_at": int(time.time())}
    try:
        addresses = await asyncio.to_thread(lambda: sorted({item[4][0] for item in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)}))
        result["resolved_addresses"] = addresses
        result["domain_status"] = "verified" if addresses else "pending"
    except OSError as exc:
        result["detail"] = f"DNS lookup failed: {exc}"
        return result
    if not addresses:
        result["domain_status"] = "unresolved"
        return result
    try:
        resolved_addresses = [ipaddress.ip_address(address) for address in addresses]
    except ValueError:
        result.update({"domain_status": "blocked", "ssl_status": "not_checked", "detail": "Domain resolved to an invalid address."})
        return result
    if any(not address.is_global for address in resolved_addresses):
        result.update({"domain_status": "blocked", "ssl_status": "not_checked", "detail": "Domain resolves to a non-public network address."})
        return result
    selected_address = str(resolved_addresses[0])

    def inspect_certificate() -> dict[str, Any]:
        context = ssl.create_default_context()
        with socket.create_connection((selected_address, 443), timeout=7) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=domain) as tls_socket:
                certificate = tls_socket.getpeercert()
        expires = ssl.cert_time_to_seconds(certificate["notAfter"])
        issuer = ", ".join("=".join(part) for group in certificate.get("issuer", []) for part in group)
        return {
            "ssl_status": "valid" if expires > time.time() else "expired",
            "issuer": issuer,
            "expires_at": int(expires),
            "days_remaining": max(0, int((expires - time.time()) // 86400)),
        }

    try:
        result.update(await asyncio.to_thread(inspect_certificate))
    except (OSError, ssl.SSLError, KeyError, ValueError) as exc:
        result.update({"ssl_status": "invalid", "ssl_error": str(exc)[:500]})
    return result


def _smtp_probe(config: dict[str, Any]) -> None:
    host = str(config.get("host", ""))
    port = int(config.get("port", 587))
    security = config.get("security", "starttls")
    smtp: smtplib.SMTP
    if security == "ssl":
        smtp = smtplib.SMTP_SSL(host, port, timeout=8, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(host, port, timeout=8)
    try:
        smtp.ehlo()
        if security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if config.get("username"):
            smtp.login(str(config["username"]), str(config.get("password", "")))
    finally:
        try:
            smtp.quit()
        except smtplib.SMTPException:
            smtp.close()


def _send_password_reset_email(config: dict[str, Any], reset: dict[str, Any], reset_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Concierge.AI administrator password reset"
    message["From"] = str(config["from_address"])
    message["To"] = str(reset["email"])
    message.set_content(
        f"Hello {reset['display_name']},\n\n"
        "A password reset was requested for your Concierge.AI administrator account. "
        "This link expires in 30 minutes:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this reset, you can ignore this message."
    )
    host = str(config["host"])
    port = int(config["port"])
    security = config.get("security", "starttls")
    if security == "ssl":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(host, port, timeout=10)
    try:
        smtp.ehlo()
        if security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if config.get("username"):
            smtp.login(str(config["username"]), str(config.get("password", "")))
        smtp.send_message(message)
    finally:
        try:
            smtp.quit()
        except smtplib.SMTPException:
            smtp.close()


async def _dispatch_webhooks(property_id: str, event_name: str, payload: dict[str, Any]) -> None:
    webhooks = [
        item for item in operations.list_webhooks(property_id)
        if item.get("enabled") and event_name in item.get("events", [])
    ]
    if not webhooks:
        return
    body = json.dumps({"event": event_name, "property_id": property_id, "timestamp": int(time.time()), **payload}, default=str).encode("utf-8")
    broker = _outbound_broker(property_id)
    for item in webhooks:
        webhook = operations.get_webhook(property_id, item["webhook_id"], include_secret=True)
        if webhook is None:
            continue
        headers = {"Content-Type": "application/json"}
        if webhook.get("secret"):
            headers["X-Concierge-Signature"] = "sha256=" + hmac.new(webhook["secret"].encode("utf-8"), body, hashlib.sha256).hexdigest()
        try:
            response = await broker.post(webhook["endpoint_url"], content=body, headers=headers)
            status = "delivered" if 200 <= response.status_code < 300 else "failed"
            error = "" if status == "delivered" else f"Endpoint returned HTTP {response.status_code}."
            operations.record_webhook_delivery(property_id, webhook["webhook_id"], event_name, status, response.status_code, error)
        except OutboundRequestError as exc:
            operations.record_webhook_delivery(property_id, webhook["webhook_id"], event_name, "failed", error=str(exc))


# Fail application startup if an administrator API route is missing an explicit
# permission/authentication policy. The inventory is checked again in tests.
configuration_action_services = {
    "properties": properties,
    "hospitality": hospitality,
    "operations": operations,
    "knowledge_management": knowledge_management,
    "knowledge_categories": CATEGORIES,
    "ai_provider_store": ai_provider_store,
    "require_restaurant_access": _require_restaurant_access,
    "validate_design_config": validate_design_config,
    "normalize_guardrails": normalize_guardrails,
    "validated_guest_domain": _validated_guest_domain,
    "validated_guest_url": _validated_guest_url,
    "effective_management_access": _effective_management_access_settings,
    "management_access_guard": management_access_guard,
    "GuestNetworkAccessPayload": GuestNetworkAccessPayload,
    "ManagementAccessPayload": ManagementAccessPayload,
    "save_guest_network_access": save_guest_network_access,
    "save_management_network_access": save_management_network_access,
}
register_admin_configuration_actions(configuration_action_registry, configuration_action_services)
bind_admin_route_policies(app)
