"""Channel-neutral conversation events emitted by text and voice adapters."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict
import uuid

from src.config import settings

def make_event(event_type: str, ticket_id: str, **payload: Any) -> Dict[str, Any]:
    event = dict(payload)
    text_value = event.get("text")
    if isinstance(text_value, str) and settings.VOICE_MAX_EVENT_TEXT_CHARS:
        event["text"] = text_value[: settings.VOICE_MAX_EVENT_TEXT_CHARS]
    return {
        "schema_version": 2,
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **event,
    }
