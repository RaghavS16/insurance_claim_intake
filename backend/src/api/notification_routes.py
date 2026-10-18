"""Real-time role-based In-App Notification Center API."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import User, Claim
from src.database.hardening_models import ClaimEvidenceRequest
from src.api.deps import get_current_user
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=False)
def get_user_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return live role-based notifications from claim events and evidence inquiries."""
    items: List[Dict[str, Any]] = []
    try:
        if current_user.role == "CLAIMANT":
            user_claims = db.query(Claim).filter(
                Claim.claimant_id == current_user.id,
                Claim.tenant_id == current_user.tenant_id,
                Claim.status != "discarded",
            ).order_by(Claim.updated_at.desc()).limit(10).all()
            for c in user_claims:
                open_reqs = db.query(ClaimEvidenceRequest).filter(
                    ClaimEvidenceRequest.claim_id == c.id,
                    ClaimEvidenceRequest.status == "open",
                ).all()
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
        else:
            recent_claims = db.query(Claim).filter(
                Claim.tenant_id == current_user.tenant_id,
                Claim.status.notin_(["draft", "discarded"]),
            ).order_by(Claim.updated_at.desc()).limit(8).all()
            for c in recent_claims:
                responded_reqs = db.query(ClaimEvidenceRequest).filter(
                    ClaimEvidenceRequest.claim_id == c.id,
                    ClaimEvidenceRequest.status == "responded",
                ).all()
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
                    "message": f"{(c.insurance_type or 'General').title()} claim — Est. ${float(c.estimated_claim_amount or 0):,.2f}",
                    "time": c.updated_at.strftime("%b %d, %H:%M") if c.updated_at else "Recent",
                    "unread": c.status == "submitted",
                    "href": f"/adjuster/claims/{c.ticket_id}" if current_user.role == "ADJUSTER" else "/admin/claims",
                })
        return {"items": items[:10]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to retrieve notifications for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve notifications.")
