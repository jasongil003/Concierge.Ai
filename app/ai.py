from dataclasses import dataclass
from typing import Any

import httpx

from .config import settings
from .llm import LocalLLM, build_prompt


COMPLEX_HINTS = {
    "recommend", "recommendation", "nearby", "restaurant", "restaurants", "eat",
    "plan", "itinerary", "compare", "best", "family", "children", "allergy",
    "airport", "flight", "tour", "trip", "things to do", "where should",
}


@dataclass
class AIResult:
    answer: str
    provider: str
    model: str
    mode: str
    escalated: bool


class GeminiProvider:
    async def chat(
        self,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
        live_context: str,
        advanced: bool,
    ) -> AIResult:
        if not settings.gemini_api_key:
            raise RuntimeError("Gemini is not configured.")

        model = settings.gemini_advanced_model if advanced else settings.gemini_fast_model
        system, prompt = build_prompt(user_message, hotel_name, context, live_context)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={settings.gemini_api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": settings.max_output_tokens if not advanced else settings.max_output_tokens * 2,
            },
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            body = response.json()

        parts = (
            body.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        answer = "".join(part.get("text", "") for part in parts).strip()
        if not answer:
            raise RuntimeError("Gemini returned an empty response.")
        return AIResult(answer, "gemini", model, "advanced" if advanced else "fast", advanced)


class OpenAIProvider:
    async def chat(
        self,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
        live_context: str,
        advanced: bool,
    ) -> AIResult:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI is not configured.")

        model = settings.openai_advanced_model if advanced else settings.openai_fast_model
        system, prompt = build_prompt(user_message, hotel_name, context, live_context)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": settings.max_output_tokens if not advanced else settings.max_output_tokens * 2,
        }
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        answer = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if isinstance(answer, list):
            answer = "".join(item.get("text", "") for item in answer if isinstance(item, dict))
        answer = str(answer).strip()
        if not answer:
            raise RuntimeError("OpenAI returned an empty response.")
        return AIResult(answer, "openai", model, "advanced" if advanced else "fast", advanced)


class AIOrchestrator:
    def __init__(self) -> None:
        self.local = LocalLLM()
        self.gemini = GeminiProvider()
        self.openai = OpenAIProvider()

    @staticmethod
    def is_complex(message: str) -> bool:
        text = message.lower()
        return len(text.split()) > 35 or any(hint in text for hint in COMPLEX_HINTS)

    async def _local(
        self,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
        live_context: str,
        advanced: bool,
    ) -> AIResult:
        answer = await self.local.chat(
            user_message=user_message,
            hotel_name=hotel_name,
            context=context,
            live_context=live_context,
            advanced=advanced,
        )
        return AIResult(
            answer=answer,
            provider="local",
            model=settings.ollama_model,
            mode="advanced" if advanced else "fast",
            escalated=advanced,
        )

    async def chat(
        self,
        user_message: str,
        hotel_name: str,
        context: list[dict[str, Any]],
        live_context: str = "",
        requested_mode: str = "auto",
    ) -> AIResult:
        requested_mode = requested_mode if requested_mode in {"fast", "auto", "advanced"} else "auto"
        advanced = requested_mode == "advanced" or (
            requested_mode == "auto" and self.is_complex(user_message)
        )
        policy = settings.ai_provider_mode

        if policy == "local":
            return await self._local(user_message, hotel_name, context, live_context, advanced)

        if policy == "gemini":
            return await self.gemini.chat(user_message, hotel_name, context, live_context, advanced)

        if policy == "openai":
            return await self.openai.chat(user_message, hotel_name, context, live_context, advanced)

        if policy == "hybrid":
            if not advanced:
                try:
                    return await self._local(user_message, hotel_name, context, live_context, False)
                except Exception:
                    pass
            for provider in (self.gemini, self.openai):
                try:
                    return await provider.chat(user_message, hotel_name, context, live_context, True)
                except Exception:
                    continue
            return await self._local(user_message, hotel_name, context, live_context, advanced)

        # auto: prefer local for simple questions, cloud for complex/live recommendations,
        # and gracefully fall back across configured providers.
        candidates = []
        if advanced or live_context:
            candidates = [self.gemini, self.openai]
        else:
            candidates = [self.local, self.gemini, self.openai]

        for provider in candidates:
            try:
                if isinstance(provider, LocalLLM):
                    return await self._local(
                        user_message, hotel_name, context, live_context, advanced
                    )
                return await provider.chat(
                    user_message, hotel_name, context, live_context, advanced
                )
            except Exception:
                continue

        raise RuntimeError("No configured AI provider is currently available.")
