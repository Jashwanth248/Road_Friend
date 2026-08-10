import pytest

from app.agents.orchestrator import RoadMateOrchestrator
from app.integrations.places import PlacesConfigurationError
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
async def test_no_maps_key_uses_background_nearby_search(monkeypatch):
    agent = RoadMateOrchestrator()

    async def no_google_places(query, location, limit=8):
        raise PlacesConfigurationError("no key")

    async def fake_nearby(query, location, limit=8):
        return [
            {
                "id": "osm-1",
                "name": "Neighborhood Coffee",
                "address": "100 Main St",
                "location": {"latitude": 38.586, "longitude": -121.406},
                "rating": 4.7,
                "reviews": None,
                "rating_source": "public web snippet",
                "distance_miles": 0.3,
                "maps_url": "https://www.google.com/maps/search/?api=1&query=38.586,-121.406",
                "source": "OpenStreetMap",
            },
            {
                "id": "osm-2",
                "name": "Second Cafe",
                "address": None,
                "location": {"latitude": 38.588, "longitude": -121.408},
                "rating": None,
                "reviews": None,
                "rating_source": None,
                "distance_miles": 0.8,
                "maps_url": None,
                "source": "OpenStreetMap",
            },
        ]

    monkeypatch.setattr(agent.places, "search", no_google_places)
    monkeypatch.setattr(agent.nearby, "search", fake_nearby)
    loc = Location(latitude=38.5859, longitude=-121.4058)

    result = await agent.handle(ChatRequest(message="take me to nearest coffee location", location=loc, session_id="s3"))
    assert result.intent == "places"
    assert "Neighborhood Coffee" in result.text
    assert "0.3 miles" in result.text
    assert result.permission_request is None


@pytest.mark.asyncio
async def test_missing_location_requests_permission():
    agent = RoadMateOrchestrator()
    result = await agent.handle(ChatRequest(message="coffee near me", session_id="s2"))
    assert result.intent == "location_required"
