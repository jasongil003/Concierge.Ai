from contextlib import asynccontextmanager
import asyncio
import base64
import binascii
import hashlib
import hmac
import json
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
from urllib.parse import urlparse

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
from .hotel import HotelKnowledge
from .improvement_loop import ImprovementLoopManager, ImprovementLoopStore
from .guest_identity import GuestIdentityStore
from .guest_context import build_guest_context
from .personalization import PREFERENCE_CATEGORIES, PersonalizationStore, extract_preferences, preference_commands
from .admin_copilot import ADMIN_POLICY, AdminCopilotStore, available_tools, parse_tool_plan, planner_prompt, synthesis_prompt
from .guardrails import (
    AIInputSanitizer,
    AIOutputValidator,
    ActionGuard,
    GuardrailDecision,
    GuardrailDenied,
    GatewayGuard,
    InternetGuard,
    NetworkGuard,
    PrivacyGuard,
    PropertyGuard,
    SQLiteRateLimiter,
    SecurityAuditLogger,
    normalize_guardrails,
    public_guardrails,
)
from .hospitality import HospitalityStore
from .intro import IntroExperienceStore
from .location_analytics import LocationAnalyticsStore
from .lunara_seed import PROPERTY_ID as LUNARA_PROPERTY_ID, seed_lunara_demo
from .operations import OperationsStore
from .knowledge_management import KnowledgeStore, CATEGORIES
from .observability import DiagnosticContext, DiagnosticToolRegistry, ObservabilityStore, PERIODS
from .outbound_http import OutboundRequestBroker, OutboundRequestError
from .places import GooglePlaces, format_places_for_ai, rank_places
from .properties import AUTHENTICATION_RULES, PropertyRecord, PropertyStore, validate_design_config
from .reporting import ReportService
from .session_store import SessionStore
from .zones import ZoneStore

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

knowledge = HotelKnowledge(settings.hotel_config_path)
store = SessionStore(settings.db_path, settings.session_ttl_minutes)
properties = PropertyStore(settings.db_path)
properties.seed_from_hotel_json(settings.property_id, settings.hotel_config_path)
zones = ZoneStore(settings.db_path)
guest_identities = GuestIdentityStore(settings.db_path)
personalization = PersonalizationStore(settings.db_path)
location_analytics = LocationAnalyticsStore(settings.db_path)
intro_experiences = IntroExperienceStore(settings.db_path)
hospitality = HospitalityStore(settings.db_path)
ai_provider_store = AIProviderStore(settings.db_path)
ai_models = AIModelService(ai_provider_store)
improvement_loop_store = ImprovementLoopStore(settings.db_path)
improvement_loops = ImprovementLoopManager(improvement_loop_store, ai_models)
admin_copilot_store = AdminCopilotStore(settings.db_path)
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
rate_limiter = SQLiteRateLimiter(settings.db_path)
security_audit = SecurityAuditLogger(settings.db_path)
if settings.property_id == LUNARA_PROPERTY_ID:
    seed_lunara_demo(
        properties,
        zones,
        hospitality,
        operations,
        STATIC_DIR / "assets" / "lunara-property-map.png",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    personalization.cleanup_expired()
    improvement_loops.resume_persisted()
    async def process_pending_knowledge():
        while True:
            for property_id, source_id in knowledge_management.pending_sources():
                await asyncio.to_thread(knowledge_management.process, property_id, source_id)
            await asyncio.sleep(10)
    knowledge_worker = asyncio.create_task(process_pending_knowledge())
    yield
    knowledge_worker.cancel()
    try:
        await knowledge_worker
    except asyncio.CancelledError:
        pass
    improvement_loops.shutdown()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(GuardrailDenied)
async def guardrail_denied_handler(request: Request, exc: GuardrailDenied) -> JSONResponse:
    del request
    return JSONResponse(exc.decision.payload(guest_safe=True), status_code=exc.status_code)


def _required_admin_permission(method: str, path: str) -> str | None:
    if path.startswith("/api/admin/auth/"):
        return None
    if path.startswith("/api/admin/users"):
        if method == "GET":
            return "users.view"
        if method == "POST" and path.endswith("/revoke-sessions"):
            return "security.configure"
        if method == "POST":
            return "users.create" if path == "/api/admin/users" else "users.edit"
        return "users.delete" if method == "DELETE" else "users.edit"
    if path.startswith("/api/admin/roles"):
        return "roles.view" if method == "GET" else "roles.manage"
    if path.startswith("/api/admin/permissions"):
        return "roles.view"
    if path.startswith("/api/admin/audit"):
        return "audit.view"
    if path.startswith("/api/admin/system/"):
        return "system.configure"
    if "/assistant/" in path:
        return "assistant.use"
    if "/reports/" in path:
        return "reports.export"
    if "/operations/alerts" in path:
        return "dashboard.view"
    if "/operations/" in path:
        return "dashboard.view"
    if "/guardrails" in path:
        return "security.view" if method == "GET" else "security.configure"
    if "/knowledge" in path:
        if method == "DELETE":
            return "knowledge.delete"
        if path.endswith(("/publish", "/approve", "/unpublish", "/supersede", "/resolve")):
            return "knowledge.publish"
        return "knowledge.view" if method == "GET" else "knowledge.edit"
    if "/webhooks" in path:
        return "integrations.view" if method == "GET" else "integrations.configure"
    if "/deployment" in path:
        return "domains.view" if method == "GET" else "domains.configure"
    if path.endswith("/dashboard"):
        return "dashboard.view"
    if "/conversations" in path:
        return "conversations.view" if method == "GET" else "conversations.reply"
    if "/service-catalog" in path or "/departments" in path:
        return "requests.view" if method == "GET" else "requests.manage"
    if "/ai/" in path or path.endswith("/ai") or "/improvement-loop" in path:
        return "ai.view" if method == "GET" else "ai.configure"
    if "/design" in path or "/intro" in path:
        return "concierge.view" if method == "GET" else "concierge.edit"
    if "/service-requests" in path or "/feedback" in path or "/notifications" in path:
        return "requests.view" if method == "GET" else "requests.manage"
    if "/antlabs/" in path:
        return "integrations.view"
    if "/sessions" in path or "/stays/" in path:
        return "conversations.view" if method == "GET" else "conversations.reply"
    if "/location/" in path:
        return "analytics.view" if method == "GET" else "properties.edit"
    if any(token in path for token in ("/zones", "/buildings", "/floors", "/floor-maps", "/facilities", "/restaurants", "/menus", "/events", "/navigation/", "/access-points")):
        return "properties.view" if method == "GET" else "properties.edit"
    return "properties.view" if method == "GET" else "properties.edit"


def _path_property_id(path: str) -> str | None:
    match = re.match(r"^/api/admin/properties/([^/]+)", path)
    return match.group(1) if match else None


def _admin_rate_limited(session_id: str) -> bool:
    return not rate_limiter.allow(f"admin-api:{session_id}", 300, 60)


def _chat_rate_limited(session_id: str) -> bool:
    return not rate_limiter.allow(f"guest-chat:{session_id}", 20, 60)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers["X-Request-ID"] = getattr(request.state, "request_id", "")
    if settings.app_environment in ("production", "staging"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request.state.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", supplied) else uuid.uuid4().hex
    return await call_next(request)


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
        )


@app.middleware("http")
async def enforce_admin_security(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    public_admin_paths = {
        "/admin/login",
        "/api/admin/auth/login",
        "/api/admin/auth/password-reset/request",
        "/api/admin/auth/password-reset/confirm",
    }
    is_admin_page = path == "/admin"
    is_admin_api = path == "/api/admin" or path.startswith("/api/admin/")
    if path in public_admin_paths or not (is_admin_page or is_admin_api):
        return await call_next(request)

    principal = admin_auth.authenticate(request.cookies.get(SESSION_COOKIE))
    if principal is None:
        if is_admin_page:
            return RedirectResponse("/admin/login", status_code=303)
        return JSONResponse({"detail": "Administrator authentication required."}, status_code=401)
    request.state.admin = principal

    if is_admin_api:
        if _admin_rate_limited(principal.session_id):
            return JSONResponse({"detail": "Administrative request limit exceeded. Try again shortly."}, status_code=429)
        if principal.force_password_change and path not in {
            "/api/admin/auth/me", "/api/admin/auth/change-password", "/api/admin/auth/logout"
        }:
            return JSONResponse({"detail": "Change your temporary password before continuing."}, status_code=428)
        permission = _required_admin_permission(request.method, path)
        if permission and not principal.can(permission):
            return JSONResponse({"detail": f"Permission required: {permission}"}, status_code=403)
        property_id = _path_property_id(path)
        if property_id and not principal.can_access_property(property_id):
            return JSONResponse({"detail": "You do not have access to this property."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf = request.headers.get("X-CSRF-Token", "")
            if not csrf or not secrets_compare(csrf, principal.csrf_token):
                return JSONResponse({"detail": "CSRF validation failed."}, status_code=403)

    response = await call_next(request)
    if is_admin_api and request.method not in {"GET", "HEAD", "OPTIONS"} and response.status_code < 400:
        property_id = _path_property_id(path)
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
    decision = network_guard.evaluate(property_record.property_id, property_record.guardrails, direct_ip, request.headers, _request_id(request), action_level)
    request.state.guardrail_decision = decision
    if not decision.allowed:
        security_audit.record(decision.request_id, property_record.property_id, "network_access_denied", "denied", decision.client_ip, metadata={"path": request.url.path})
        raise GuardrailDenied(decision)
    return decision


def _guest_session(request: Request, session_id: str, action_level: int = 1):
    session = store.peek(session_id)
    if session is None:
        decision = GuardrailDecision(False, "Concierge session expired.", "session_validation", None, action_level, False, False, _request_id(request))
        raise GuardrailDenied(decision, status_code=401)
    property_record = _guest_property(request, session.property_id)
    policy_config = normalize_guardrails(property_record.guardrails)
    if session.last_seen_at < int(time.time()) - int(policy_config["guest_session_timeout"]) * 60:
        store.delete(session.session_id)
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


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    mode: str = "auto"


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


class DesignConfigPayload(BaseModel):
    config: dict[str, Any]


class RestoreDesignPayload(BaseModel):
    version: int


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


class ServiceRequestUpdatePayload(BaseModel):
    priority: str | None = Field(default=None, max_length=40)
    department: str | None = Field(default=None, max_length=120)
    assigned_to: str | None = Field(default=None, max_length=160)
    note: str | None = Field(default=None, max_length=1000)


class ConversationStatePayload(BaseModel):
    status: str = Field(pattern=r"^(open|closed|escalated)$")
    human_takeover: bool = False


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
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    force_password_change: bool = True


class AdminUserUpdatePayload(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    property_id: str | None = None
    department_id: str | None = None
    role_id: str | None = None
    email: str | None = Field(default=None, max_length=254)
    status: str | None = Field(default=None, pattern=r"^(active|disabled|locked)$")


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
    question: str = Field(min_length=2, max_length=1200)
    period: str = Field(default="24h", pattern=r"^(1h|6h|24h|7d|30d|today|yesterday)$")
    current_page: str = Field(default="overview", max_length=80)
    conversation_id: str | None = Field(default=None, max_length=80)


class AssistantConversationPayload(BaseModel):
    conversation_id: str = Field(min_length=16, max_length=80)


class HotelAssistantPayload(BaseModel):
    question: str = Field(min_length=2, max_length=1200)


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
    try:
        with sqlite3.connect(settings.db_path, timeout=2) as db:
            db.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Database is not ready.") from exc
    return {
        "status": "ok",
        "app": settings.app_name,
        "property_id": settings.property_id,
        "ai_provider_mode": settings.ai_provider_mode,
        "local_model": settings.ollama_model,
        "antlabs_mode": settings.antlabs_mode,
    }


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
    profile = property_record.public_profile if property_record else knowledge.public_profile
    if not profile.get("ai"):
        profile["ai"] = {
            "guest_mode_switch": settings.ai_guest_mode_switch,
            "default_mode": settings.ai_default_mode,
            "modes": [],
        }
    return profile


@app.get("/api/guest/zones")
async def guest_zones(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    return zones.overview(record.property_id, guest=True)


@app.get("/api/guest/intro")
async def guest_intro(request: Request, property_id: str | None = None) -> dict[str, Any]:
    record = _guest_property(request, property_id)
    _enforce_guest_network(request, record)
    return intro_experiences.get(record.property_id)


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


@app.get("/api/guest/personalization")
async def get_guest_personalization(session_id: str, request: Request) -> dict[str, Any]:
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
async def clear_guest_preferences(session_id: str, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, session_id)
    deleted = personalization.clear_preferences(session.property_id, session.session_id)
    return {"deleted": deleted, **personalization.guest_state(session.property_id, session.session_id)}


@app.delete("/api/guest/personalization/preferences/{preference_key}")
async def delete_guest_preference(preference_key: str, session_id: str, request: Request) -> dict[str, Any]:
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


@app.post("/api/guest/service-requests")
async def create_guest_service_request(payload: GuestServiceRequestPayload, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id, action_level=2)
    decision = action_guard.decide("service_request", session.property_id, property_record.guardrails, _request_id(request), payload.confirmed)
    if not decision.allowed:
        security_audit.record(decision.request_id, session.property_id, "service_request_blocked", "denied", getattr(request.state, "guardrail_decision", decision).client_ip)
        raise GuardrailDenied(decision, status_code=409 if decision.confirmation_required else 403)
    if not rate_limiter.allow(f"service:{session.property_id}:{session.session_id}", 10, 300):
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
    if not replayed:
        await _dispatch_webhooks(session.property_id, "guest.request.created", {"request": request_record})
    return {"status": "existing" if replayed else "created", "request": request_record}


@app.get("/api/guest/conversations/{session_id}/staff-messages")
async def guest_staff_messages(session_id: str, request: Request) -> dict[str, Any]:
    session, _ = _guest_session(request, session_id)
    return {"messages": store.staff_messages(session_id, session.property_id)}


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
    ip_allowed = rate_limiter.allow(f"password-reset:ip:{client_ip}", 12, 3600)
    account_allowed = rate_limiter.allow(f"password-reset:account:{account_key}", 3, 3600)
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
        reset_url = str(request.url_for("admin_login_page")) + f"#reset_token={reset['token']}"
        try:
            await asyncio.to_thread(_send_password_reset_email, smtp_config, reset, reset_url)
        except Exception:
            pass
    return {"message": "If recovery is configured for this account, reset instructions will be sent."}


@app.post("/api/admin/auth/password-reset/confirm")
async def confirm_admin_password_reset(payload: AdminPasswordResetConfirmPayload, request: Request) -> dict[str, str]:
    client_ip = request.client.host if request.client else ""
    token_key = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()[:16]
    ip_allowed = rate_limiter.allow(f"password-reset-confirm:ip:{client_ip}", 30, 3600)
    token_allowed = rate_limiter.allow(f"password-reset-confirm:token:{token_key}", 10, 3600)
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
        records.sort(key=lambda record: (record.property_id != settings.property_id, record.hotel_name.lower()))
    return {"properties": [record.to_dict() for record in records]}


@app.get("/api/admin/properties/{property_id}")
async def get_property(property_id: str) -> dict[str, Any]:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return record.to_dict()


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
    session_metrics = store.metrics(property_id)
    for metric, value, unit in (
        ("service_requests", summary["service_requests"], "request"),
        ("overdue_requests", summary["overdue_requests"], "request"),
        ("ai_errors", ai_summary["errors"], "error"),
        ("ai_latency_ms", ai_summary["average_latency_ms"], "ms"),
        ("guest_auth_success_rate", analytics_full["guest_auth"]["success_rate"], "%"),
        ("active_sessions", session_metrics.get("active_guests", 0), "session"),
    ):
        observability.record(property_id, metric, value, unit, "available" if value is not None else "unavailable", "application")

    infrastructure_allowed = principal.can("infrastructure.view")
    system_metrics = observability.collect_system(property_id) if infrastructure_allowed else {
        metric: {"value": None, "unit": "", "availability": "restricted"}
        for metric in ("cpu_utilization", "memory_utilization", "disk_utilization", "network_rx_bytes", "network_tx_bytes", "application_uptime_seconds")
    }
    database = observability.database_health() if infrastructure_allowed else {
        "state": "unavailable", "latency_ms": None, "size_bytes": None,
        "evidence": "Infrastructure telemetry is not available to this role.",
    }
    ai_settings = ai_provider_store.get_settings(property_id)
    providers = ai_provider_store.list_connections(property_id)
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
    antlabs_status = antlabs.configuration_status()
    antlabs_state = "simulation" if antlabs_status["status"] == "simulation" else ("healthy" if antlabs_status["configured"] else "unavailable")
    request_state = "warning" if summary["overdue_requests"] else "healthy"
    auth_rate = analytics_full["guest_auth"]["success_rate"]
    auth_state = "unavailable" if auth_rate is None else ("warning" if auth_rate < 90 else "healthy")
    knowledge_count = len(operations.list_knowledge(property_id))
    recent_errors = observability.recent_errors(property_id, period)
    application_state = "warning" if recent_errors else "healthy"
    components = [
        {"id": "application", "name": "Application", "state": application_state, "evidence": f"The API is responding; {len(recent_errors)} recorded integration or AI error(s) were found in this period."},
        {"id": "database", "name": "Database", "state": database["state"], "evidence": database["evidence"]},
        {"id": "ai_providers", "name": "AI providers", "state": ai_state, "evidence": f"{len(configured_providers)} of {len(enabled_providers)} enabled providers have credentials or local execution."},
        {"id": "antlabs", "name": "ANTlabs gateway", "state": antlabs_state, "evidence": f"Mode: {antlabs_status['mode']}; status: {antlabs_status['status']}."},
        {"id": "guest_auth", "name": "Guest authentication", "state": auth_state, "evidence": "No authentication attempts in this period." if auth_rate is None else f"{auth_rate}% of attempts succeeded."},
        {"id": "request_queue", "name": "Service request queue", "state": request_state, "evidence": f"{summary['open_requests']} open; {summary['overdue_requests']} overdue."},
        {"id": "knowledge", "name": "Knowledge index", "state": "healthy" if knowledge_count else "warning", "evidence": f"{knowledge_count} indexed knowledge item(s)."},
    ]
    overall = _component_state([item["state"] for item in components])
    analytics = {key: value for key, value in analytics_full.items() if key != "raw_requests"}
    selected_provider = next((item for item in providers if item["provider_id"] == ai_settings.get("default_provider")), None)
    analytics["summary"]["active_sessions"] = session_metrics.get("active_guests", 0)
    analytics["ai"]["selected_provider"] = ai_settings.get("default_provider")
    analytics["ai"]["selected_model"] = selected_provider.get("selected_model") if selected_provider else None
    histories = {
        metric: observability.history(property_id, metric, period, start_at, end_at)
        for metric in ("api_latency_ms", "http_errors", "request_queue_depth", "active_sessions", "service_requests", "overdue_requests", "ai_latency_ms", "ai_errors", "guest_auth_success_rate", "cpu_utilization", "memory_utilization", "disk_utilization", "network_rx_bytes", "network_tx_bytes")
    }
    infrastructure_metrics = {"cpu_utilization", "memory_utilization", "disk_utilization", "network_rx_bytes", "network_tx_bytes", "request_queue_depth", "http_errors", "api_latency_ms"}
    history_availability = {metric: "available" for metric in histories}
    if not infrastructure_allowed:
        for metric in infrastructure_metrics:
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
    payload["alerts"] = observability.evaluate_alerts(property_id, payload)
    return payload


def _recommendations(analytics: dict[str, Any], alerts: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    summary = analytics["summary"]
    if summary["overdue_requests"]:
        recommendations.append(f"Review the {summary['overdue_requests']} overdue request(s) and rebalance the busiest department queue.")
    if analytics["ai"]["requests"] and analytics["ai"]["errors"]:
        recommendations.append("Review failed AI provider calls before changing routing or fallback configuration.")
    if summary["fallback_rate_percent"] > 10:
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


def _diagnostic_result(tool: str, context: DiagnosticContext, dashboard: dict[str, Any], record: PropertyRecord, period: str) -> dict[str, Any]:
    analytics = dashboard["analytics"]
    if tool == "get_system_health":
        return {"component": "system", "state": dashboard["health"]["state"], "evidence": dashboard["health"]["components"], "timeframe": period}
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
        return {"component": "reporting", "state": "available", "evidence": {"property_id": context.property_id, "period": period, "department_scope": analytics.get("department_scope"), "formats": ["xlsx", "pdf"]}, "timeframe": period}
    raise KeyError("Unknown diagnostic tool.")


for _tool_name, _tool_permission in {
    "get_system_health": "dashboard.view", "query_metrics": "dashboard.view", "query_logs": "audit.view", "get_recent_errors": "audit.view",
    "check_database": "infrastructure.view", "check_ai_provider": "ai.view",
    "check_antlabs_gateway": "integrations.view", "check_dns": "domains.view", "check_ssl": "domains.view",
    "check_request_queue": "requests.view", "check_guest_auth": "analytics.view",
    "check_knowledge_index": "knowledge.view", "compare_time_periods": "analytics.view",
    "analyze_business_operations": "analytics.view", "prepare_management_report": "reports.export",
}.items():
    diagnostic_tools.register(_tool_name, _tool_permission, lambda context, tool=_tool_name, **kwargs: _diagnostic_result(tool, context, **kwargs))


def _choose_diagnostic_tool(question: str) -> str:
    lowered = question.casefold()
    choices = [
        (("database", "sqlite"), "check_database"), (("provider", "model", "ai "), "check_ai_provider"),
        (("antlabs", "gateway"), "check_antlabs_gateway"), (("dns", "domain"), "check_dns"),
        (("ssl", "certificate", "https"), "check_ssl"),
        (("report", "export"), "prepare_management_report"), (("department", "guests asking", "guest question", "resolution time", "busiest", "most requested"), "analyze_business_operations"),
        (("queue", "request", "sla", "delay"), "check_request_queue"),
        (("guest auth", "authentication", "login"), "check_guest_auth"), (("knowledge", "index", "answer"), "check_knowledge_index"),
        (("compare", "versus", "trend"), "compare_time_periods"), (("log",), "query_logs"), (("error", "failure"), "get_recent_errors"),
        (("latency", "metric", "utilization", "uptime", "network"), "query_metrics"),
    ]
    return next((tool for words, tool in choices if any(word in lowered for word in words)), "get_system_health")


@app.post("/api/admin/properties/{property_id}/assistant/query")
async def operations_assistant(property_id: str, payload: AssistantQueryPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use"):
        raise HTTPException(status_code=403, detail="You do not have permission to use the assistant.")
    if not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    record = _require_property_record(property_id)
    destructive = bool(re.search(r"\b(restart|delete|disable|enable|change|rotate|reset|deploy|update|remove|configure|publish)\b", payload.question, re.I))
    context = DiagnosticContext(property_id, principal.role_slug, principal.department_id, principal.permissions, _request_id(request))
    requested_tool = _choose_diagnostic_tool(payload.question)
    required_permission = diagnostic_tools._tools.get(requested_tool, ("diagnostics.view", None))[0]
    if not principal.can(required_permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {required_permission}")
    tools_allowed = available_tools(diagnostic_tools, principal.permissions)
    if not tools_allowed:
        raise HTTPException(status_code=403, detail="This role has no permission to run read-only diagnostics.")
    conversation_id = payload.conversation_id or admin_copilot_store.new_conversation_id()
    history = admin_copilot_store.history(conversation_id, property_id, principal.user_id)
    question = AIInputSanitizer.sanitize_text(payload.question)
    try:
        planned = await ai_models.concierge_chat(
            property_id=property_id, user_message=planner_prompt(question, tools_allowed, history),
            hotel_name="Operations Copilot", context=[], requested_mode="advanced",
            conversation_history=history, system_prompt_override=ADMIN_POLICY + " Return only the requested JSON object when selecting tools.",
        )
        selected_tools = parse_tool_plan(planned.text, tools_allowed)
        if not selected_tools:
            selected_tools = ["get_system_health"] if "get_system_health" in tools_allowed else []
        dashboard = _build_operations_dashboard(property_id, payload.period, principal) if selected_tools else {}
        evidence = []
        for tool_name in selected_tools:
            # Registry.run checks the principal's permission again on every tool call.
            result = diagnostic_tools.run(tool_name, context, dashboard=dashboard, record=record, period=payload.period)
            evidence.append({"tool": tool_name, "result": result})
        if destructive:
            synthesis = "I can prepare the recommended change, but it requires explicit confirmation through the appropriate administrative workflow. No configuration changes were made."
        else:
            synthesized = await ai_models.concierge_chat(
                property_id=property_id, user_message=synthesis_prompt(question, evidence, history),
                hotel_name="Operations Copilot", context=[], requested_mode="advanced",
                conversation_history=history, system_prompt_override=ADMIN_POLICY,
            )
            synthesis = AIOutputValidator.validate(synthesized.text)
    except Exception as exc:
        # Preserve diagnostic truth when model planning/synthesis is unavailable.
        try:
            fallback_tool = _choose_diagnostic_tool(question)
            fallback_names = [fallback_tool] if fallback_tool in tools_allowed else [name for name in ("get_system_health", "get_recent_errors") if name in tools_allowed]
            dashboard = _build_operations_dashboard(property_id, payload.period, principal) if fallback_names else {}
            evidence = [{"tool": name, "result": diagnostic_tools.run(name, context, dashboard=dashboard, record=record, period=payload.period)} for name in fallback_names]
        except Exception:
            evidence = []
        admin_auth.audit(principal, "assistant.copilot_provider_failure", "assistant", "configured_provider", property_id=property_id, metadata={"error_type": exc.__class__.__name__})
        deterministic_summary = "AI synthesis is unavailable. Raw deterministic diagnostic evidence is shown below; no changes were made."
        return {"question": question, "conversation_id": conversation_id, "answer": deterministic_summary, "finding": deterministic_summary, "tool": evidence[0]["tool"] if evidence else "unavailable", "component": evidence[0]["result"].get("component", "diagnostics") if evidence else "diagnostics", "timeframe": payload.period, "evidence": evidence, "recommendations": [], "links": [{"label": "Open system health", "panel": "system-health"}], "tool_activity": [item["tool"] for item in evidence], "confirmation_required": destructive, "action_status": "No change was made."}
    primary = evidence[0]["result"] if evidence else {"component": "diagnostics", "state": "unavailable", "evidence": []}
    tool = evidence[0]["tool"] if len(evidence) == 1 else "multi_tool_investigation"
    finding = f"{len(evidence)} diagnostic check(s) completed." if evidence else "No permitted diagnostic evidence was collected."
    recommendations = ["Review the collected evidence and verify the likely cause against the relevant operational screen."] if evidence else []
    links = [{"label": "Open system health", "panel": "system-health"}]
    if any(item["tool"] in {"analyze_business_operations", "compare_time_periods", "check_guest_auth"} for item in evidence):
        links = [{"label": "Open analytics", "panel": "analytics"}, *links]
    if any(item["tool"] == "prepare_management_report" for item in evidence):
        links = [{"label": "Open reports", "panel": "reports"}]
    admin_copilot_store.append(conversation_id, property_id, principal.user_id, question, synthesis)
    response = {
        "question": question, "conversation_id": conversation_id, "answer": synthesis, "tool": tool, "finding": finding,
        "component": primary.get("component", "diagnostics"), "timeframe": primary.get("timeframe", payload.period),
        "evidence": evidence, "likely_cause": primary.get("likely_cause"), "tool_activity": [item["tool"] for item in evidence],
        "recommendations": recommendations,
        "links": links,
        "confirmation_required": destructive,
        "action_status": "No change was made. Explicit confirmation in the relevant configuration screen is required." if destructive else "No changes were made.",
        "request_id": context.request_id,
    }
    observability.log_diagnostic(context.request_id, property_id, principal.user_id, tool, payload.period, finding)
    admin_auth.audit(principal, "assistant.diagnostic", "diagnostic", tool, property_id=property_id, metadata={"period": payload.period, "tools": [item["tool"] for item in evidence], "confirmation_required": destructive})
    return response


@app.delete("/api/admin/properties/{property_id}/assistant/conversation")
async def clear_operations_assistant(property_id: str, payload: AssistantConversationPayload, request: Request) -> dict[str, Any]:
    principal = _admin_principal(request)
    if not principal.can("assistant.use") or not principal.can_access_property(property_id):
        raise HTTPException(status_code=403, detail="Property access denied.")
    admin_copilot_store.clear(payload.conversation_id, property_id, principal.user_id)
    return {"status": "cleared"}


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
    question = AIInputSanitizer.sanitize_text(payload.question)
    lower_question = question.casefold()
    if not question.endswith("?") and (lower_question.startswith("our ") or lower_question.startswith("the hotel ")) and any(token in lower_question for token in (" is ", " are ", " opens ", " closes ")):
        category = next((category for category in CATEGORIES if category.casefold() in lower_question), "Other")
        if "pool" in lower_question: category = "Pool"
        elif "gym" in lower_question: category = "Gym"
        elif "restaurant" in lower_question or "breakfast" in lower_question: category = "Dining"
        proposal = {"title": question.split(" is ", 1)[0][:100].strip(" ."), "content": question, "category": category, "visibility": "admin"}
        return {"question": question, "answer": f"I can save this as a {category} knowledge draft. Review the wording and visibility before approving or publishing it.", "provider": "knowledge_tools", "model": "deterministic", "sources": [], "proposed_draft": proposal}
    if any(phrase in lower_question for phrase in ("knowledge health", "missing knowledge", "knowledge coverage")):
        health = knowledge_management.health(property_id)
        return {"question": question, "answer": f"Knowledge coverage is {health['coverage_percent']}%. Missing categories: {', '.join(health['missing_categories']) or 'none'}. Missing core facts: {', '.join(health['missing_fields']) or 'none'}. Pending review: {health['pending_review']}; open conflicts: {health['open_conflicts']}. {health['methodology']}", "provider": "knowledge_tools", "model": "deterministic", "sources": []}
    if any(phrase in lower_question for phrase in ("find conflicts", "contradictory information", "show conflicts")):
        conflicts = [item for item in knowledge_management.conflicts(property_id) if item["status"] == "open"]
        return {"question": question, "answer": f"{len(conflicts)} unresolved knowledge conflict(s). Review them in Knowledge Management.", "provider": "knowledge_tools", "model": "deterministic", "sources": []}
    if any(phrase in lower_question for phrase in ("pending review", "waiting for approval")):
        pending = knowledge_management.list_items(property_id, status="ready_review")
        pending = [item for item in pending if _knowledge_item_allowed(item, principal)]
        return {"question": question, "answer": f"{len(pending)} knowledge item(s) are waiting for review.", "provider": "knowledge_tools", "model": "deterministic", "sources": [{"item_id": item["item_id"], "title": item["title"]} for item in pending[:20]]}
    managed_context = knowledge_management.search(property_id, question, guest=False, role_slug=principal.role_slug)
    context = managed_context + operations.search_knowledge(property_id, question, include_documents=False)
    if property_id == settings.property_id:
        context += knowledge.retrieve(question)
    context.extend(_property_ai_context(record))
    try:
        result = await ai_models.concierge_chat(
            property_id=property_id,
            user_message=question,
            hotel_name=record.hotel_name,
            context=AIInputSanitizer.sanitize_context(context),
            requested_mode="auto",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The configured AI provider could not answer. Check AI Models and provider status, then try again.") from exc
    answer = AIOutputValidator.validate(result.text)
    admin_auth.audit(principal, "assistant.hotel_chat", "assistant", result.provider, property_id=property_id, metadata={"model": result.model})
    return {"question": question, "answer": answer, "provider": result.provider, "model": result.model, "sources": [{"title": item["title"], "source": item["source"], "source_id": item["source_id"], "item_id": item["item_id"], "location": item["location"], "status": item["status"]} for item in managed_context]}


@app.middleware("http")
async def enforce_guest_origin(request: Request, call_next):
    path = request.url.path
    guest_mutation = request.method not in {"GET", "HEAD", "OPTIONS"} and (
        path.startswith("/api/guest/") or path in {"/api/session/start", "/api/session/resume", "/api/authenticate", "/api/chat"}
    )
    origin = request.headers.get("origin")
    if guest_mutation and origin:
        parsed = urlparse(origin)
        origin_host = (parsed.hostname or "").casefold().rstrip(".")
        request_host = request.headers.get("host", "").split(":", 1)[0].casefold().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not origin_host or origin_host != request_host:
            security_audit.record(_request_id(request), None, "guest_origin_blocked", "denied", request.client.host if request.client else "", metadata={"path": path})
            return JSONResponse({"detail": "Cross-origin guest mutation denied."}, status_code=403)
    return await call_next(request)


@app.get("/api/admin/properties/{property_id}/reports/export.xlsx")
async def export_operations_xlsx(property_id: str, request: Request, period: str = "7d") -> Response:
    principal = _admin_principal(request)
    record = _require_property_record(property_id)
    analytics = _analytics_for_principal(property_id, period, principal)
    dashboard = _build_operations_dashboard(property_id, period, principal)
    content = report_service.workbook(record.hotel_name, analytics, _recommendations(analytics, dashboard["alerts"]))
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{property_id}-{period}-operations.xlsx"'})


@app.get("/api/admin/properties/{property_id}/reports/export.pdf")
async def export_operations_pdf(property_id: str, request: Request, period: str = "7d") -> Response:
    principal = _admin_principal(request)
    record = _require_property_record(property_id)
    analytics = _analytics_for_principal(property_id, period, principal)
    dashboard = _build_operations_dashboard(property_id, period, principal)
    content = report_service.management_pdf(record.hotel_name, analytics, dashboard["alerts"], _recommendations(analytics, dashboard["alerts"]))
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{property_id}-{period}-management.pdf"'})


@app.get("/api/admin/properties/{property_id}/conversations")
async def property_conversations(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {"conversations": store.conversations(property_id), "retention": store.retention(property_id)}


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


@app.put("/api/admin/properties/{property_id}/conversations/retention")
async def update_conversation_retention(property_id: str, payload: ConversationRetentionPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return store.set_retention(property_id, payload.retention_days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/conversations/{session_id}")
async def update_conversation_state(property_id: str, session_id: str, payload: ConversationStatePayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return store.set_conversation_state(session_id, property_id, payload.status, payload.human_takeover)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/conversations/{session_id}/messages")
async def staff_conversation_reply(property_id: str, session_id: str, payload: StaffReplyPayload) -> dict[str, Any]:
    _require_property(property_id)
    session = store.get(session_id)
    if session is None or session.property_id != property_id:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    store.record_message(session_id, property_id, "staff", payload.message, provider="human", model="staff")
    store.set_conversation_state(session_id, property_id, "open", True)
    return {"status": "sent"}


@app.put("/api/admin/properties/{property_id}")
async def upsert_property(property_id: str, payload: PropertyPayload) -> dict[str, Any]:
    if property_id != payload.property_id:
        raise HTTPException(status_code=400, detail="Property ID must match the request path.")
    record = payload.to_record()
    existing = properties.get(property_id)
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
    return properties.upsert(record).to_dict()


@app.get("/api/admin/properties/{property_id}/guardrails")
async def get_property_guardrails(property_id: str) -> dict[str, Any]:
    record = _require_property_record(property_id)
    return {"config": public_guardrails(record.guardrails)}


@app.put("/api/admin/properties/{property_id}/guardrails")
async def update_property_guardrails(property_id: str, payload: GuardrailConfigPayload, request: Request) -> dict[str, Any]:
    record = _require_property_record(property_id)
    secret = str((record.guardrails or {}).get("antlabs_signature_secret") or "")
    incoming = dict(payload.config)
    if not incoming.get("antlabs_signature_secret"):
        incoming["antlabs_signature_secret"] = secret
    try:
        record.guardrails = normalize_guardrails(incoming)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    properties.upsert(record)
    principal = _admin_principal(request)
    security_audit.record(_request_id(request), property_id, "network_policy_changed", "success", request.client.host if request.client else "", actor=principal.username)
    return {"config": public_guardrails(record.guardrails)}


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
            "conversation.escalated",
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
        record = properties.save_design_draft(property_id, payload.config)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "draft_saved", "draft": record.design_draft}


@app.post("/api/admin/properties/{property_id}/design/publish")
async def publish_property_design(property_id: str) -> dict[str, Any]:
    try:
        record = properties.publish_design(property_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    latest = record.design_versions[-1] if record.design_versions else {}
    return {
        "status": "published",
        "published": record.design_published,
        "version": latest.get("version"),
        "published_at": latest.get("published_at"),
    }


@app.post("/api/admin/properties/{property_id}/design/discard")
async def discard_property_design(property_id: str) -> dict[str, Any]:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    record.design_draft = validate_design_config(record.design_published)
    properties.upsert(record)
    return {"status": "discarded", "draft": record.design_draft}


@app.post("/api/admin/properties/{property_id}/design/restore")
async def restore_property_design(property_id: str, payload: RestoreDesignPayload) -> dict[str, Any]:
    try:
        record = properties.restore_design_version(property_id, payload.version)
    except KeyError:
        raise HTTPException(status_code=404, detail="Property not found.") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "restored_to_draft", "draft": record.design_draft}


@app.delete("/api/admin/properties/{property_id}")
async def delete_property(property_id: str) -> dict[str, Any]:
    if property_id == settings.property_id:
        raise HTTPException(status_code=400, detail="The active default property cannot be deleted.")
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
        return FileResponse(zones.floor_map_path(property_id, map_id))
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


@app.post("/api/admin/properties/{property_id}/access-points")
async def create_access_point(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_access_point(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/navigation/nodes")
async def create_navigation_node(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_node(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/navigation/edges")
async def create_navigation_edge(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return zones.create_edge(property_id, payload.data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        "devices": guest_identities.list_devices(property_id),
    }


@app.get("/api/admin/properties/{property_id}/ai/usage")
async def property_ai_usage(property_id: str, days: int = 7) -> dict[str, Any]:
    _require_property(property_id)
    return store.operational_metrics(property_id, days)


@app.get("/api/admin/properties/{property_id}/antlabs/status")
async def antlabs_status(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return antlabs.configuration_status()


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


@app.get("/api/admin/properties/{property_id}/intro/assets/{filename}")
async def intro_asset(property_id: str, filename: str) -> FileResponse:
    _require_property(property_id)
    try:
        return FileResponse(intro_experiences.asset_path(property_id, filename))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/hospitality")
async def hospitality_overview(property_id: str, request: Request) -> dict[str, Any]:
    _require_property(property_id)
    overview = hospitality.overview(property_id)
    principal = _admin_principal(request)
    if not principal.can("requests.view"):
        overview.pop("service_requests", None)
        overview.pop("notification_rules", None)
    return overview


@app.get("/api/admin/properties/{property_id}/service-catalog")
async def admin_service_catalog(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return hospitality.catalog(property_id)


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


@app.post("/api/admin/properties/{property_id}/restaurants")
async def create_restaurant(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.create_restaurant(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/restaurants/{restaurant_id}/menus")
async def create_menu(property_id: str, restaurant_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.create_menu(property_id, restaurant_id, payload.data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/admin/properties/{property_id}/menus/{menu_id}/items")
async def create_menu_item(property_id: str, menu_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.create_menu_item(property_id, menu_id, payload.data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
async def create_service_request(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        request_record = hospitality.create_service_request(property_id, payload.data)
        await _dispatch_webhooks(property_id, "guest.request.created", {"request": request_record})
        return request_record
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/service-requests/{request_id}/status")
async def update_service_request_status(property_id: str, request_id: str, payload: ServiceStatusPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        request_record = hospitality.update_service_status(property_id, request_id, payload.status)
        await _dispatch_webhooks(property_id, "guest.request.updated", {"request": request_record})
        return request_record
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/admin/properties/{property_id}/restaurants/{restaurant_id}")
async def delete_restaurant(property_id: str, restaurant_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not hospitality.delete_restaurant(property_id, restaurant_id):
        raise HTTPException(status_code=404, detail="Restaurant not found.")
    return {"status": "deleted"}


@app.delete("/api/admin/properties/{property_id}/hospitality/facilities/{facility_id}")
async def delete_facility_profile(property_id: str, facility_id: str) -> dict[str, str]:
    _require_property(property_id)
    if not hospitality.delete_facility_profile(property_id, facility_id):
        raise HTTPException(status_code=404, detail="Facility not found.")
    return {"status": "deleted"}


@app.put("/api/admin/properties/{property_id}/service-requests/{request_id}")
async def update_service_request(property_id: str, request_id: str, payload: ServiceRequestUpdatePayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.update_service_request(property_id, request_id, payload.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/admin/properties/{property_id}/service-requests/{request_id}/history")
async def service_request_history(property_id: str, request_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {"history": hospitality.request_history(property_id, request_id)}


@app.post("/api/admin/properties/{property_id}/feedback")
async def add_guest_feedback(property_id: str, payload: GenericPayload) -> dict[str, Any]:
    _require_property(property_id)
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
async def start_session(payload: StartSessionRequest, request: Request) -> dict[str, Any]:
    property_record = _guest_property(request, payload.property_id)
    network = _enforce_guest_network(request, property_record)
    policy = normalize_guardrails(property_record.guardrails)
    gateway_context: dict[str, Any] = {}
    if policy["antlabs_gateway_enabled"]:
        raw_body = await request.body()
        if not GatewayGuard.validate(request.headers, raw_body, request.client.host if request.client else "", property_record.guardrails):
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
    if not rate_limiter.allow(ip_rate_key, 240, 300) or not rate_limiter.allow(client_rate_key, 10, 300):
        raise HTTPException(status_code=429, detail="Too many session attempts. Please wait before trying again.")
    session = store.create(
        property_id=property_record.property_id,
        client_id=payload.client_id,
        gateway_context=gateway_context,
    )
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
async def resume_session(payload: ResumeSessionRequest, request: Request) -> dict[str, Any]:
    candidate = store.peek(payload.session_id)
    if candidate is None or candidate.client_id != payload.client_id:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
    if not rate_limiter.allow(f"session-resume:{candidate.property_id}:{candidate.session_id}", 30, 60):
        raise HTTPException(status_code=429, detail="Too many resume attempts. Please wait a moment.")
    session, property_record = _guest_session(request, payload.session_id)
    policy = normalize_guardrails(property_record.guardrails)
    return {"session_id": session.session_id, "expires_after_minutes": policy["guest_session_timeout"]}


@app.post("/api/authenticate")
async def authenticate(payload: AuthRequest, request: Request) -> dict[str, Any]:
    session, property_record = _guest_session(request, payload.session_id)
    auth_type = payload.auth_type.strip().lower()
    if auth_type not in AUTHENTICATION_RULES:
        raise HTTPException(status_code=422, detail="Unsupported authentication type.")

    configured_types = property_record.antlabs_config.get("authentication_types", {})
    configured_type = configured_types.get(auth_type, {}) if isinstance(configured_types, dict) else {}
    if not isinstance(configured_type, dict) or configured_type.get("enabled") is not True:
        raise HTTPException(status_code=403, detail="This authentication method is disabled for this hotel.")

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
    if _chat_rate_limited(payload.session_id):
        raise HTTPException(status_code=429, detail="Too many messages. Please wait a moment.")

    requested_mode = payload.mode if settings.ai_guest_mode_switch else settings.ai_default_mode
    auth_types = property_record.public_profile.get("authentication", {}).get("enabled_types", []) if property_record else []
    conversation_history = store.recent_messages(session.session_id, session.property_id, limit=10)
    sanitized_message = AIInputSanitizer.sanitize_text(payload.message)
    contextual_query = _contextual_query(sanitized_message, conversation_history)
    store.record_message(session.session_id, session.property_id, "guest", sanitized_message)
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
        store.record_message(session.session_id, session.property_id, "assistant", answer, provider="personalization", model="memory-controls")
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
    conversation_state = store.conversation_state(session.session_id, session.property_id)
    if conversation_state["human_takeover"]:
        answer = "Your message was added to the staff conversation. A hotel team member can reply here."
        store.record_message(session.session_id, session.property_id, "assistant", answer, provider="human_queue", model="staff")
        return {"answer": answer, "source": "human_queue", "provider": "human", "model": "staff", "mode": requested_mode, "escalated": True}

    safety_reason = PrivacyGuard.classify(sanitized_message)
    if safety_reason:
        security_audit.record(_request_id(request), session.property_id, safety_reason, "blocked", getattr(request.state, "guardrail_decision").client_ip)
    # Fast answers must match the current turn. Using contextual_query here let
    # a previous topic hijack an unrelated follow-up or greeting.
    fast_answer = (PrivacyGuard.safe_response(safety_reason) if safety_reason else None) or _safety_fast_answer(sanitized_message) or _property_fast_answer(property_record, sanitized_message) or (knowledge.exact_fast_answer(sanitized_message) if session.property_id == settings.property_id else None)
    if fast_answer and (safety_reason or (requested_mode != "advanced" and not uses_guest_recommendations)):
        answer = fast_answer
        if _is_authentication_question(sanitized_message):
            answer = f"{answer}\n\n{_authentication_guidance(auth_types)}"
        store.record_message(session.session_id, session.property_id, "assistant", answer, provider="fast_path", model="none", latency_ms=int((time.perf_counter() - started_at) * 1000))
        return {
            "answer": answer,
            "source": "fast_path",
            "provider": "none",
            "model": "none",
            "mode": "fast",
            "escalated": False,
        }

    context = knowledge_management.search(session.property_id, contextual_query, guest=True) + operations.search_knowledge(session.property_id, contextual_query, include_documents=False)
    if session.property_id == settings.property_id:
        context += knowledge.retrieve(contextual_query)
    context.extend(_property_ai_context(property_record))
    if auth_types:
        context.append(
            {
                "title": "Enabled hotel authentication methods",
                "answer": _authentication_guidance(auth_types),
            }
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
        raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again.") from exc

    answer = AIOutputValidator.validate(answer)
    store.record_message(session.session_id, session.property_id, "assistant", answer, provider=provider, model=model, latency_ms=int((time.perf_counter() - started_at) * 1000))
    if requested_mode == "advanced":
        await _dispatch_webhooks(
            session.property_id,
            "conversation.escalated",
            {"session_id": session.session_id, "message": sanitized_message},
        )
    return {
        "answer": answer,
        "source": "ai",
        "provider": provider,
        "model": model,
        "mode": requested_mode,
        "escalated": requested_mode == "advanced",
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
        return "I can’t provide private guest information, credentials, surveillance footage, payment details, or instructions that bypass hotel security. I can connect you with the Front Desk or Security for a properly verified request."
    return None


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
            saved_facilities = hospitality.guest_facilities(property_record.property_id).get("facilities", [])
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
            opening_hours = saved.get("opening_hours") or {}
            requested_facilities.append({
                "name": saved.get("name"),
                "location": saved.get("description") or saved.get("location"),
                "hours": opening_hours.get("display", "") if isinstance(opening_hours, dict) else "",
            })
    if requested_facilities:
        details = []
        for facility in requested_facilities:
            name = str(facility.get("name") or "Facility")
            location = str(facility.get("location") or "").strip()
            hours = _display_hours(str(facility.get("hours") or "").strip())
            facts = [value for value in (location, hours) if value]
            details.append(f"{name}: {'; '.join(facts)}." if facts else f"{name} information is available from the concierge.")
        return " ".join(details)
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
                hours = (facility.get("opening_hours") or {}).get("display")
                detail = f" Hours: {hours}." if hours else ""
                return f"{facility['name']}.{detail}"
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


def _authentication_guidance(auth_types: list[dict[str, Any]]) -> str:
    if not auth_types:
        return "No hotel authentication method is currently enabled in the admin settings. Tell the guest to contact the front desk."
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
        result.append(
            {
                "title": "Room inventory",
                "answer": "; ".join(
                    f"{item.get('name')} ({item.get('count')} rooms, floors {item.get('floors')})"
                    for item in property_record.rooms
                )[:2000],
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
            if key in {"allowed_topics", "restricted_topics", "unknown_answer", "escalation_behavior", "sensitive_information", "human_escalation"}
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


def _require_property(property_id: str) -> None:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")


def _require_property_record(property_id: str) -> PropertyRecord:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return record


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
            "status": verification.get("ssl_status") or "not_checked",
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

    def inspect_certificate() -> dict[str, Any]:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=7) as raw_socket:
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
