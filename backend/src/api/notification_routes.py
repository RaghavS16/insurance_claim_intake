"""Real-time role-based In-App Notification Center API with persistent user states."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import User, Claim
from src.database.hardening_models import ClaimEvidenceRequest, UserNotificationState
from src.api.deps import get_current_user
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


class NotificationActionPayload(BaseModel):
    notification_ids: Optional[List[str]] = None


def _build_raw_notifications(current_user: User, db: Session) -> List[Dict[str, Any]]:
    """Synthesizes role-based notifications from active claims and evidence workflows."""
    items: List[Dict[str, Any]] = []
    if current_user.role == "CLAIMANT":
        user_claims = db.query(Claim).filter(
            Claim.claimant_id == current_user.id,
            Claim.tenant_id == current_user.tenant_id,
            Claim.status != "discarded",
        ).order_by(Claim.updated_at.desc()).limit(10).all()
        claim_ids = [c.id for c in user_claims]
        open_reqs_by_claim: dict[str, list[ClaimEvidenceRequest]] = {str(cid): [] for cid in claim_ids}
        if claim_ids:
            for req in db.query(ClaimEvidenceRequest).filter(
                ClaimEvidenceRequest.claim_id.in_(claim_ids),
                ClaimEvidenceRequest.status == "open",
            ).all():
                open_reqs_by_claim.setdefault(str(req.claim_id), []).append(req)

        for c in user_claims:
            open_reqs = open_reqs_by_claim.get(str(c.id), [])
            for req in open_reqs:
                items.append({
                    "id": f"req-{req.id}",
                    "title": f"Action Required on #{c.ticket_id}",
                    "message": f"Adjuster requested: {req.request_text[:90]}",
                    "time": req.requested_at.strftime("%b %d, %H:%M") if req.requested_at else "Recent",
                    "unread": True,
                    "href": f"/claimant/claims/{c.ticket_id}",
                })
            if c.status in ("submitted", "under_review", "approved", "rejected"):
                items.append({
                    "id": f"clm-{c.id}-{c.status}",
                    "title": f"Claim #{c.ticket_id} — {c.status.replace('_', ' ').title()}",
                    "message": f"Your {c.insurance_type or 'insurance'} claim is currently {c.status.replace('_', ' ')}.",
                    "time": c.updated_at.strftime("%b %d, %H:%M") if c.updated_at else "Recent",
                    "unread": c.status in ("approved", "rejected"),
                    "href": f"/claimant/claims/{c.ticket_id}",
                })
    elif current_user.role == "ADJUSTER":
        from src.database.models import Adjuster
        from src.database.hardening_models import ClaimAssignment

        adj = db.query(Adjuster).filter(
            Adjuster.user_id == current_user.id,
            Adjuster.tenant_id == current_user.tenant_id,
        ).first()
        adj_ids = [str(current_user.id)]
        if adj:
            adj_ids.append(str(adj.id))

        assigned_claim_ids = [
            row[0]
            for row in db.query(ClaimAssignment.claim_id)
            .filter(
                ClaimAssignment.tenant_id == current_user.tenant_id,
                ClaimAssignment.adjuster_id.in_(adj_ids),
                ClaimAssignment.is_active.is_(True),
            )
            .all()
        ]

        if not assigned_claim_ids:
            return []

        recent_claims = db.query(Claim).filter(
            Claim.id.in_(assigned_claim_ids),
            Claim.tenant_id == current_user.tenant_id,
            Claim.status.notin_(["draft", "discarded"]),
        ).order_by(Claim.updated_at.desc()).limit(8).all()

        adj_claim_ids = [c.id for c in recent_claims]
        resp_reqs_by_claim: dict[str, list[ClaimEvidenceRequest]] = {str(cid): [] for cid in adj_claim_ids}
        if adj_claim_ids:
            for rreq in db.query(ClaimEvidenceRequest).filter(
                ClaimEvidenceRequest.claim_id.in_(adj_claim_ids),
                ClaimEvidenceRequest.status == "responded",
            ).all():
                resp_reqs_by_claim.setdefault(str(rreq.claim_id), []).append(rreq)

        for c in recent_claims:
            responded_reqs = resp_reqs_by_claim.get(str(c.id), [])
            for rreq in responded_reqs:
                items.append({
                    "id": f"resp-{rreq.id}",
                    "title": f"Claimant Responded on #{c.ticket_id}",
                    "message": f"Response submitted for: {rreq.request_text[:80]}",
                    "time": rreq.responded_at.strftime("%b %d, %H:%M") if rreq.responded_at else "Recent",
                    "unread": True,
                    "href": f"/adjuster/claims/{c.ticket_id}",
                })
            items.append({
                "id": f"queue-{c.id}",
                "title": f"Claim #{c.ticket_id} ({c.status.replace('_', ' ').title()})",
                "message": f"{(c.insurance_type or 'General').title()} claim — Est. ₹{float(c.estimated_claim_amount or 0):,.2f}",
                "time": c.updated_at.strftime("%b %d, %H:%M") if c.updated_at else "Recent",
                "unread": c.status == "submitted",
                "href": f"/adjuster/claims/{c.ticket_id}",
            })
    else:
        # ADMIN role: global visibility across tenant claims
        recent_claims = db.query(Claim).filter(
            Claim.tenant_id == current_user.tenant_id,
            Claim.status.notin_(["draft", "discarded"]),
        ).order_by(Claim.updated_at.desc()).limit(8).all()

        admin_claim_ids = [c.id for c in recent_claims]
        admin_reqs_by_claim: dict[str, list[ClaimEvidenceRequest]] = {str(cid): [] for cid in admin_claim_ids}
        if admin_claim_ids:
            for rreq in db.query(ClaimEvidenceRequest).filter(
                ClaimEvidenceRequest.claim_id.in_(admin_claim_ids),
                ClaimEvidenceRequest.status == "responded",
            ).all():
                admin_reqs_by_claim.setdefault(str(rreq.claim_id), []).append(rreq)

        for c in recent_claims:
            responded_reqs = admin_reqs_by_claim.get(str(c.id), [])
            for rreq in responded_reqs:
                items.append({
                    "id": f"resp-{rreq.id}",
                    "title": f"Claimant Responded on #{c.ticket_id}",
                    "message": f"Response submitted for: {rreq.request_text[:80]}",
                    "time": rreq.responded_at.strftime("%b %d, %H:%M") if rreq.responded_at else "Recent",
                    "unread": True,
                    "href": f"/adjuster/claims/{c.ticket_id}",
                })
            items.append({
                "id": f"queue-{c.id}",
                "title": f"Claim #{c.ticket_id} ({c.status.replace('_', ' ').title()})",
                "message": f"{(c.insurance_type or 'General').title()} claim — Est. ₹{float(c.estimated_claim_amount or 0):,.2f}",
                "time": c.updated_at.strftime("%b %d, %H:%M") if c.updated_at else "Recent",
                "unread": c.status == "submitted",
                "href": "/admin/claims",
            })
    return items


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=False)
def get_user_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return live role-based notifications, taking persistent user read/cleared states into account."""
    try:
        raw_items = _build_raw_notifications(current_user, db)

        # Retrieve saved user notification states
        states = {
            s.notification_id: s
            for s in db.query(UserNotificationState).filter(
                UserNotificationState.user_id == current_user.id,
                UserNotificationState.tenant_id == current_user.tenant_id,
            ).all()
        }

        filtered: List[Dict[str, Any]] = []
        for item in raw_items:
            nid = item["id"]
            if nid in states:
                st = states[nid]
                if st.is_cleared:
                    continue
                if st.is_read:
                    item["unread"] = False
            filtered.append(item)

        return {"items": filtered[:10]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to retrieve notifications for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve notifications.")


@router.post("/mark-read")
def mark_notifications_read(
    payload: Optional[NotificationActionPayload] = Body(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Persist read state for specified or all active notifications for the current user."""
    try:
        target_ids = payload.notification_ids if (payload and payload.notification_ids) else None
        if not target_ids:
            raw_items = _build_raw_notifications(current_user, db)
            target_ids = [item["id"] for item in raw_items]

        for nid in target_ids:
            st = db.query(UserNotificationState).filter(
                UserNotificationState.user_id == current_user.id,
                UserNotificationState.tenant_id == current_user.tenant_id,
                UserNotificationState.notification_id == nid,
            ).first()
            if not st:
                st = UserNotificationState(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    notification_id=nid,
                    is_read=True,
                    is_cleared=False,
                )
                db.add(st)
            else:
                st.is_read = True

        db.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to mark notifications read for user %s: %s", current_user.id, exc)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to mark notifications read.")


@router.post("/clear")
def clear_notifications(
    payload: Optional[NotificationActionPayload] = Body(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Persist cleared state permanently for specified or all active notifications for the current user."""
    try:
        target_ids = payload.notification_ids if (payload and payload.notification_ids) else None
        if not target_ids:
            raw_items = _build_raw_notifications(current_user, db)
            target_ids = [item["id"] for item in raw_items]

        for nid in target_ids:
            st = db.query(UserNotificationState).filter(
                UserNotificationState.user_id == current_user.id,
                UserNotificationState.tenant_id == current_user.tenant_id,
                UserNotificationState.notification_id == nid,
            ).first()
            if not st:
                st = UserNotificationState(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    notification_id=nid,
                    is_read=True,
                    is_cleared=True,
                )
                db.add(st)
            else:
                st.is_cleared = True
                st.is_read = True

        db.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to clear notifications for user %s: %s", current_user.id, exc)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to clear notifications.")
