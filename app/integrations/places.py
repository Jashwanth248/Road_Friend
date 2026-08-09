from __future__ import annotations
import httpx
from app.config import settings
from app.models import Location


class PlacesClient:
    endpoint = "https://places.googleapis.com/v1/places:searchText"

    async def search(self, query: str, location: Location, limit: int = 5) -> list[dict]:
        if not settings.google_maps_api_key:
            return self._demo(query, location, limit)
        payload = {
            "textQuery": query,
            "maxResultCount": limit,
            "locationBias": {
                "circle": {
                    "center": {"latitude": location.latitude, "longitude": location.longitude},
                    "radius": 12000.0,
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.googleMapsUri",
        }
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            return [self._normalize(p) for p in response.json().get("places", [])]

    def _normalize(self, p: dict) -> dict:
        return {
            "id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text"),
            "address": p.get("formattedAddress"),
            "location": p.get("location"),
            "rating": p.get("rating"),
            "reviews": p.get("userRatingCount"),
            "maps_url": p.get("googleMapsUri"),
        }

    def _demo(self, query: str, location: Location, limit: int) -> list[dict]:
        names = [f"Demo {query.title()} #{i+1}" for i in range(limit)]
        return [{
            "id": f"demo-{i}", "name": name,
            "address": "Demo result — add GOOGLE_MAPS_API_KEY for live places",
            "location": {"latitude": location.latitude + i * 0.002, "longitude": location.longitude + i * 0.002},
            "rating": round(4.7 - i * 0.1, 1), "reviews": 100 - i * 7, "maps_url": None,
        } for i, name in enumerate(names)]
