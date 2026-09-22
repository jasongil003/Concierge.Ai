from typing import Any

import httpx

from .config import settings


def build_prompt(
    user_message: str,
    hotel_name: str,
    context: list[dict[str, Any]],
    live_context: str = "",
    conversation_history: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    context_text = "\n".join(
        f"- {item.get('title', 'Hotel information')}: {item.get('answer', '')}"
        for item in context
    )
    history_text = "\n".join(
        f"{('Guest' if item.get('role') == 'guest' else 'Concierge')}: {item.get('content', '')}"
        for item in (conversation_history or [])[-10:]
    )
    system = (
        f"You are the conversational hotel concierge for {hotel_name}. Speak naturally like an attentive hotel colleague, not a scripted chatbot. "
        "Use recent conversation to resolve follow-ups and pronouns. Answer the guest's intent directly, then offer one useful next step only when relevant. "
        "Use verified hotel context and live place data when supplied. Never invent hours, prices, availability, guest records, locations, or completed actions. "
        "If a fact is unavailable, say that plainly and offer to check with hotel staff. Never expose private guest information, credentials, lock bypass instructions, CCTV, PINs, OTPs, or payment secrets. "
        "For fire, medical danger, missing children, threats, or active security incidents, direct the guest to emergency services and hotel staff immediately. "
        "Do not describe yourself as an AI unless asked. Avoid meta phrases such as 'based on the context'. Keep ordinary replies concise."
    )
    prompt = (
        f"Verified hotel context:\n{context_text or '- No matching verified hotel facts.'}\n\n"
        f"Live external context:\n{live_context or '- No live external context supplied.'}\n\n"
        f"Recent conversation:\n{history_text or '- This is the first turn.'}\n\n"
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
