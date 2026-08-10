from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

import httpx

from app.data.events import EventSink
from app.integrations.browser_actions import BrowserActions
from app.integrations.gemini import GeminiConfigurationError, GeminiFriend
from app.integrations.gmail import GmailClient, GmailConfigurationError
from app.integrations.local_ai import LocalAI
from app.integrations.macos_messages import MacMessagesClient
from app.integrations.nearby_search import NearbySearchClient
from app.integrations.places import PlacesClient, PlacesConfigurationError
from app.integrations.routes import RoutesClient
from app.integrations.spotify import SpotifyClient
from app.integrations.web_search import WebSearchClient
from app.ml.recommender import rank_places
from app.models import ChatRequest, ChatResponse, Location, PermissionRequest, ToolResult
from app.permissions import PermissionBroker

YES = {"yes", "yep", "yeah", "allow", "okay", "ok", "go ahead", "sure", "do it"}
NO = {"no", "nope", "deny", "cancel", "don't", "do not"}


class RoadMateOrchestrator:
    """Personal companion orchestrator with background research, memory and permissioned actions."""

    def __init__(self, rag=None) -> None:
        self.places = PlacesClient()
        self.nearby = NearbySearchClient()
        self.routes = RoutesClient()
        self.spotify = SpotifyClient()
        self.gmail = GmailClient()
        self.messages = MacMessagesClient()
        self.gemini = GeminiFriend()
        self.local_ai = LocalAI()
        self.web = WebSearchClient()
        self.browser = BrowserActions()
        self.events = EventSink()
        self.permissions = PermissionBroker()
        self.rag = rag
        self.sessions: dict[str, dict[str, Any]] = {}

    def _session(self, session_id: str) -> dict[str, Any]:
        return self.sessions.setdefault(session_id, {"places": [], "selected_place": None, "location": None, "history": [], "documents": []})

    def register_document(self, session_id: str, filename: str) -> None:
        state = self._session(session_id)
        if filename not in state["documents"]:
            state["documents"].append(filename)
        self.permissions.grant(session_id, "files_read")

    async def handle(self, req: ChatRequest) -> ChatResponse:
        text = req.message.strip()
        lower = text.lower()
        state = self._session(req.session_id)
        if req.location:
            state["location"] = req.location
        location: Location | None = req.location or state.get("location")
        self.events.emit("chat_message", {"session_id": req.session_id, "text_length": len(text)})

        pending = self.permissions.pending(req.session_id)
        if pending and lower in YES:
            self.permissions.consume(req.session_id)
            return self._remember(state, text, await self._execute_permission(req.session_id, pending, location, state))
        if pending and lower in NO:
            self.permissions.deny(req.session_id)
            return self._remember(state, text, ChatResponse(text="Okay, I won't do that.", intent="permission_denied"))

        media = self._parse_browser_request(text)
        if media:
            pending = self.permissions.request(req.session_id, "browser_open", f"Open {media['label']} in your browser for: {media['query']}", "browser_open", media)
            return self._remember(state, text, ChatResponse(
                text=f"Sure. I can open {media['label']} and search for “{media['query']}”. Want me to open it?",
                intent="permission",
                permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title=f"Open {media['label']}?", reason=pending.reason, scope="once"),
            ))

        selected = self._resolve_place_reference(text, state.get("places", []))
        route_requested = any(k in lower for k in ["take me", "route me", "directions", "navigate", "get me there", "go there"])
        if selected and (route_requested or self._looks_like_selection(lower)):
            state["selected_place"] = selected
            if not route_requested:
                return self._remember(state, text, ChatResponse(text=f"Got it — {selected['name']}. Say ‘take me there’ and I’ll work out the route.", intent="place_selection", tools=[ToolResult(tool="selected_place", data=selected)]))
            return self._remember(state, text, await self._route_to_place(selected, location, req.session_id))
        if route_requested and state.get("selected_place"):
            return self._remember(state, text, await self._route_to_place(state["selected_place"], location, req.session_id))

        if self._is_place_search(lower):
            return self._remember(state, text, await self._handle_place_search(text, location, state, req.session_id))

        if self._looks_like_file_request(lower):
            if state["documents"] and self._looks_like_document_question(lower):
                return self._remember(state, text, await self._answer_from_documents(text, state))
            pending = self.permissions.request(req.session_id, "files_read", "Open a file picker so you choose exactly which local document Road Friend may read.", "choose_file")
            return self._remember(state, text, ChatResponse(text="I can read it. I won't browse your Mac by myself — may I open a file picker so you can choose the document?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Choose a document?", reason=pending.reason, scope="once")))

        if self._looks_like_gmail_read(lower):
            if not self.permissions.has(req.session_id, "gmail_read"):
                pending = self.permissions.request(req.session_id, "gmail_read", "Read Gmail metadata and snippets for this Road Friend session.", "gmail_read")
                return self._remember(state, text, ChatResponse(text="I can check your Gmail. May I access it for this session?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Allow Gmail access?", reason=pending.reason, scope="session")))
            return self._remember(state, text, await self._read_gmail(text))

        draft = self._parse_email_send(text)
        if draft:
            pending = self.permissions.request(req.session_id, "gmail_send", f"Send one email to {draft['to']}.", "gmail_send", draft)
            return self._remember(state, text, ChatResponse(text=f"I prepared the email to {draft['to']}: “{draft['body']}”. Should I send it?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Send this email?", reason=pending.reason, scope="once")))

        sms = self._parse_text_send(text)
        if sms:
            pending = self.permissions.request(req.session_id, "messages_send", f"Send one message to {sms['recipient']} through macOS Messages.", "messages_send", sms)
            return self._remember(state, text, ChatResponse(text=f"I prepared this message for {sms['recipient']}: “{sms['body']}”. Should I send it?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Send this message?", reason=pending.reason, scope="once")))

        if lower.startswith("pause") or "pause music" in lower:
            result = await self.spotify.pause()
            return self._remember(state, text, ChatResponse(text="Done — I sent pause to Spotify." if result.get("mode") == "live" else result["message"], intent="music", tools=[ToolResult(tool="spotify", data=result)]))

        if any(k in lower for k in ["red light", "green light", "traffic signal", "stop sign"]):
            return self._remember(state, text, ChatResponse(text="I can explain what a sign or signal means, but I won't make the driving decision for you. Follow the real signal, signs, road conditions and law.", intent="road_awareness", safety_notice="Road-awareness output is advisory only."))

        if lower in {"hi", "hello", "hey", "hey roadmate", "hey road friend"}:
            return self._remember(state, text, ChatResponse(text="Hey! I’m here. Ask me anything, ask me to search the web, find somewhere nearby, open YouTube or Prime, read a file you choose, or help with Gmail.", intent="greeting"))

        return self._remember(state, text, await self._general_answer(text, state, location))

    async def _execute_permission(self, session_id: str, pending, location: Location | None, state: dict[str, Any]) -> ChatResponse:
        if pending.capability == "browser_open":
            return ChatResponse(text=f"Opening {pending.payload['label']} for you.", intent="browser_open", ui_action="open_url", ui_data={"url": pending.payload["url"], "label": pending.payload["label"]})
        if pending.capability == "files_read":
            return ChatResponse(text="Okay — choose the file you want me to read.", intent="files", ui_action="choose_file")
        if pending.capability == "gmail_read":
            self.permissions.grant(session_id, "gmail_read")
            if not self.gmail.connected():
                return ChatResponse(text="Okay. I’ll open the Google sign-in flow. After you connect, ask me to check your inbox again.", intent="gmail_connect", ui_action="connect_gmail")
            return await self._read_gmail("latest emails")
        if pending.capability == "gmail_send":
            try:
                result = await self.gmail.send(**pending.payload)
                return ChatResponse(text=f"Sent it to {pending.payload['to']}.", intent="gmail_send", tools=[ToolResult(tool="gmail_send", data=result)])
            except GmailConfigurationError as exc:
                return ChatResponse(text=str(exc), intent="configuration", ui_action="connect_gmail")
        if pending.capability == "messages_send":
            result = await self.messages.send(**pending.payload)
            return ChatResponse(text=result.get("message") or "Message sent.", intent="messages_send", tools=[ToolResult(tool="macos_messages", data=result)])
        return ChatResponse(text="Permission was granted, but I don't recognize that action.", intent="permission")

    async def _handle_place_search(self, text: str, location: Location | None, state: dict[str, Any], session_id: str) -> ChatResponse:
        if not location:
            return ChatResponse(text="I need your location first. Click Enable Location and allow it, then ask me again.", intent="location_required")
        query = self._place_query(text)
        source = "Google Places"
        try:
            places = await self.places.search(query, location, 8)
            ranked = rank_places(places)
        except (PlacesConfigurationError, httpx.HTTPStatusError):
            source = "OpenStreetMap + public web"
            try:
                ranked = await self.nearby.search(query, location, 8)
            except Exception as exc:
                return ChatResponse(text=f"I couldn't finish the nearby search in the background just now: {exc}. You can try again in a moment.", intent="places_error")

        state["places"] = ranked
        state["selected_place"] = None
        if not ranked:
            return ChatResponse(text=f"I couldn't find anything useful for {query} nearby.", intent="places")

        top = ranked[:4]
        parts: list[str] = []
        for i, p in enumerate(top, 1):
            distance = p.get("distance_miles")
            distance_text = f", about {distance:.1f} miles away" if isinstance(distance, (int, float)) else ""
            rating = p.get("rating")
            rating_text = f", rated {rating} out of 5" if rating else ", rating not verified"
            parts.append(f"{i}. {p['name']}{rating_text}{distance_text}")

        verified_ratings = any(p.get("rating") for p in top)
        if verified_ratings:
            intro = "I checked nearby places in the background and found four good options."
        else:
            intro = "I checked nearby places in the background and found four real options. I couldn't verify ratings for all of them, so the distance information is the more reliable comparison."
        nearest = min(top, key=lambda p: p.get("distance_miles", 10**9))
        tail = f"The closest one I found is {nearest['name']}"
        if nearest.get("distance_miles") is not None:
            tail += f", about {nearest['distance_miles']:.1f} miles away"
        tail += ". Which one do you want to go to? You can say first, second, third, fourth, or the place name."
        return ChatResponse(text=f"{intro} {'; '.join(parts)}. {tail}", intent="places", tools=[ToolResult(tool="places_search", data={"source": source, "places": ranked})])

    async def _general_answer(self, text: str, state: dict[str, Any], location: Location | None) -> ChatResponse:
        try:
            results = self.web.search(text, 5)
        except Exception as exc:
            results = []
            search_error = str(exc)
        else:
            search_error = None

        if results:
            evidence = "\n".join(f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results)
            prompt = (
                f"The user asked: {text}\n\nThese are fresh web search results:\n{evidence}\n\n"
                "Answer like a helpful friend speaking naturally. Summarize the useful points, avoid sounding robotic, and do not invent facts not supported by the results."
            )
            if self.local_ai.configured():
                answer = await self.local_ai.answer(prompt, state.get("history", []))
            elif self.gemini.configured():
                answer = (await self.gemini.answer(prompt, state.get("history", []), use_google_search=False))["text"]
            else:
                top = results[:3]
                answer = "I checked the web. " + " ".join(f"{r['title']} says {r['snippet'][:180]}." for r in top)
            return ChatResponse(text=answer, intent="web_search", tools=[ToolResult(tool="web_search", data=results)])

        if self.local_ai.configured():
            return ChatResponse(text=await self.local_ai.answer(text, state.get("history", [])), intent="general")
        if self.gemini.configured():
            try:
                result = await self.gemini.answer(text, state.get("history", []), use_google_search=False)
                return ChatResponse(text=result["text"], intent="general")
            except (GeminiConfigurationError, Exception):
                pass
        msg = "I couldn’t reach web search just now."
        if search_error:
            msg += f" Search error: {search_error}"
        msg += " You can still ask me to open Google, Maps, YouTube or Prime, or install Ollama for fully local conversation."
        return ChatResponse(text=msg, intent="general")

    async def _read_gmail(self, text: str) -> ChatResponse:
        try:
            query = None
            match = re.search(r"(?:from|about)\s+(.+)$", text, re.I)
            if match and len(match.group(1)) < 80:
                query = match.group(1)
            emails = await self.gmail.recent(max_results=5, query=query)
        except GmailConfigurationError as exc:
            return ChatResponse(text=str(exc), intent="configuration", ui_action="connect_gmail")
        if not emails:
            return ChatResponse(text="I didn’t find matching emails.", intent="gmail")
        summary = "; ".join(f"{i}. {e['subject']} from {e['from']}. {e['snippet'][:120]}" for i, e in enumerate(emails[:5], 1))
        return ChatResponse(text=f"I checked your inbox. {summary}", intent="gmail", tools=[ToolResult(tool="gmail_recent", data=emails)])

    async def _answer_from_documents(self, text: str, state: dict[str, Any]) -> ChatResponse:
        if not self.rag:
            return ChatResponse(text="The document store is unavailable.", intent="documents")
        evidence = self.rag.query(text, 4)
        if not evidence:
            return ChatResponse(text="I couldn’t find that in the documents you shared.", intent="documents")
        context = "\n\n".join(str(x) for x in evidence)
        prompt = f"Answer only from this document evidence. Question: {text}\nEvidence:\n{context}"
        if self.local_ai.configured():
            answer = await self.local_ai.answer(prompt, [])
            return ChatResponse(text=answer, intent="documents", tools=[ToolResult(tool="rag", data=evidence)])
        if self.gemini.configured():
            answer = await self.gemini.answer(prompt, history=[], use_google_search=False)
            return ChatResponse(text=answer["text"], intent="documents", tools=[ToolResult(tool="rag", data=evidence)])
        return ChatResponse(text=f"Here’s what I found in your document: {context[:1200]}", intent="documents", tools=[ToolResult(tool="rag", data=evidence)])

    async def _route_to_place(self, place: dict, location: Location | None, session_id: str) -> ChatResponse:
        if not location:
            return ChatResponse(text="I need your current location first.", intent="location_required")
        loc = place.get("location") or {}
        if loc.get("latitude") is None or loc.get("longitude") is None:
            return ChatResponse(text=f"I don’t have coordinates for {place.get('name', 'that place')}.", intent="route_error")
        destination = Location(latitude=loc["latitude"], longitude=loc["longitude"])
        route = await self.routes.route(location, destination, "DRIVE")
        if route.get("mode") != "live":
            straight = place.get("distance_miles")
            distance_text = f" about {straight:.1f} miles away in a straight line" if isinstance(straight, (int, float)) else " nearby"
            params = urlencode({
                "api": 1,
                "origin": f"{location.latitude},{location.longitude}",
                "destination": f"{destination.latitude},{destination.longitude}",
                "travelmode": "driving",
            })
            payload = {"label": "Google Maps directions", "query": place["name"], "url": f"https://www.google.com/maps/dir/?{params}"}
            pending = self.permissions.request(session_id, "browser_open", f"Open driving directions to {place['name']} in Google Maps.", "browser_open", payload)
            return ChatResponse(
                text=f"{place['name']} is{distance_text}. I don't have a verified live traffic ETA without the Routes API. Want me to open Google Maps directions to it?",
                intent="permission",
                permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title=f"Navigate to {place['name']}?", reason=pending.reason, scope="once"),
            )
        routes = route.get("routes", [])
        if not routes:
            return ChatResponse(text=f"I couldn’t calculate a route to {place['name']}.", intent="route_error")
        best = routes[0]
        meters = best.get("distanceMeters")
        duration = best.get("duration") or "unknown time"
        miles = round(meters / 1609.344, 1) if meters else None
        distance_text = f"{miles} miles" if miles is not None else "an unknown distance"
        return ChatResponse(text=f"Okay — {place['name']} is about {distance_text} away and the current driving estimate is {duration}. That ETA includes traffic.", intent="route", tools=[ToolResult(tool="route", data={"place": place, **route})])

    def _parse_browser_request(self, text: str) -> dict[str, str] | None:
        lower = text.lower().strip()
        patterns = [
            (r"(?:search|google)\s+(?:for\s+)?(.+?)(?:\s+on google)?$", "Google", self.browser.google_search),
            (r"(?:open|search)\s+(?:google maps|maps)\s+(?:for\s+)?(.+)$", "Google Maps", self.browser.google_maps),
            (r"(?:play|search|open)\s+(.+?)\s+(?:on\s+)?youtube$", "YouTube", self.browser.youtube_search),
            (r"(?:youtube)\s+(.+)$", "YouTube", self.browser.youtube_search),
            (r"(?:play|search|open)\s+(.+?)\s+(?:on\s+)?(?:prime|prime video|amazon prime)$", "Prime Video", self.browser.prime_search),
            (r"(?:prime|prime video)\s+(.+)$", "Prime Video", self.browser.prime_search),
        ]
        for pattern, label, builder in patterns:
            match = re.search(pattern, lower, re.I)
            if match:
                query = match.group(1).strip()
                return {"label": label, "query": query, "url": builder(query)}
        return None

    def _remember(self, state: dict[str, Any], user_text: str, response: ChatResponse) -> ChatResponse:
        state["history"].append({"role": "user", "text": user_text})
        state["history"].append({"role": "assistant", "text": response.text})
        state["history"] = state["history"][-16:]
        return response

    def _looks_like_file_request(self, lower: str) -> bool:
        return any(k in lower for k in ["my file", "my document", "my pdf", "my resume", "open a file", "read a file", "read document", "open document", "choose a file"])

    def _looks_like_document_question(self, lower: str) -> bool:
        return any(k in lower for k in ["what does", "summarize", "according to", "in the document", "in my file", "in my resume", "tell me about"])

    def _looks_like_gmail_read(self, lower: str) -> bool:
        return any(k in lower for k in ["my email", "my gmail", "my inbox", "latest email", "recent email", "check email", "check gmail"])

    def _parse_email_send(self, text: str) -> dict[str, str] | None:
        match = re.search(r"(?:send|email)\s+(?:an?\s+email\s+)?to\s+([\w.+-]+@[\w.-]+)\s+(?:saying|that says|message)?\s*[:,-]?\s*(.+)", text, re.I)
        return {"to": match.group(1), "subject": "Message from Road Friend", "body": match.group(2).strip()} if match else None

    def _parse_text_send(self, text: str) -> dict[str, str] | None:
        match = re.search(r"(?:text|message)\s+([+\w@.()-]+)\s+(?:saying|that says)?\s*[:,-]?\s*(.+)", text, re.I)
        return {"recipient": match.group(1), "body": match.group(2).strip()} if match else None

    def _is_place_search(self, lower: str) -> bool:
        return any(k in lower for k in ["near me", "nearby", "restaurant", "waterfall", "coffee", "food", "gas station", "park", "hiking", "cafe", "breakfast", "lunch", "dinner", "nearest", "closest"])

    def _looks_like_selection(self, lower: str) -> bool:
        return lower in {"first", "first one", "second", "second one", "third", "third one", "fourth", "fourth one", "number 1", "number 2", "number 3", "number 4"}

    def _resolve_place_reference(self, text: str, places: list[dict]) -> dict | None:
        if not places:
            return None
        lower = text.lower().strip()
        ordinal_patterns = {
            0: ["first", "first one", "number 1", "#1", "option 1"],
            1: ["second", "second one", "number 2", "#2", "option 2"],
            2: ["third", "third one", "number 3", "#3", "option 3"],
            3: ["fourth", "fourth one", "number 4", "#4", "option 4"],
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
        aliases = {"cafe": "coffee shop", "coffee": "coffee shop", "food": "restaurant", "hiking": "hiking trail"}
        for category in ["waterfall", "restaurant", "coffee", "cafe", "food", "gas station", "park", "hiking", "breakfast", "lunch", "dinner"]:
            if category in lower:
                return aliases.get(category, category)
        return text
