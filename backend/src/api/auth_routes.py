"""Authentication API routes for claimant and adjuster accounts."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import User
from src.utils.auth import get_password_hash, verify_password, create_access_token
from src.utils.validators import validate_email, validate_password_strength, validate_full_name, validate_phone
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    role: Literal["CLAIMANT", "ADJUSTER"] = "CLAIMANT"
    adjuster_code: Optional[str] = Field(None, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/signup")
def signup(payload: SignUpRequest, db: Session = Depends(get_db)):
    """Register a claimant or an authorized adjuster."""
    try:
        clean_name = validate_full_name(payload.full_name)
        clean_email = validate_email(payload.email)
        validate_password_strength(payload.password)
        clean_phone = validate_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")

    if payload.role == "ADJUSTER":
        configured_code = getattr(settings, "ADJUSTER_SIGNUP_CODE", "")
        if not configured_code or payload.adjuster_code != configured_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid adjuster registration code.")

    if db.query(User).filter(User.email == clean_email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    new_user = User(
        full_name=clean_name,
        email=clean_email,
        phone=clean_phone,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        status="active",
    )
    db.add(new_user)
    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        logger.exception("Failed to create user account")
        raise HTTPException(status_code=500, detail="Account creation failed. Please try again.")

    return {
        "id": str(new_user.id),
        "full_name": new_user.full_name,
        "email": new_user.email,
        "phone": new_user.phone,
        "role": new_user.role,
        "status": new_user.status,
    }


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT containing the server-side role."""
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not verify_password(payload.password, str(user.password_hash)):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is disabled. Please contact support.")

    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        },
    }


@router.post("/logout")
def logout():
    """JWT logout is client-side token disposal in this stateless implementation."""
    return {"message": "Logged out successfully."}
