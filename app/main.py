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
from .session_store import SessionStore

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

knowledge = HotelKnowledge(settings.hotel_config_path)
store = SessionStore(settings.db_path, settings.session_ttl_minutes)
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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
    profile = knowledge.public_profile
    profile["ai"] = knowledge.data.get(
        "ai",
        {
            "guest_mode_switch": settings.ai_guest_mode_switch,
            "default_mode": settings.ai_default_mode,
            "modes": [],
        },
    )
    return profile


@app.post("/api/session/start")
async def start_session(request: StartSessionRequest) -> dict[str, Any]:
    session = store.create(
        property_id=request.property_id or settings.property_id,
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
