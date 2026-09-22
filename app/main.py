from contextlib import asynccontextmanager
from collections import defaultdict, deque
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
import ssl
import time
from typing import Any
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
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
from .ai import AIOrchestrator
from .ai_providers import AIModelService, AIProviderStore
from .antlabs import AntlabsAdapter
from .config import settings
from .hotel import HotelKnowledge
from .improvement_loop import ImprovementLoopManager, ImprovementLoopStore
from .guest_identity import GuestIdentityStore
from .hospitality import HospitalityStore
from .intro import IntroExperienceStore
from .location_analytics import LocationAnalyticsStore
from .lunara_seed import PROPERTY_ID as LUNARA_PROPERTY_ID, seed_lunara_demo
from .operations import OperationsStore
from .places import GooglePlaces, format_places_for_ai
from .properties import PropertyRecord, PropertyStore, validate_design_config
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
location_analytics = LocationAnalyticsStore(settings.db_path)
intro_experiences = IntroExperienceStore(settings.db_path)
hospitality = HospitalityStore(settings.db_path)
ai = AIOrchestrator()
ai_provider_store = AIProviderStore(settings.db_path)
ai_models = AIModelService(ai_provider_store)
improvement_loop_store = ImprovementLoopStore(settings.db_path)
improvement_loops = ImprovementLoopManager(improvement_loop_store, ai_models)
admin_auth = AdminAuthStore(
    settings.db_path,
    session_ttl_minutes=settings.admin_session_ttl_minutes,
    lockout_attempts=settings.admin_lockout_attempts,
    lockout_minutes=settings.admin_lockout_minutes,
)
if settings.app_environment in ("production", "staging") and settings.admin_bootstrap_password == "ChangeMe123!":
    raise RuntimeError("Set ADMIN_BOOTSTRAP_PASSWORD before starting Concierge.Ai in production/staging.")
admin_auth.ensure_bootstrap_admin(
    settings.admin_bootstrap_username,
    settings.admin_bootstrap_password,
)
admin_request_windows: dict[str, deque[float]] = defaultdict(deque)
chat_rate_windows: dict[str, deque[float]] = defaultdict(deque)
places = GooglePlaces()
antlabs = AntlabsAdapter()
operations = OperationsStore(settings.db_path)
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
    improvement_loops.resume_persisted()
    yield
    improvement_loops.shutdown()


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    if "/knowledge" in path:
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
    import time

    now = time.monotonic()
    window = admin_request_windows[session_id]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= 300:
        return True
    window.append(now)
    return False


def _chat_rate_limited(session_id: str) -> bool:
    now = time.monotonic()
    window = chat_rate_windows[session_id]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= 20:
        return True
    window.append(now)
    return False


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    if settings.app_environment in ("production", "staging"):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


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


class StartSessionRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    property_id: str | None = None
    gateway_context: dict[str, Any] = Field(default_factory=dict)


class AuthRequest(BaseModel):
    session_id: str
    room: str = Field(min_length=1, max_length=64)
    last_name: str = Field(min_length=1, max_length=128)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    mode: str = "auto"


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


class UploadPayload(BaseModel):
    filename: str = Field(min_length=1, max_length=220)
    content_type: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(min_length=1)
    width: float | None = None
    height: float | None = None


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
    role_id: str
    email: str | None = Field(default=None, max_length=254)
    status: str = Field(default="active", pattern=r"^(active|disabled)$")
    force_password_change: bool = True


class AdminUserUpdatePayload(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    property_id: str | None = None
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
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin/login")
async def admin_login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin-login.html")


@app.get("/admin")
async def admin() -> FileResponse:
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "property_id": settings.property_id,
        "ai_provider_mode": settings.ai_provider_mode,
        "local_model": settings.ollama_model,
        "antlabs_mode": settings.antlabs_mode,
    }


@app.get("/api/hotel")
async def hotel() -> dict[str, Any]:
    property_record = properties.get(settings.property_id)
    profile = property_record.public_profile if property_record else knowledge.public_profile
    if not profile.get("ai"):
        profile["ai"] = {
            "guest_mode_switch": settings.ai_guest_mode_switch,
            "default_mode": settings.ai_default_mode,
            "modes": [],
        }
    return profile


@app.get("/api/guest/zones")
async def guest_zones(property_id: str | None = None) -> dict[str, Any]:
    requested_property_id = property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return zones.overview(requested_property_id, guest=True)


@app.get("/api/guest/intro")
async def guest_intro(property_id: str | None = None) -> dict[str, Any]:
    requested_property_id = property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return intro_experiences.get(requested_property_id)


@app.get("/api/guest/navigation/route")
async def guest_route(from_node_id: str, to_node_id: str, property_id: str | None = None) -> dict[str, Any]:
    requested_property_id = property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    try:
        return zones.route(requested_property_id, from_node_id, to_node_id, guest=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/guest/facilities")
async def guest_facilities(property_id: str | None = None) -> dict[str, Any]:
    requested_property_id = property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return hospitality.guest_facilities(requested_property_id)


@app.get("/api/guest/service-catalog")
async def guest_service_catalog(property_id: str | None = None) -> dict[str, Any]:
    requested_property_id = property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return hospitality.catalog(requested_property_id, guest=True)


@app.get("/api/guest/recommendations")
async def guest_recommendations(property_id: str | None = None) -> dict[str, Any]:
    requested_property_id = property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return {"recommendations": hospitality.recommendations(requested_property_id, guest=True)}


@app.post("/api/guest/uploads")
async def upload_guest_document(payload: GuestUploadPayload) -> dict[str, Any]:
    session = store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
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
async def create_guest_service_request(payload: GuestServiceRequestPayload) -> dict[str, Any]:
    session = store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
    try:
        request_record = hospitality.create_service_request(
            session.property_id,
            {
                "service_id": payload.service_id,
                "description": payload.description,
                "room": payload.room,
                "stay_id": session.session_id,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _dispatch_webhooks(session.property_id, "guest.request.created", {"request": request_record})
    return {"status": "created", "request": request_record}


@app.get("/api/guest/conversations/{session_id}/staff-messages")
async def guest_staff_messages(session_id: str) -> dict[str, Any]:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
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
    admin_auth.audit(
        None,
        "auth.password_reset_requested",
        "user",
        payload.username.casefold(),
        ip_address=request.client.host if request.client else "",
    )
    smtp_config = operations.get_email_settings(include_secret=True)
    reset = admin_auth.create_password_reset(payload.username) if smtp_config.get("enabled") else None
    if reset:
        reset_url = str(request.url_for("admin_login_page")) + f"?reset_token={reset['token']}"
        try:
            await asyncio.to_thread(_send_password_reset_email, smtp_config, reset, reset_url)
        except Exception:
            pass
    return {"message": "If recovery is configured for this account, reset instructions will be sent."}


@app.post("/api/admin/auth/password-reset/confirm")
async def confirm_admin_password_reset(payload: AdminPasswordResetConfirmPayload) -> dict[str, str]:
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


@app.get("/api/admin/properties/{property_id}/conversations")
async def property_conversations(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return {"conversations": store.conversations(property_id), "retention": store.retention(property_id)}


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
    if existing:
        record.design_draft = existing.design_draft
        record.design_published = existing.design_published
        record.design_versions = existing.design_versions
    return properties.upsert(record).to_dict()


@app.get("/api/admin/properties/{property_id}/knowledge")
async def list_property_knowledge(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    items = operations.list_knowledge(property_id)
    return {
        "items": [item for item in items if item["kind"] == "entry"],
        "documents": [item for item in items if item["kind"] == "document"],
        "faqs": [item for item in items if item["kind"] == "faq"],
    }


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
async def upload_knowledge_document(property_id: str, payload: UploadPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return operations.upload_document(property_id, payload.filename, payload.content_type, payload.content_base64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        return operations.save_webhook(property_id, payload.model_dump(), payload.webhook_id)
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
async def test_property_webhook(property_id: str, webhook_id: str) -> dict[str, Any]:
    _require_property(property_id)
    webhook = operations.get_webhook(property_id, webhook_id, include_secret=True)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    body = json.dumps({"event": "concierge.webhook.test", "property_id": property_id, "timestamp": int(time.time())}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Concierge.Ai-Webhooks/1.0"}
    if webhook.get("secret"):
        headers["X-Concierge-Signature"] = "sha256=" + hmac.new(webhook["secret"].encode("utf-8"), body, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(webhook["endpoint_url"], content=body, headers=headers)
        status = "delivered" if 200 <= response.status_code < 300 else "failed"
        error = "" if status == "delivered" else f"Endpoint returned HTTP {response.status_code}."
        return operations.record_webhook_delivery(property_id, webhook_id, "concierge.webhook.test", status, response.status_code, error)
    except httpx.HTTPError as exc:
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
        return guest_identities.checkout(property_id, stay_id, anonymize=True)
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
async def hospitality_overview(property_id: str) -> dict[str, Any]:
    _require_property(property_id)
    return hospitality.overview(property_id)


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
async def start_session(request: StartSessionRequest) -> dict[str, Any]:
    requested_property_id = request.property_id or settings.property_id
    if properties.get(requested_property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    session = store.create(
        property_id=requested_property_id,
        client_id=request.client_id,
        gateway_context=request.gateway_context,
    )
    await _dispatch_webhooks(
        requested_property_id,
        "guest.session.started",
        {"session_id": session.session_id, "client_id": request.client_id},
    )
    return {
        "session_id": session.session_id,
        "expires_after_minutes": settings.session_ttl_minutes,
    }


@app.post("/api/authenticate")
async def authenticate(request: AuthRequest) -> dict[str, Any]:
    session = store.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Concierge session expired.")

    result = antlabs.authenticate(
        room=request.room,
        last_name=request.last_name,
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
async def chat(request: ChatRequest) -> dict[str, Any]:
    session = store.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Concierge session expired.")
    if _chat_rate_limited(request.session_id):
        raise HTTPException(status_code=429, detail="Too many messages. Please wait a moment.")

    requested_mode = request.mode if settings.ai_guest_mode_switch else settings.ai_default_mode
    property_record = properties.get(session.property_id)
    auth_types = property_record.public_profile.get("authentication", {}).get("enabled_types", []) if property_record else []
    store.record_message(session.session_id, session.property_id, "guest", request.message)
    started_at = time.perf_counter()
    conversation_state = store.conversation_state(session.session_id, session.property_id)
    if conversation_state["human_takeover"]:
        answer = "Your message was added to the staff conversation. A hotel team member can reply here."
        store.record_message(session.session_id, session.property_id, "assistant", answer, provider="human_queue", model="staff")
        return {"answer": answer, "source": "human_queue", "provider": "human", "model": "staff", "mode": requested_mode, "escalated": True}

    fast_answer = _property_fast_answer(property_record, request.message) or knowledge.exact_fast_answer(request.message)
    if fast_answer and requested_mode != "advanced":
        answer = fast_answer
        if _is_authentication_question(request.message):
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

    context = operations.search_knowledge(session.property_id, request.message) + knowledge.retrieve(request.message)
    context.extend(_property_ai_context(property_record))
    if auth_types:
        context.append(
            {
                "title": "Enabled hotel authentication methods",
                "answer": _authentication_guidance(auth_types),
            }
        )
    location = knowledge.data.get("location", {})
    place_results = await places.search(
        request.message,
        location.get("latitude"),
        location.get("longitude"),
    )
    live_context = format_places_for_ai(place_results)

    try:
        model_result = await ai_models.concierge_chat(
            property_id=session.property_id,
            user_message=request.message,
            hotel_name=property_record.hotel_name if property_record else knowledge.data["name"],
            context=context,
            live_context=live_context,
            requested_mode=requested_mode,
        )
        provider = model_result.provider
        model = model_result.model
        answer = model_result.text
    except Exception as exc:
        try:
            result = await ai.chat(
                user_message=request.message,
                hotel_name=property_record.hotel_name if property_record else knowledge.data["name"],
                context=context,
                live_context=live_context,
                requested_mode=requested_mode,
            )
            provider = result.provider
            model = result.model
            answer = result.answer
        except Exception:
            if context:
                answer = context[0].get("answer")
                store.record_message(session.session_id, session.property_id, "assistant", answer or "", provider="verified_fallback", model="none", latency_ms=int((time.perf_counter() - started_at) * 1000))
                return {
                    "answer": answer,
                    "source": "verified_fallback",
                    "provider": "none",
                    "model": "none",
                    "mode": requested_mode,
                    "escalated": False,
                }
            raise HTTPException(status_code=503, detail="The AI service is temporarily unavailable. Please try again.") from exc

    store.record_message(session.session_id, session.property_id, "assistant", answer, provider=provider, model=model, latency_ms=int((time.perf_counter() - started_at) * 1000))
    if requested_mode == "advanced":
        await _dispatch_webhooks(
            session.property_id,
            "conversation.escalated",
            {"session_id": session.session_id, "message": request.message},
        )
    return {
        "answer": answer,
        "source": "ai",
        "provider": provider,
        "model": model,
        "mode": requested_mode,
        "escalated": requested_mode == "advanced",
        "live_places_used": bool(place_results),
        "places": place_results,
        "context_titles": [item.get("title") for item in context],
    }


def _is_authentication_question(message: str) -> bool:
    normalized = message.lower()
    return any(token in normalized for token in ("wi-fi", "wifi", "internet", "connect", "login", "auth"))


def _property_fast_answer(property_record: PropertyRecord | None, message: str) -> str | None:
    if property_record is None:
        return None
    lowered = message.lower()
    contact = property_record.contact_details or {}
    if "breakfast" in lowered and contact.get("breakfast"):
        return str(contact["breakfast"])
    if any(term in lowered for term in ("checkout", "check out", "departure")) and contact.get("checkout"):
        return f"Standard checkout is {contact['checkout']}."
    if any(term in lowered for term in ("wifi", "wi-fi", "internet")) and contact.get("wifi_guidance"):
        return str(contact["wifi_guidance"])
    facility_terms = ("pool", "gym", "spa", "parking", "business center")
    if any(term in lowered for term in facility_terms):
        overview = hospitality.overview(property_record.property_id)
        for facility in overview.get("facilities", []):
            haystack = f"{facility.get('name', '')} {facility.get('facility_type', '')}".lower()
            if any(term in lowered and term in haystack for term in facility_terms):
                hours = (facility.get("opening_hours") or {}).get("display")
                status = str(facility.get("live_status") or "open").replace("_", " ")
                detail = f" Hours: {hours}." if hours else ""
                return f"{facility['name']} is currently {status}.{detail}"
    for location in (property_record.app_settings or {}).get("locations", []):
        if location.get("guest_visible", True) and str(location.get("name", "")).lower() in lowered:
            description = str(location.get("description") or "").strip()
            location_type = str(location.get("type") or "location").replace("_", " ")
            return description or f"{location['name']} is listed as a {location_type}."
    return None


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
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        for item in webhooks:
            webhook = operations.get_webhook(property_id, item["webhook_id"], include_secret=True)
            if webhook is None:
                continue
            headers = {"Content-Type": "application/json", "User-Agent": "Concierge.Ai-Webhooks/1.0"}
            if webhook.get("secret"):
                headers["X-Concierge-Signature"] = "sha256=" + hmac.new(webhook["secret"].encode("utf-8"), body, hashlib.sha256).hexdigest()
            try:
                response = await client.post(webhook["endpoint_url"], content=body, headers=headers)
                status = "delivered" if 200 <= response.status_code < 300 else "failed"
                error = "" if status == "delivered" else f"Endpoint returned HTTP {response.status_code}."
                operations.record_webhook_delivery(property_id, webhook["webhook_id"], event_name, status, response.status_code, error)
            except httpx.HTTPError as exc:
                operations.record_webhook_delivery(property_id, webhook["webhook_id"], event_name, "failed", error=str(exc))
