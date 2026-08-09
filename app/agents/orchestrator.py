from __future__ import annotations
import re
from app.integrations.places import PlacesClient
from app.integrations.routes import RoutesClient
from app.integrations.spotify import SpotifyClient
from app.ml.recommender import rank_places
from app.models import ChatRequest, ChatResponse, ToolResult
from app.data.events import EventSink


class RoadMateOrchestrator:
    """Deterministic tool router with an LLM-ready seam for future Gemini tool calling."""

    def __init__(self) -> None:
        self.places = PlacesClient()
        self.routes = RoutesClient()
        self.spotify = SpotifyClient()
        self.events = EventSink()

    async def handle(self, req: ChatRequest) -> ChatResponse:
        text = req.message.strip()
        lower = text.lower()
        self.events.emit("chat_message", {"session_id": req.session_id, "text_length": len(text)})

        if any(k in lower for k in ["near me", "nearby", "restaurant", "waterfall", "coffee", "food", "gas station", "park"]):
            if not req.location:
                return ChatResponse(text="Share your location so I can search nearby places.", intent="places")
            query = self._place_query(text)
            places = await self.places.search(query, req.location, 5)
            ranked = rank_places(places)
            names = ", ".join(p["name"] for p in ranked[:3])
            return ChatResponse(
                text=f"I found these options: {names}. Select one and I can calculate a route.",
                intent="places",
                tools=[ToolResult(tool="places_search", data=ranked)],
            )

        if lower.startswith("pause") or "pause music" in lower:
            result = await self.spotify.pause()
            return ChatResponse(text="I sent the pause command to Spotify." if result.get("mode") == "live" else result["message"], intent="music", tools=[ToolResult(tool="spotify", data=result)])

        if any(k in lower for k in ["play ", "song", "music"]):
            query = re.sub(r"^(please )?play\s+", "", text, flags=re.I)
            result = await self.spotify.search_track(query)
            return ChatResponse(text="I searched Spotify for that request." if result.get("mode") == "live" else result["message"], intent="music", tools=[ToolResult(tool="spotify", data=result)])

        if any(k in lower for k in ["red light", "green light", "traffic signal", "stop sign"]):
            return ChatResponse(
                text="I can explain detected road signs or signal observations, but I cannot make driving decisions for you. Follow the physical signal, road signs, and applicable law.",
                intent="road_awareness",
                safety_notice="Road-awareness output is advisory only and must not be used as an authoritative go/stop command.",
            )

        return ChatResponse(
            text="I can help with nearby places, routing, music commands, road-rule questions, and documents. Connect Gemini Live to replace this local fallback with open-ended voice conversation.",
            intent="general",
        )

    def _place_query(self, text: str) -> str:
        lower = text.lower()
        for category in ["waterfall", "restaurant", "coffee", "food", "gas station", "park", "hiking"]:
            if category in lower:
                return category
        return text
