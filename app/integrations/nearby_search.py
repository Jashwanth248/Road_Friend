from __future__ import annotations

import math
import re
from typing import Any

import httpx

from app.integrations.web_search import WebSearchClient
from app.models import Location


class NearbySearchClient:
    """Key-free nearby-place discovery using OpenStreetMap/Overpass.

    Distances are straight-line estimates from the user's current coordinates.
    Public-web snippets are used only to enrich ratings when a clear rating is found.
    """

    endpoint = "https://overpass-api.de/api/interpreter"

    def __init__(self) -> None:
        self.web = WebSearchClient()

    async def search(self, query: str, location: Location, limit: int = 6, radius_m: int = 8000) -> list[dict[str, Any]]:
        filters = self._filters(query)
        clauses: list[str] = []
        for key, value in filters:
            clauses.extend([
                f'node["{key}"="{value}"](around:{radius_m},{location.latitude},{location.longitude});',
                f'way["{key}"="{value}"](around:{radius_m},{location.latitude},{location.longitude});',
                f'relation["{key}"="{value}"](around:{radius_m},{location.latitude},{location.longitude});',
            ])
        overpass = "[out:json][timeout:15];(" + "".join(clauses) + ");out center tags;"
        headers = {"User-Agent": "RoadFriend/1.0 local-personal-assistant"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            response = await client.post(self.endpoint, data={"data": overpass})
            response.raise_for_status()
            elements = response.json().get("elements", [])

        places: list[dict[str, Any]] = []
        seen: set[tuple[str, int, int]] = set()
        for element in elements:
            tags = element.get("tags") or {}
            name = tags.get("name") or tags.get("brand")
            if not name:
                continue
            lat = element.get("lat") or (element.get("center") or {}).get("lat")
            lon = element.get("lon") or (element.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            key = (name.lower(), round(float(lat), 4), round(float(lon), 4))
            if key in seen:
                continue
            seen.add(key)
            distance_miles = self._haversine_miles(location.latitude, location.longitude, float(lat), float(lon))
            address = self._address(tags)
            places.append({
                "id": f"osm-{element.get('type')}-{element.get('id')}",
                "name": name,
                "address": address,
                "location": {"latitude": float(lat), "longitude": float(lon)},
                "rating": None,
                "reviews": None,
                "rating_source": None,
                "distance_miles": round(distance_miles, 2),
                "maps_url": f"https://www.google.com/maps/search/?api=1&query={float(lat)},{float(lon)}",
                "source": "OpenStreetMap",
            })

        places.sort(key=lambda p: p["distance_miles"])
        top = places[: max(limit, 4)]
        for place in top[:4]:
            self._enrich_rating(place, query)
        # Prefer clearly verified public rating, then distance. Unrated entries remain useful and honest.
        top.sort(key=lambda p: (p.get("rating") is None, -(p.get("rating") or 0), p["distance_miles"]))
        return top[:limit]

    def _enrich_rating(self, place: dict[str, Any], query: str) -> None:
        try:
            results = self.web.search(f'"{place["name"]}" {query} rating', 3)
        except Exception:
            return
        text = " ".join(f"{r.get('title', '')} {r.get('snippet', '')}" for r in results)
        patterns = [
            r"\b([1-5](?:\.\d)?)\s*(?:out of\s*5|/\s*5|stars?)\b",
            r"\brating[:\s]+([1-5](?:\.\d)?)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = float(match.group(1))
                if 1 <= value <= 5:
                    place["rating"] = value
                    place["rating_source"] = "public web snippet"
                    return

    def _filters(self, query: str) -> list[tuple[str, str]]:
        lower = query.lower()
        if "coffee" in lower or "cafe" in lower:
            return [("amenity", "cafe")]
        if any(k in lower for k in ["restaurant", "food", "breakfast", "lunch", "dinner"]):
            return [("amenity", "restaurant"), ("amenity", "fast_food")]
        if "gas" in lower or "fuel" in lower:
            return [("amenity", "fuel")]
        if "waterfall" in lower:
            return [("natural", "waterfall")]
        if "park" in lower:
            return [("leisure", "park")]
        if "hiking" in lower or "trail" in lower:
            return [("route", "hiking"), ("highway", "path")]
        return [("amenity", "cafe"), ("amenity", "restaurant")]

    @staticmethod
    def _address(tags: dict[str, Any]) -> str | None:
        parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:city"),
            tags.get("addr:state"),
        ]
        text = " ".join(str(p) for p in parts if p)
        return text or None

    @staticmethod
    def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_miles = 3958.7613
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return 2 * radius_miles * math.asin(math.sqrt(a))
