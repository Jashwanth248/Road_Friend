import pytest

from app.agents.orchestrator import RoadMateOrchestrator
from app.models import ChatRequest, Location


@pytest.mark.asyncio
async def test_selection_then_route_uses_session_memory(monkeypatch):
    agent = RoadMateOrchestrator()
    live_places = [{
        "id": "p1", "name": "Real Coffee", "address": "1 Main St",
        "location": {"latitude": 44.57, "longitude": -123.27},
        "rating": 4.8, "reviews": 200, "maps_url": "https://maps.google.com/", "open_now": True,
    }]

    async def fake_search(query, location, limit=5):
        return live_places

    async def fake_route(origin, destination, travel_mode="DRIVE"):
        return {"mode": "live", "traffic_aware": True, "routes": [{"distanceMeters": 3218, "duration": "420s"}]}

    monkeypatch.setattr(agent.places, "search", fake_search)
    monkeypatch.setattr(agent.routes, "route", fake_route)
    loc = Location(latitude=44.56, longitude=-123.26)

    result = await agent.handle(ChatRequest(message="best coffee near me", location=loc, session_id="s1"))
    assert result.intent == "places"
    assert "Real Coffee" in result.text

    result = await agent.handle(ChatRequest(message="take me to the first one", location=loc, session_id="s1"))
    assert result.intent == "route"
    assert "Real Coffee" in result.text
    assert "2.0 miles" in result.text


@pytest.mark.asyncio
async def test_missing_location_requests_permission():
    agent = RoadMateOrchestrator()
    result = await agent.handle(ChatRequest(message="coffee near me", session_id="s2"))
    assert result.intent == "location_required"
