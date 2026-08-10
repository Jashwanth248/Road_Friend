from __future__ import annotations

import httpx

from app.config import settings


class LocalAI:
    """Optional local conversational brain backed by Ollama."""

    def configured(self) -> bool:
        return bool(settings.ollama_model)

    async def answer(self, prompt: str, history: list[dict] | None = None) -> str:
        messages = [{"role": "system", "content": (
            "You are Road Friend, a warm concise personal companion. Speak naturally, not like an API. "
            "When summarizing search results, mention useful concrete details and clearly say when something is uncertain."
        )}]
        for item in (history or [])[-10:]:
            role = "assistant" if item.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": item.get("text", "")})
        messages.append({"role": "user", "content": prompt})
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={"model": settings.ollama_model, "messages": messages, "stream": False},
            )
            response.raise_for_status()
            return response.json()["message"]["content"].strip()
