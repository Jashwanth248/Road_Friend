from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from ddgs import DDGS


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchClient:
    """Key-free web search for current public information."""

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = DDGS().text(query, max_results=limit)
        out: list[dict[str, Any]] = []
        for row in rows or []:
            result = SearchResult(
                title=str(row.get("title") or "Untitled"),
                url=str(row.get("href") or row.get("url") or ""),
                snippet=str(row.get("body") or row.get("snippet") or ""),
            )
            out.append(asdict(result))
        return out
