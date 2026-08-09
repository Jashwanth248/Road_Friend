from __future__ import annotations
from urllib.parse import quote
import httpx
from app.config import settings


class SpotifyClient:
    base = "https://api.spotify.com/v1"

    def _headers(self) -> dict[str, str] | None:
        if not settings.spotify_access_token:
            return None
        return {"Authorization": f"Bearer {settings.spotify_access_token}"}

    async def search_track(self, query: str) -> dict:
        headers = self._headers()
        if not headers:
            return {"mode": "demo", "message": "Connect Spotify OAuth to search/play music."}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base}/search?q={quote(query)}&type=track&limit=5", headers=headers)
            r.raise_for_status()
            return {"mode": "live", "tracks": r.json().get("tracks", {}).get("items", [])}

    async def pause(self) -> dict:
        headers = self._headers()
        if not headers:
            return {"mode": "demo", "message": "Connect Spotify OAuth to control playback."}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.put(f"{self.base}/me/player/pause", headers=headers)
            r.raise_for_status()
        return {"mode": "live", "status": "paused"}
