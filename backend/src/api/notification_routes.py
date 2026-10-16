"""Real-time role-based In-App Notification Center API."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import User, Claim, Adjuster, Policy
from src.database.hardening_models import (
    ClaimEvidenceRequest,
    ClaimException,
    ClaimAuditEvent,
    OutboxEvent,
    UserNotificationRead,
)
from src.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


class MarkReadRequest(BaseModel):
    notification_id: Optional[str] = None
    all: bool = False


def _format_time_ago(dt: Optional[datetime]) -> str:
    if not dt:
        return "Recent"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


@router.get("")
def get_user_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return real-time role-relevant notifications for the authenticated user."""
    user_id = str(current_user.id)
    tenant_id = str(current_user.tenant_id or "")

    # Read notification IDs for this user
    read_rows = db.query(UserNotificationRead.notification_id).filter(
        UserNotificationRead.user_id == user_id
    ).all()
    read_ids = {r[0] for r in read_rows}

    items: list[dict[str, Any]] = []
    user_role = (current_user.role or "").lower()

    # 1. Claimant notifications
    if user_role == "claimant":
        user_claims = db.query(Claim).filter(Claim.claimant_id == user_id).all()
        claim_map = {c.id: c for c in user_claims}
        claim_ids = list(claim_map.keys())

        if claim_ids:
            # Evidence requests from adjuster
            ev_reqs = (
                db.query(ClaimEvidenceRequest)
                .filter(
                    ClaimEvidenceRequest.claim_id.in_(claim_ids),
                    ClaimEvidenceRequest.status == "open",
                )
                .order_by(ClaimEvidenceRequest.requested_at.desc())
                .limit(10)
                .all()
            )
            for req in ev_reqs:
                cl = claim_map.get(req.claim_id)
                nid = f"ev-req-{req.id}"
                items.append({
                    "id": nid,
                    "title": f"Evidence Requested: #{cl.ticket_id if cl else 'Claim'}",
                    "message": req.request_text or "Your adjuster requested additional evidence.",
                    "time": _format_time_ago(req.requested_at),
                    "unread": nid not in read_ids,
                    "ticket_id": cl.ticket_id if cl else "",
                    "url": f"/claimant/claims/{cl.ticket_id}" if cl else "/claimant/claims",
                })

            # Status transitions on submitted claims
            for cl in user_claims:
                if cl.status and cl.status.lower() in ("under_review", "approved", "partially_approved", "rejected", "closed"):
                    nid = f"claim-status-{cl.id}-{cl.status}"
                    st_label = cl.status.replace("_", " ").capitalize()
                    items.append({
                        "id": nid,
                        "title": f"Claim #{cl.ticket_id}: {st_label}",
                        "message": f"Your claim is currently in {st_label.lower()} status.",
                        "time": _format_time_ago(getattr(cl, "updated_at", cl.created_at)),
                        "unread": nid not in read_ids,
                        "ticket_id": cl.ticket_id,
                        "url": f"/claimant/claims/{cl.ticket_id}",
                    })

    # 2. Adjuster notifications
    elif user_role == "adjuster":
        adj_profile = db.query(Adjuster).filter(Adjuster.user_id == user_id).first()
        if adj_profile:
            # Newly assigned claims
            assigned_claims = (
                db.query(Claim)
                .filter(Claim.assigned_adjuster_id == adj_profile.id)
                .order_by(Claim.created_at.desc())
                .limit(10)
                .all()
            )
            for cl in assigned_claims:
                nid = f"adj-assigned-{cl.id}"
                items.append({
                    "id": nid,
                    "title": f"Assigned Claim #{cl.ticket_id}",
                    "message": f"Claim for {cl.insurance_type or 'general insurance'} is in your queue.",
                    "time": _format_time_ago(cl.created_at),
                    "unread": nid not in read_ids,
                    "ticket_id": cl.ticket_id,
                    "url": f"/adjuster/claims/{cl.ticket_id}",
                })

            # Claimant responses to evidence requests
            ev_responses = (
                db.query(ClaimEvidenceRequest, Claim)
                .join(Claim, ClaimEvidenceRequest.claim_id == Claim.id)
                .filter(
                    ClaimEvidenceRequest.adjuster_id == adj_profile.id,
                    ClaimEvidenceRequest.status == "responded",
                )
                .order_by(ClaimEvidenceRequest.responded_at.desc())
                .limit(10)
                .all()
            )
            for req, cl in ev_responses:
                nid = f"ev-resp-{req.id}"
                items.append({
                    "id": nid,
                    "title": f"Evidence Uploaded: #{cl.ticket_id}",
                    "message": req.response_note or "Claimant submitted response to evidence request.",
                    "time": _format_time_ago(req.responded_at),
                    "unread": nid not in read_ids,
                    "ticket_id": cl.ticket_id,
                    "url": f"/adjuster/claims/{cl.ticket_id}",
                })

            # Open high-severity exceptions on assigned claims
            assigned_ids = [c.id for c in assigned_claims]
            if assigned_ids:
                exc_list = (
                    db.query(ClaimException, Claim)
                    .join(Claim, ClaimException.claim_id == Claim.id)
                    .filter(
                        ClaimException.claim_id.in_(assigned_ids),
                        ClaimException.status == "open",
                        ClaimException.severity == "high",
                    )
                    .order_by(ClaimException.created_at.desc())
                    .limit(10)
                    .all()
                )
                for exc, cl in exc_list:
                    nid = f"exc-{exc.id}"
                    items.append({
                        "id": nid,
                        "title": f"High Priority Exception: #{cl.ticket_id}",
                        "message": exc.reason,
                        "time": _format_time_ago(exc.created_at),
                        "unread": nid not in read_ids,
                        "ticket_id": cl.ticket_id,
                        "url": f"/adjuster/claims/{cl.ticket_id}",
                    })

    # 3. Admin notifications
    elif user_role == "admin":
        # Missing policy knowledge escalations
        missing_know = (
            db.query(ClaimException, Claim)
            .join(Claim, ClaimException.claim_id == Claim.id)
            .filter(
                ClaimException.event_type == "missing_policy_knowledge",
                ClaimException.status == "open",
            )
            .order_by(ClaimException.created_at.desc())
            .limit(10)
            .all()
        )
        for exc, cl in missing_know:
            nid = f"admin-miss-know-{exc.id}"
            items.append({
                "id": nid,
                "title": f"Missing Knowledge: #{cl.ticket_id}",
                "message": exc.reason,
                "time": _format_time_ago(exc.created_at),
                "unread": nid not in read_ids,
                "ticket_id": cl.ticket_id,
                "url": "/adjuster/knowledge",
            })

        # Failed outbox events
        failed_outbox = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.status == "failed")
            .order_by(OutboxEvent.created_at.desc())
            .limit(5)
            .all()
        )
        for evt in failed_outbox:
            nid = f"outbox-{evt.id}"
            items.append({
                "id": nid,
                "title": "Failed Outbox Event",
                "message": f"Event '{evt.event_type}' delivery failed: {evt.last_error or 'Max retries exhausted'}",
                "time": _format_time_ago(evt.created_at),
                "unread": nid not in read_ids,
                "ticket_id": "",
                "url": "/admin/audit",
            })

        # High-value claims
        high_val_claims = (
            db.query(Claim)
            .filter(
                Claim.estimated_claim_amount >= 50000,
                Claim.status.notin_(["draft", "discarded", "pending_confirmation"]),
            )
            .order_by(Claim.created_at.desc())
            .limit(5)
            .all()
        )
        for cl in high_val_claims:
            nid = f"high-val-{cl.id}"
            items.append({
                "id": nid,
                "title": f"High-Value Claim: #{cl.ticket_id}",
                "message": f"Claim estimated at ${int(cl.estimated_claim_amount or 0):,} requires underwriting oversight.",
                "time": _format_time_ago(cl.created_at),
                "unread": nid not in read_ids,
                "ticket_id": cl.ticket_id,
                "url": "/admin/claims",
            })

    # Default fallback welcome notification if no events exist
    if not items:
        nid = "welcome-live-system"
        items.append({
            "id": nid,
            "title": "IntelliClaim Notification Hub",
            "message": "All claim activities, evidence updates, and exceptions will appear here in real time.",
            "time": "Active",
            "unread": nid not in read_ids,
            "ticket_id": "",
            "url": "/",
        })

    return {
        "items": items,
        "unread_count": sum(1 for n in items if n["unread"]),
    }


@router.post("/mark-read")
def mark_notifications_read(
    payload: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a specific notification or all notifications as read."""
    user_id = str(current_user.id)
    tenant_id = str(current_user.tenant_id or "")

    if payload.all:
        notifs_res = get_user_notifications(current_user=current_user, db=db)
        for item in notifs_res.get("items", []):
            nid = str(item.get("id"))
            existing = db.query(UserNotificationRead).filter(
                UserNotificationRead.user_id == user_id,
                UserNotificationRead.notification_id == nid,
            ).first()
            if not existing:
                db.add(UserNotificationRead(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    notification_id=nid,
                ))
    elif payload.notification_id:
        nid = payload.notification_id.strip()
        existing = db.query(UserNotificationRead).filter(
            UserNotificationRead.user_id == user_id,
            UserNotificationRead.notification_id == nid,
        ).first()
        if not existing:
            db.add(UserNotificationRead(
                tenant_id=tenant_id,
                user_id=user_id,
                notification_id=nid,
            ))

    db.commit()
    return {"status": "ok"}
