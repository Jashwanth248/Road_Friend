from __future__ import annotations

import re
from typing import Any

import httpx

from app.data.events import EventSink
from app.integrations.places import PlacesClient, PlacesConfigurationError
from app.integrations.routes import RoutesClient
from app.integrations.spotify import SpotifyClient
from app.ml.recommender import rank_places
from app.models import ChatRequest, ChatResponse, Location, ToolResult


class RoadMateOrchestrator:
    """Conversational tool router with lightweight per-session place/route memory."""

    def __init__(self) -> None:
        self.places = PlacesClient()
        self.routes = RoutesClient()
        self.spotify = SpotifyClient()
        self.events = EventSink()
        self.sessions: dict[str, dict[str, Any]] = {}

    def _session(self, session_id: str) -> dict[str, Any]:
        return self.sessions.setdefault(session_id, {"places": [], "selected_place": None, "location": None})

    async def handle(self, req: ChatRequest) -> ChatResponse:
        text = req.message.strip()
        lower = text.lower()
        state = self._session(req.session_id)
        if req.location:
            state["location"] = req.location
        location: Location | None = req.location or state.get("location")
        self.events.emit("chat_message", {"session_id": req.session_id, "text_length": len(text)})

        selected = self._resolve_place_reference(text, state.get("places", []))
        route_requested = any(k in lower for k in ["take me", "route me", "directions", "navigate", "get me there", "go there"])
        if selected and (route_requested or self._looks_like_selection(lower)):
            state["selected_place"] = selected
            if not route_requested:
                return ChatResponse(
                    text=f"Selected {selected['name']}. Say ‘take me there’ and I’ll calculate a live route from your current location.",
                    intent="place_selection",
                    tools=[ToolResult(tool="selected_place", data=selected)],
                )
            return await self._route_to_place(selected, location)

        if route_requested and state.get("selected_place"):
            return await self._route_to_place(state["selected_place"], location)

        if self._is_place_search(lower):
            if not location:
                return ChatResponse(
                    text="I need your location first. Click Enable Location and allow location access, then ask me again.",
                    intent="location_required",
                )
            query = self._place_query(text)
            try:
                places = await self.places.search(query, location, 6)
            except PlacesConfigurationError as exc:
                return ChatResponse(text=str(exc), intent="configuration")
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:240]
                return ChatResponse(
                    text=f"Google Places returned an error ({exc.response.status_code}). Check that Places API (New) is enabled for your API key. {detail}",
                    intent="places_error",
                )

            ranked = rank_places(places)
            state["places"] = ranked
            state["selected_place"] = None
            if not ranked:
                return ChatResponse(text=f"I couldn't find nearby results for {query}.", intent="places")

            spoken = []
            for i, p in enumerate(ranked[:3], start=1):
                rating = f", rated {p['rating']}" if p.get("rating") else ""
                spoken.append(f"{i}. {p['name']}{rating}")
            return ChatResponse(
                text="Here are the best nearby options: " + "; ".join(spoken) + ". Say ‘first one’, the place name, or ‘take me to number 1’.",
                intent="places",
                tools=[ToolResult(tool="places_search", data=ranked)],
            )

        if lower.startswith("pause") or "pause music" in lower:
            result = await self.spotify.pause()
            return ChatResponse(
                text="I sent the pause command to Spotify." if result.get("mode") == "live" else result["message"],
                intent="music",
                tools=[ToolResult(tool="spotify", data=result)],
            )

        if any(k in lower for k in ["play ", "song", "music"]):
            query = re.sub(r"^(please )?play\s+", "", text, flags=re.I)
            result = await self.spotify.search_track(query)
            return ChatResponse(
                text="I searched Spotify for that request." if result.get("mode") == "live" else result["message"],
                intent="music",
                tools=[ToolResult(tool="spotify", data=result)],
            )

        if any(k in lower for k in ["red light", "green light", "traffic signal", "stop sign"]):
            return ChatResponse(
                text="I can explain detected road signs or signal observations, but I cannot make driving decisions for you. Follow the physical signal, road signs, and applicable law.",
                intent="road_awareness",
                safety_notice="Road-awareness output is advisory only and must not be used as an authoritative go/stop command.",
            )

        if lower in {"hi", "hello", "hey", "hey roadmate"}:
            return ChatResponse(
                text="Hi! I’m RoadMate. Enable location and ask me for coffee, food, parks, waterfalls, or another nearby place. You can then say ‘take me there’ for a route.",
                intent="greeting",
            )

        return ChatResponse(
            text="Ask me for a nearby place, a route, music, or a road-rule explanation. For example: ‘best coffee near me’ or ‘find waterfalls near me’.",
            intent="general",
        )

    async def _route_to_place(self, place: dict, location: Location | None) -> ChatResponse:
        if not location:
            return ChatResponse(text="I need your current location before I can calculate the route.", intent="location_required")
        loc = place.get("location") or {}
        if loc.get("latitude") is None or loc.get("longitude") is None:
            return ChatResponse(text=f"I don't have coordinates for {place.get('name', 'that place')}.", intent="route_error")
        destination = Location(latitude=loc["latitude"], longitude=loc["longitude"])
        route = await self.routes.route(location, destination, "DRIVE")
        if route.get("mode") != "live":
            return ChatResponse(text=route.get("message", "Live routing is not configured."), intent="configuration")
        routes = route.get("routes", [])
        if not routes:
            return ChatResponse(text=f"I couldn't calculate a route to {place['name']}.", intent="route_error")
        best = routes[0]
        meters = best.get("distanceMeters")
        duration = best.get("duration") or "unknown time"
        miles = round(meters / 1609.344, 1) if meters else None
        distance_text = f"{miles} miles" if miles is not None else "an unknown distance"
        return ChatResponse(
            text=f"Routing to {place['name']}. The best current route is about {distance_text} and {duration}. Live traffic is included in the driving ETA.",
            intent="route",
            tools=[ToolResult(tool="route", data={"place": place, **route})],
        )

    def _is_place_search(self, lower: str) -> bool:
        return any(k in lower for k in [
            "near me", "nearby", "restaurant", "waterfall", "coffee", "food",
            "gas station", "park", "hiking", "cafe", "breakfast", "lunch", "dinner",
        ])

    def _looks_like_selection(self, lower: str) -> bool:
        return lower in {"first", "first one", "second", "second one", "third", "third one", "number 1", "number 2", "number 3"}

    def _resolve_place_reference(self, text: str, places: list[dict]) -> dict | None:
        if not places:
            return None
        lower = text.lower().strip()
        ordinal_patterns = {
            0: ["first", "first one", "number 1", "#1", "option 1"],
            1: ["second", "second one", "number 2", "#2", "option 2"],
            2: ["third", "third one", "number 3", "#3", "option 3"],
        }
        for idx, patterns in ordinal_patterns.items():
            if idx < len(places) and any(p in lower for p in patterns):
                return places[idx]
        for place in places:
            name = (place.get("name") or "").lower()
            if name and name in lower:
                return place
        return None

    def _place_query(self, text: str) -> str:
        lower = text.lower()
        aliases = {
            "cafe": "coffee shop",
            "coffee": "coffee shop",
            "food": "restaurant",
            "hiking": "hiking trail",
        }
        for category in ["waterfall", "restaurant", "coffee", "cafe", "food", "gas station", "park", "hiking", "breakfast", "lunch", "dinner"]:
            if category in lower:
                return aliases.get(category, category)
        return text
