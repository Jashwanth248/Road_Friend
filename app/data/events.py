from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from app.config import settings


class EventSink:
    def emit(self, event_type: str, payload: dict) -> None:
        path = Path(settings.event_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"event_type": event_type, "timestamp": datetime.now(timezone.utc).isoformat(), **payload}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
