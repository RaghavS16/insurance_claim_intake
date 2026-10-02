"""Append-only system audit logging for consequential actions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.database.hardening_models import SystemAuditEvent


def append_system_audit(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: Optional[str],
    event_type: str,
    resource_type: str,
    resource_id: Optional[str],
    action: str,
    payload: dict[str, Any] | None = None,
) -> SystemAuditEvent:
    """Append a hash-chained event. Payload must already be redacted of raw PII/secrets."""
    tenant = str(tenant_id or "")
    if not tenant:
        raise ValueError("tenant_id is required for system audit events")

    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"system-audit:{tenant}"},
        )

    last = (
        db.query(SystemAuditEvent)
        .filter(SystemAuditEvent.tenant_id == tenant)
        .order_by(SystemAuditEvent.sequence_no.desc())
        .with_for_update()
        .first()
    )
    sequence_no = int(last.sequence_no) + 1 if last else 1
    previous_hash = last.event_hash if last else None
    body = {
        "tenant_id": tenant,
        "sequence_no": sequence_no,
        "previous_hash": previous_hash,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "action": action,
        "payload": payload or {},
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    row = SystemAuditEvent(
        id=str(uuid.uuid4()),
        tenant_id=tenant,
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        payload_json=payload or {},
        sequence_no=sequence_no,
        previous_hash=previous_hash,
        event_hash=event_hash,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    return row
