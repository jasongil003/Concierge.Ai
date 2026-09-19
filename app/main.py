from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import AIOrchestrator
from .antlabs import AntlabsAdapter
from .config import settings
from .hotel import HotelKnowledge
from .places import GooglePlaces, format_places_for_ai
from .properties import PropertyRecord, PropertyStore, validate_design_config
from .session_store import SessionStore

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

knowledge = HotelKnowledge(settings.hotel_config_path)
store = SessionStore(settings.db_path, settings.session_ttl_minutes)
properties = PropertyStore(settings.db_path)
properties.seed_from_hotel_json(settings.property_id, settings.hotel_config_path)
ai = AIOrchestrator()
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

    fast_answer = knowledge.exact_fast_answer(request.message)
    if fast_answer and requested_mode != "advanced":
        return {
            "answer": fast_answer,
            "source": "fast_path",
            "provider": "none",
            "model": "none",
            "mode": "fast",
            "escalated": False,
        }

    context = knowledge.retrieve(request.message)
    location = knowledge.data.get("location", {})
    place_results = await places.search(
        request.message,
        location.get("latitude"),
        location.get("longitude"),
    )
    live_context = format_places_for_ai(place_results)

    try:
        result = await ai.chat(
            user_message=request.message,
            hotel_name=knowledge.data["name"],
            context=context,
            live_context=live_context,
            requested_mode=requested_mode,
        )
    except RuntimeError as exc:
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
        "answer": result.answer,
        "source": "ai",
        "provider": result.provider,
        "model": result.model,
        "mode": result.mode,
        "escalated": result.escalated,
        "live_places_used": bool(place_results),
        "places": place_results,
        "context_titles": [item.get("title") for item in context],
    }
