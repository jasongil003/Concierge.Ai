from typing import Any

import httpx

from .config import settings


def build_prompt(
    user_message: str,
    hotel_name: str,
    context: list[dict[str, Any]],
    live_context: str = "",
) -> tuple[str, str]:
    context_text = "\n".join(
        f"- {item.get('title', 'Hotel information')}: {item.get('answer', '')}"
        for item in context
    )
    system = (
        f"You are the digital hotel concierge for {hotel_name}. "
        "Be warm, concise, practical, and hospitality-focused. "
        "Use verified hotel context and live place data when supplied. "
        "Never invent opening hours, prices, ratings, guest records, locations, "
        "or completed service requests. If verified information is unavailable, say so. "
        "Keep normal replies under 100 words unless the guest asks for a plan or comparison."
    )
    prompt = (
        f"Verified hotel context:\n{context_text or '- No matching verified hotel facts.'}\n\n"
        f"Live external context:\n{live_context or '- No live external context supplied.'}\n\n"
        f"Guest: {user_message}"
    )
    return system, prompt


class LocalLLM:
    async def chat(
        self,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
        live_context: str = "",
        advanced: bool = False,
    ) -> str:
        system, prompt = build_prompt(user_message, hotel_name, context, live_context)
        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0.2,
                "num_predict": settings.max_output_tokens if not advanced else settings.max_output_tokens * 2,
            },
            "think": bool(advanced or settings.ollama_think),
        }

        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
            content = body.get("message", {}).get("content", "").strip()
            if not content:
                raise RuntimeError("Local model returned an empty response.")
            return content
