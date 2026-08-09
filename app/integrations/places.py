from __future__ import annotations

import httpx

from app.config import settings
from app.models import Location


class PlacesConfigurationError(RuntimeError):
    pass


class PlacesClient:
    endpoint = "https://places.googleapis.com/v1/places:searchText"

    async def search(self, query: str, location: Location, limit: int = 5) -> list[dict]:
        if not settings.google_maps_api_key:
            raise PlacesConfigurationError(
                "Live place search is not configured. Add GOOGLE_MAPS_API_KEY to your local .env file and enable Places API (New)."
            )

        payload = {
            "textQuery": query,
            "pageSize": min(max(limit, 1), 20),
            "rankPreference": "DISTANCE",
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": location.latitude,
                        "longitude": location.longitude,
                    },
                    "radius": 12000.0,
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,places.location,"
                "places.rating,places.userRatingCount,places.googleMapsUri,places.currentOpeningHours"
            ),
        }
        async with httpx.AsyncClient(timeout=15) as client:
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
            "open_now": (p.get("currentOpeningHours") or {}).get("openNow"),
        }
