"""Adjuster invitation acceptance and onboarding API."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.hardening_models import AdjusterInvitation
from src.database.models import Adjuster, User
from src.database.session import get_db
from src.utils.auth import create_access_token, get_password_hash
from src.utils.validators import validate_password_strength

router = APIRouter(prefix="/api/v1/auth/onboarding", tags=["Authentication"])

class AdjusterInvitationAccept(BaseModel):
    token: str = Field(..., min_length=20, max_length=256)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

def _find_invite(db: Session, raw_token: str):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return db.query(AdjusterInvitation).filter(
        AdjusterInvitation.token_hash == token_hash,
        AdjusterInvitation.accepted_at.is_(None),
    ).first()

@router.get("/adjuster/{token}")
def preview_adjuster_invitation(token: str, db: Session = Depends(get_db)):
    invite = _find_invite(db, token)
    if not invite or invite.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail="Invitation is invalid or expired.")
    return {"valid": True, "name": invite.name, "email": invite.email, "specialization": invite.specialization, "expires_at": invite.expires_at.isoformat()}

@router.post("/adjuster/accept")
def accept_adjuster_invitation(payload: AdjusterInvitationAccept, request: Request, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)):
    invite = _find_invite(db, payload.token)
    if not invite or invite.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired.")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = db.query(User).filter(
        User.email == invite.email,
        User.tenant_id == invite.tenant_id,
        User.role == "ADJUSTER",
    ).first()
    adjuster = db.query(Adjuster).filter(
        Adjuster.email == invite.email,
        Adjuster.tenant_id == invite.tenant_id,
    ).first()
    if not user or not adjuster:
        raise HTTPException(status_code=409, detail="Invitation account is no longer available.")
    if adjuster.is_active:
        raise HTTPException(status_code=409, detail="This adjuster invitation has already been completed.")

    now = datetime.now(timezone.utc)
    user.password_hash = get_password_hash(payload.password)
    user.email_verified_at = now
    user.session_version = int(getattr(user, "session_version", 1) or 1) + 1
    invite.accepted_at = now
    invite.accepted_user_id = user.id
    db.commit()

    setup_token = create_access_token(
        data={
            "sub": user.id,
            "tenant_id": user.tenant_id or "",
            "role": user.role,
            "sv": user.session_version,
            "purpose": "adjuster_onboarding",
            "amr": ["invite"],
        },
        expires_delta=timedelta(minutes=15),
    )
    return {
        "accepted": True,
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role},
        "setup_access_token": setup_token,
        "next": "register_passkey",
        "message": "Account created. Register your passkey to activate adjuster access.",
    }
