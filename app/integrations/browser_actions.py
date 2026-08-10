from __future__ import annotations

from urllib.parse import quote_plus


class BrowserActions:
    """Builds user-visible browser URLs; the browser opens them only after permission."""

    @staticmethod
    def google_search(query: str) -> str:
        return f"https://www.google.com/search?q={quote_plus(query)}"

    @staticmethod
    def google_maps(query: str) -> str:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"

    @staticmethod
    def youtube_search(query: str) -> str:
        return f"https://www.youtube.com/results?search_query={quote_plus(query)}"

    @staticmethod
    def prime_search(query: str) -> str:
        return f"https://www.primevideo.com/search/ref=atv_nb_sr?phrase={quote_plus(query)}"
