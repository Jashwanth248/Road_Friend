from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass
class PendingPermission:
    id: str
    capability: str
    reason: str
    action: str
    payload: dict[str, Any]


class PermissionBroker:
    """Session-scoped permission and confirmation state."""

    def __init__(self) -> None:
        self._grants: dict[str, set[str]] = {}
        self._pending: dict[str, PendingPermission] = {}

    def has(self, session_id: str, capability: str) -> bool:
        return capability in self._grants.get(session_id, set())

    def grant(self, session_id: str, capability: str) -> None:
        self._grants.setdefault(session_id, set()).add(capability)

    def revoke(self, session_id: str, capability: str) -> None:
        self._grants.setdefault(session_id, set()).discard(capability)

    def request(self, session_id: str, capability: str, reason: str, action: str, payload: dict[str, Any] | None = None) -> PendingPermission:
        pending = PendingPermission(
            id=str(uuid4()),
            capability=capability,
            reason=reason,
            action=action,
            payload=payload or {},
        )
        self._pending[session_id] = pending
        return pending

    def pending(self, session_id: str) -> PendingPermission | None:
        return self._pending.get(session_id)

    def consume(self, session_id: str) -> PendingPermission | None:
        return self._pending.pop(session_id, None)

    def deny(self, session_id: str) -> None:
        self._pending.pop(session_id, None)
