from __future__ import annotations

import asyncio
from typing import Any

from app.config import settings


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiFriend:
    """Gemini-backed conversational brain with optional Google Search grounding."""

    def __init__(self) -> None:
        self._client = None

    def configured(self) -> bool:
        return bool(settings.gemini_api_key)

    def _get_client(self):
        if not settings.gemini_api_key:
            raise GeminiConfigurationError(
                "Add GEMINI_API_KEY to your local .env to enable open-ended answers and Google-grounded search."
            )
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def answer(self, message: str, history: list[dict[str, str]] | None = None, location_context: str | None = None, use_google_search: bool = True) -> dict[str, Any]:
        return await asyncio.to_thread(self._answer_sync, message, history or [], location_context, use_google_search)

    def _answer_sync(self, message: str, history: list[dict[str, str]], location_context: str | None, use_google_search: bool) -> dict[str, Any]:
        from google.genai import types

        client = self._get_client()
        recent = history[-8:]
        transcript = "\n".join(f"{m['role']}: {m['text']}" for m in recent)
        system = (
            "You are Road Friend, a warm, concise personal AI companion. "
            "Answer naturally for spoken conversation. Never claim you accessed private files, "
            "email, messages, camera, location, or accounts unless a tool actually provided that data. "
            "For private data and side-effect actions, say that permission or confirmation is required. "
            "For driving, provide navigation information but never act as an authoritative traffic-signal controller."
        )
        context = f"\nCurrent approximate user location: {location_context}" if location_context else ""
        prompt = f"{system}{context}\nRecent conversation:\n{transcript}\nuser: {message}"

        tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None
        config = types.GenerateContentConfig(tools=tools) if tools else None
        response = client.models.generate_content(model=settings.gemini_model, contents=prompt, config=config)
        text = response.text or "I couldn't produce a response."
        sources: list[dict[str, str]] = []
        try:
            candidates = getattr(response, "candidates", None) or []
            metadata = getattr(candidates[0], "grounding_metadata", None) if candidates else None
            chunks = getattr(metadata, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None)
                if uri:
                    sources.append({"title": title or uri, "url": uri})
        except Exception:
            pass
        return {"text": text, "sources": sources}
