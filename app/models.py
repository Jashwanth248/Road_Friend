from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ChatRequest(BaseModel):
    message: str
    location: Location | None = None
    session_id: str = "demo"


class ToolResult(BaseModel):
    tool: str
    data: Any


class PermissionRequest(BaseModel):
    id: str
    capability: str
    title: str
    reason: str
    scope: Literal["once", "session"] = "once"


class ChatResponse(BaseModel):
    text: str
    intent: str
    tools: list[ToolResult] = Field(default_factory=list)
    speak: bool = True
    safety_notice: str | None = None
    permission_request: PermissionRequest | None = None
    ui_action: str | None = None
    ui_data: dict[str, Any] = Field(default_factory=dict)


class PlaceSearchRequest(BaseModel):
    query: str
    location: Location
    radius_m: int = Field(default=8000, ge=100, le=50000)
    limit: int = Field(default=5, ge=1, le=10)


class RouteRequest(BaseModel):
    origin: Location
    destination: Location
    travel_mode: Literal["DRIVE", "WALK", "BICYCLE"] = "DRIVE"


class VisionObservation(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    advisory_only: bool = True


class RagQuery(BaseModel):
    question: str
    top_k: int = Field(default=4, ge=1, le=10)
