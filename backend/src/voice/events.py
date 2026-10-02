"""Channel-neutral conversation events emitted by text and voice adapters."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict
import uuid

def make_event(event_type: str, ticket_id: str, **payload: Any) -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
