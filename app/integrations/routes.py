from __future__ import annotations
import httpx
from app.config import settings
from app.models import Location


class RoutesClient:
    endpoint = "https://routes.googleapis.com/directions/v2:computeRoutes"

    async def route(self, origin: Location, destination: Location, travel_mode: str = "DRIVE") -> dict:
        if not settings.google_maps_api_key:
            return {
                "mode": "demo",
                "distance_meters": None,
                "duration": None,
                "traffic_aware": False,
                "message": "Add GOOGLE_MAPS_API_KEY for live routing and traffic-aware ETA.",
            }
        payload = {
            "origin": {"location": {"latLng": {"latitude": origin.latitude, "longitude": origin.longitude}}},
            "destination": {"location": {"latLng": {"latitude": destination.latitude, "longitude": destination.longitude}}},
            "travelMode": travel_mode,
            "routingPreference": "TRAFFIC_AWARE" if travel_mode == "DRIVE" else None,
            "computeAlternativeRoutes": True,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.routeLabels",
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            routes = response.json().get("routes", [])
        return {"mode": "live", "routes": routes, "traffic_aware": travel_mode == "DRIVE"}
