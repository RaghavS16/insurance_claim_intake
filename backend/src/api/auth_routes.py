"""
Authentication API routes.

Handles user signup, login, logout, and profile retrieval.
Extracted from the monolithic main.py for clean architectural separation.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.session import get_db
from src.database.models import User
from src.utils.auth import get_password_hash, verify_password, create_access_token, verify_token
from src.utils.validators import validate_email, validate_password_strength, validate_full_name, validate_phone
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------
class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/signup")
def signup(payload: SignUpRequest, db: Session = Depends(get_db)):
    """Register a new claimant account with validated input."""
    # Validate and sanitize inputs
    try:
        clean_name = validate_full_name(payload.full_name)
        clean_email = validate_email(payload.email)
        validate_password_strength(payload.password)
        clean_phone = validate_phone(payload.phone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match.")

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    hashed_pwd = get_password_hash(payload.password)
    new_user = User(
        full_name=clean_name,
        email=clean_email,
        phone=clean_phone,
        password_hash=hashed_pwd,
        role="CLAIMANT",  # Public signup always creates CLAIMANT role
        status="active",
    )
    db.add(new_user)
    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        logger.exception("Failed to create user account")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account creation failed. Please try again.",
        )

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
    """Authenticate a user and return a JWT access token."""
    try:
        clean_email = validate_email(payload.email)
    except ValueError:
        # Don't reveal whether the email format was the issue
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not verify_password(payload.password, str(user.password_hash)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact support.",
        )

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {
        "access_token": access_token,
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
    """
    Logout endpoint. In a stateless JWT architecture, actual token revocation
    requires a server-side token blacklist (Redis). For now, the client must
    discard the token. This endpoint exists for API completeness.
    """
    return {"message": "Logged out successfully. Please discard your access token."}
