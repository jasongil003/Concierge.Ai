from typing import Any

import httpx

from .config import settings


class LocalLLM:
    async def chat(
        self,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
    ) -> str:
        context_text = "\n".join(
            f"- {item.get('title', 'Hotel information')}: {item.get('answer', '')}"
            for item in context
        )
        system = (
            f"You are the digital hotel concierge for {hotel_name}. "
            "Be warm, brief, and practical. Use only the hotel facts supplied in context. "
            "Never invent opening hours, prices, guest records, or completed service requests. "
            "If the context does not contain the answer, say you do not have verified information "
            "and offer to connect the guest with hotel staff. Keep normal replies under 80 words."
        )

        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Verified hotel context:\n{context_text or '- No matching verified facts.'}\n\nGuest: {user_message}",
                },
            ],
            "options": {
                "temperature": 0.2,
                "num_predict": settings.max_output_tokens,
            },
        }
        if settings.ollama_think is not None:
            payload["think"] = settings.ollama_think

        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                content = body.get("message", {}).get("content", "").strip()
                if content:
                    return content
        except (httpx.HTTPError, ValueError):
            pass

        if context:
            return context[0].get("answer", "I do not have verified information for that yet.")
        return (
            "The local AI service is unavailable or I do not have verified information for that question yet. "
            "Please contact the hotel front desk."
        )
