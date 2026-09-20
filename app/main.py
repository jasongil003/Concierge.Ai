from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import AIOrchestrator
from .ai_providers import AIModelService, AIProviderStore
from .antlabs import AntlabsAdapter
from .config import settings
from .hotel import HotelKnowledge
from .guest_identity import GuestIdentityStore
from .hospitality import HospitalityStore
from .intro import IntroExperienceStore
from .location_analytics import LocationAnalyticsStore
from .places import GooglePlaces, format_places_for_ai
from .properties import PropertyRecord, PropertyStore, validate_design_config
from .session_store import SessionStore
from .zones import ZoneStore

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
places = GooglePlaces()
antlabs = AntlabsAdapter()


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


class NotificationEvaluatePayload(BaseModel):
    stay_id: str | None = None
    verified_payload: dict[str, Any] = Field(default_factory=dict)
    guest_preferences: dict[str, Any] = Field(default_factory=dict)
    current_zone_id: str | None = None


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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


@app.get("/api/admin/properties")
async def list_properties() -> dict[str, Any]:
    return {"properties": [record.to_dict() for record in properties.list()]}


@app.get("/api/admin/properties/{property_id}")
async def get_property(property_id: str) -> dict[str, Any]:
    record = properties.get(property_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return record.to_dict()


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
    return {"stays": guest_identities.list_stays(property_id), "devices": guest_identities.list_devices(property_id)}


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
        return hospitality.create_service_request(property_id, payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/admin/properties/{property_id}/service-requests/{request_id}/status")
async def update_service_request_status(property_id: str, request_id: str, payload: ServiceStatusPayload) -> dict[str, Any]:
    _require_property(property_id)
    try:
        return hospitality.update_service_status(property_id, request_id, payload.status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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

    requested_mode = request.mode if settings.ai_guest_mode_switch else settings.ai_default_mode
    property_record = properties.get(session.property_id)
    auth_types = property_record.public_profile.get("authentication", {}).get("enabled_types", []) if property_record else []

    fast_answer = knowledge.exact_fast_answer(request.message)
    if fast_answer and requested_mode != "advanced":
        answer = fast_answer
        if _is_authentication_question(request.message):
            answer = f"{answer}\n\n{_authentication_guidance(auth_types)}"
        return {
            "answer": answer,
            "source": "fast_path",
            "provider": "none",
            "model": "none",
            "mode": "fast",
            "escalated": False,
        }

    context = knowledge.retrieve(request.message)
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
            hotel_name=knowledge.data["name"],
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
                hotel_name=knowledge.data["name"],
                context=context,
                live_context=live_context,
                requested_mode=requested_mode,
            )
            provider = result.provider
            model = result.model
            answer = result.answer
        except Exception:
            if context:
                return {
                    "answer": context[0].get("answer"),
                    "source": "verified_fallback",
                    "provider": "none",
                    "model": "none",
                    "mode": requested_mode,
                    "escalated": False,
                }
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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


def _authentication_guidance(auth_types: list[dict[str, Any]]) -> str:
    if not auth_types:
        return "No hotel authentication method is currently enabled in the admin settings. Tell the guest to contact the front desk."
    return "Enabled authentication methods for this hotel: " + "; ".join(
        f"{item['label']} requires {', '.join(item.get('fields') or ['hotel validation'])}. {item.get('guest_guidance', '')}".strip()
        for item in auth_types
    )


def _require_property(property_id: str) -> None:
    if properties.get(property_id) is None:
        raise HTTPException(status_code=404, detail="Property not found.")
