from __future__ import annotations

import re
from typing import Any

import httpx

from app.data.events import EventSink
from app.integrations.gemini import GeminiConfigurationError, GeminiFriend
from app.integrations.gmail import GmailClient, GmailConfigurationError
from app.integrations.macos_messages import MacMessagesClient
from app.integrations.places import PlacesClient, PlacesConfigurationError
from app.integrations.routes import RoutesClient
from app.integrations.spotify import SpotifyClient
from app.ml.recommender import rank_places
from app.models import ChatRequest, ChatResponse, Location, PermissionRequest, ToolResult
from app.permissions import PermissionBroker


YES = {"yes", "yep", "yeah", "allow", "okay", "ok", "go ahead", "sure", "do it"}
NO = {"no", "nope", "deny", "cancel", "don't", "do not"}


class RoadMateOrchestrator:
    """Personal companion orchestrator with private-data permissions and conversational memory."""

    def __init__(self, rag=None) -> None:
        self.places = PlacesClient()
        self.routes = RoutesClient()
        self.spotify = SpotifyClient()
        self.gmail = GmailClient()
        self.messages = MacMessagesClient()
        self.gemini = GeminiFriend()
        self.events = EventSink()
        self.permissions = PermissionBroker()
        self.rag = rag
        self.sessions: dict[str, dict[str, Any]] = {}

    def _session(self, session_id: str) -> dict[str, Any]:
        return self.sessions.setdefault(
            session_id,
            {"places": [], "selected_place": None, "location": None, "history": [], "documents": []},
        )

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
            return await self._execute_permission(req.session_id, pending, location, state)
        if pending and lower in NO:
            self.permissions.deny(req.session_id)
            return ChatResponse(text="Okay, I won't access or perform that action.", intent="permission_denied")

        selected = self._resolve_place_reference(text, state.get("places", []))
        route_requested = any(k in lower for k in ["take me", "route me", "directions", "navigate", "get me there", "go there"])
        if selected and (route_requested or self._looks_like_selection(lower)):
            state["selected_place"] = selected
            if not route_requested:
                return self._remember(state, text, ChatResponse(text=f"Selected {selected['name']}. Say 'take me there' and I'll calculate a live route from your current location.", intent="place_selection", tools=[ToolResult(tool="selected_place", data=selected)]))
            return self._remember(state, text, await self._route_to_place(selected, location))

        if route_requested and state.get("selected_place"):
            return self._remember(state, text, await self._route_to_place(state["selected_place"], location))

        if self._is_place_search(lower):
            return self._remember(state, text, await self._handle_place_search(text, location, state))

        if self._looks_like_file_request(lower):
            if state["documents"] and self._looks_like_document_question(lower):
                return self._remember(state, text, await self._answer_from_documents(text, state))
            pending = self.permissions.request(req.session_id, "files_read", "Open a file picker so you can choose exactly which local document Road Friend may read.", "choose_file")
            return self._remember(state, text, ChatResponse(text="I can read it, but I won't browse your Mac automatically. May I open a file picker so you can choose the document?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Allow document selection?", reason=pending.reason, scope="once")))

        if self._looks_like_gmail_read(lower):
            if not self.permissions.has(req.session_id, "gmail_read"):
                pending = self.permissions.request(req.session_id, "gmail_read", "Read Gmail metadata and snippets for this Road Friend session.", "gmail_read")
                return self._remember(state, text, ChatResponse(text="I can check your Gmail. May I access your Gmail for this session? Google OAuth will ask you to sign in if it isn't connected yet.", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Allow Gmail read access?", reason=pending.reason, scope="session")))
            return self._remember(state, text, await self._read_gmail(text))

        draft = self._parse_email_send(text)
        if draft:
            pending = self.permissions.request(req.session_id, "gmail_send", f"Send one email to {draft['to']}.", "gmail_send", draft)
            return self._remember(state, text, ChatResponse(text=f"I can send that email to {draft['to']}. Subject: {draft['subject']}. Message: {draft['body']}. Should I send it?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Send this email?", reason=pending.reason, scope="once")))

        sms = self._parse_text_send(text)
        if sms:
            pending = self.permissions.request(req.session_id, "messages_send", f"Send one message to {sms['recipient']} through the local macOS Messages app.", "messages_send", sms)
            return self._remember(state, text, ChatResponse(text=f"I prepared this message for {sms['recipient']}: {sms['body']}. Should I send it through Messages?", intent="permission", permission_request=PermissionRequest(id=pending.id, capability=pending.capability, title="Send this message?", reason=pending.reason, scope="once")))

        if lower.startswith("pause") or "pause music" in lower:
            result = await self.spotify.pause()
            return self._remember(state, text, ChatResponse(text="I sent the pause command to Spotify." if result.get("mode") == "live" else result["message"], intent="music", tools=[ToolResult(tool="spotify", data=result)]))

        if any(k in lower for k in ["play ", "song", "music"]):
            query = re.sub(r"^(please )?play\s+", "", text, flags=re.I)
            result = await self.spotify.search_track(query)
            return self._remember(state, text, ChatResponse(text="I searched Spotify for that request." if result.get("mode") == "live" else result["message"], intent="music", tools=[ToolResult(tool="spotify", data=result)]))

        if any(k in lower for k in ["red light", "green light", "traffic signal", "stop sign"]):
            return self._remember(state, text, ChatResponse(text="I can explain detected road signs or signal observations, but I cannot make driving decisions for you. Follow the physical signal, road signs, and applicable law.", intent="road_awareness", safety_notice="Road-awareness output is advisory only and must not be used as an authoritative go/stop command."))

        if lower in {"hi", "hello", "hey", "hey roadmate", "hey road friend"}:
            return self._remember(state, text, ChatResponse(text="Hi! I'm Road Friend. Talk to me naturally. I can answer questions, search current information with Google, find places, route you, read documents you choose, check Gmail with permission, control music, and prepare messages.", intent="greeting"))

        return self._remember(state, text, await self._general_answer(text, state, location))

    async def _execute_permission(self, session_id: str, pending, location: Location | None, state: dict[str, Any]) -> ChatResponse:
        if pending.capability == "files_read":
            return ChatResponse(text="Okay. Choose the file you want me to read. I can only access the file you select.", intent="files", ui_action="choose_file")
        if pending.capability == "gmail_read":
            self.permissions.grant(session_id, "gmail_read")
            if not self.gmail.connected():
                return ChatResponse(text="Okay. I'll open the Google OAuth connection flow. Complete it in your browser, then ask me to check your inbox again.", intent="gmail_connect", ui_action="connect_gmail")
            return await self._read_gmail("latest emails")
        if pending.capability == "gmail_send":
            try:
                result = await self.gmail.send(**pending.payload)
                return ChatResponse(text=f"Sent the email to {pending.payload['to']}.", intent="gmail_send", tools=[ToolResult(tool="gmail_send", data=result)])
            except GmailConfigurationError as exc:
                return ChatResponse(text=str(exc), intent="configuration", ui_action="connect_gmail")
        if pending.capability == "messages_send":
            result = await self.messages.send(**pending.payload)
            return ChatResponse(text=result.get("message") or f"Sent the message to {pending.payload['recipient']}.", intent="messages_send", tools=[ToolResult(tool="macos_messages", data=result)])
        return ChatResponse(text="Permission was granted, but I don't recognize that action.", intent="permission")

    async def _handle_place_search(self, text: str, location: Location | None, state: dict[str, Any]) -> ChatResponse:
        if not location:
            return ChatResponse(text="I need your location first. Click Enable Location and allow access, then ask me again.", intent="location_required")
        query = self._place_query(text)
        try:
            places = await self.places.search(query, location, 6)
        except PlacesConfigurationError as exc:
            return ChatResponse(text=str(exc), intent="configuration")
        except httpx.HTTPStatusError as exc:
            return ChatResponse(text=f"Google Places returned an error ({exc.response.status_code}). Check that Places API (New) is enabled. {exc.response.text[:240]}", intent="places_error")
        ranked = rank_places(places)
        state["places"] = ranked
        state["selected_place"] = None
        if not ranked:
            return ChatResponse(text=f"I couldn't find nearby results for {query}.", intent="places")
        spoken = []
        for i, place in enumerate(ranked[:3], start=1):
            rating = f", rated {place['rating']}" if place.get("rating") else ""
            spoken.append(f"{i}. {place['name']}{rating}")
        return ChatResponse(text="Here are the best nearby options: " + "; ".join(spoken) + ". Say 'first one', the place name, or 'take me to number 1'.", intent="places", tools=[ToolResult(tool="places_search", data=ranked)])

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
            return ChatResponse(text="I didn't find matching emails.", intent="gmail")
        summary = "; ".join(f"{i}. {e['subject']} from {e['from']}. {e['snippet'][:120]}" for i, e in enumerate(emails[:5], start=1))
        return ChatResponse(text=f"Here are the recent messages: {summary}", intent="gmail", tools=[ToolResult(tool="gmail_recent", data=emails)])

    async def _answer_from_documents(self, text: str, state: dict[str, Any]) -> ChatResponse:
        if not self.rag:
            return ChatResponse(text="The document store is unavailable.", intent="documents")
        evidence = self.rag.query(text, 4)
        if not evidence:
            return ChatResponse(text="I couldn't find that in the documents you've shared with me.", intent="documents")
        context = "\n\n".join(str(x) for x in evidence)
        if self.gemini.configured():
            answer = await self.gemini.answer(f"Answer this question only from the supplied document evidence. Question: {text}\nEvidence:\n{context}", history=[], use_google_search=False)
            return ChatResponse(text=answer["text"], intent="documents", tools=[ToolResult(tool="rag", data=evidence)])
        return ChatResponse(text=f"I found this in your document: {context[:1200]}", intent="documents", tools=[ToolResult(tool="rag", data=evidence)])

    async def _general_answer(self, text: str, state: dict[str, Any], location: Location | None) -> ChatResponse:
        if not self.gemini.configured():
            return ChatResponse(text="I can handle Maps, routes, documents, Gmail, Spotify, and permissions now. Add GEMINI_API_KEY to .env to let me answer open-ended questions using Gemini and current Google Search.", intent="general")
        location_context = f"{location.latitude:.5f}, {location.longitude:.5f}" if location else None
        try:
            result = await self.gemini.answer(text, state.get("history", []), location_context, use_google_search=True)
            return ChatResponse(text=result["text"], intent="general", tools=[ToolResult(tool="google_grounded_gemini", data={"sources": result.get("sources", [])})])
        except GeminiConfigurationError as exc:
            return ChatResponse(text=str(exc), intent="configuration")
        except Exception as exc:
            return ChatResponse(text=f"Gemini request failed: {exc}", intent="ai_error")

    def _remember(self, state: dict[str, Any], user_text: str, response: ChatResponse) -> ChatResponse:
        state["history"].append({"role": "user", "text": user_text})
        state["history"].append({"role": "assistant", "text": response.text})
        state["history"] = state["history"][-16:]
        return response

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
        return ChatResponse(text=f"Routing to {place['name']}. The best current route is about {distance_text} and {duration}. Live traffic is included in the driving ETA.", intent="route", tools=[ToolResult(tool="route", data={"place": place, **route})])

    def _looks_like_file_request(self, lower: str) -> bool:
        return any(k in lower for k in ["my file", "my document", "my pdf", "my resume", "open a file", "read a file", "read document", "open document", "choose a file"])

    def _looks_like_document_question(self, lower: str) -> bool:
        return any(k in lower for k in ["what does", "summarize", "according to", "in the document", "in my file", "in my resume", "tell me about"])

    def _looks_like_gmail_read(self, lower: str) -> bool:
        return any(k in lower for k in ["my email", "my gmail", "my inbox", "latest email", "recent email", "check email", "check gmail"])

    def _parse_email_send(self, text: str) -> dict[str, str] | None:
        match = re.search(r"(?:send|email)\s+(?:an?\s+email\s+)?to\s+([\w.+-]+@[\w.-]+)\s+(?:saying|that says|message)?\s*[:,-]?\s*(.+)", text, re.I)
        if not match:
            return None
        return {"to": match.group(1), "subject": "Message from Road Friend", "body": match.group(2).strip()}

    def _parse_text_send(self, text: str) -> dict[str, str] | None:
        match = re.search(r"(?:text|message)\s+([+\w@.()-]+)\s+(?:saying|that says)?\s*[:,-]?\s*(.+)", text, re.I)
        if not match:
            return None
        return {"recipient": match.group(1), "body": match.group(2).strip()}

    def _is_place_search(self, lower: str) -> bool:
        return any(k in lower for k in ["near me", "nearby", "restaurant", "waterfall", "coffee", "food", "gas station", "park", "hiking", "cafe", "breakfast", "lunch", "dinner"])

    def _looks_like_selection(self, lower: str) -> bool:
        return lower in {"first", "first one", "second", "second one", "third", "third one", "number 1", "number 2", "number 3"}

    def _resolve_place_reference(self, text: str, places: list[dict]) -> dict | None:
        if not places:
            return None
        lower = text.lower().strip()
        ordinal_patterns = {0: ["first", "first one", "number 1", "#1", "option 1"], 1: ["second", "second one", "number 2", "#2", "option 2"], 2: ["third", "third one", "number 3", "#3", "option 3"]}
        for idx, patterns in ordinal_patterns.items():
            if idx < len(places) and any(pattern in lower for pattern in patterns):
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
