"""
Admin Management API Routes.

Provides endpoints for administrators to:
1. Import and synchronize policies via CSV without overriding claimant ownership.
2. Provision adjuster accounts with temporary credentials.
3. List adjusters and overview all policies.
"""
import csv
import io
import secrets
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.database.models import Adjuster, Policy, User
from src.utils.auth import get_password_hash
from src.utils.validators import validate_email, validate_full_name
from src.utils.logger import app_logger

logger = app_logger
router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

CANONICAL_POLICY_TYPES = {"health", "senior_health", "home", "travel", "motor", "cyber"}


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------
class AddAdjusterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name of the adjuster")
    email: str = Field(..., min_length=3, max_length=254, description="Adjuster email address")
    specialization: str = Field(
        ...,
        description="Canonical specialization: health, senior_health, home, travel, motor, or cyber",
    )


class UpdateAdjusterRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100, description="Full name of the adjuster")
    email: Optional[str] = Field(None, min_length=3, max_length=254, description="Adjuster email address")
    specialization: Optional[str] = Field(
        None,
        description="Canonical specialization: health, senior_health, home, travel, motor, or cyber",
    )
    is_active: Optional[bool] = Field(None, description="Active status of adjuster")


class CreatePolicyRequest(BaseModel):
    policy_number: str = Field(..., min_length=2, max_length=64, description="Unique policy identifier")
    policy_type: str = Field(..., description="Canonical policy type")
    coverage_amount: float = Field(..., gt=0, description="Maximum coverage amount")
    deductible: float = Field(0.0, ge=0, description="Deductible amount")
    effective_date: str = Field(..., description="Start date YYYY-MM-DD")
    expiry_date: str = Field(..., description="End date YYYY-MM-DD")
    policyholder_name: Optional[str] = Field(None, max_length=255, description="Full name of policyholder")
    policyholder_dob: Optional[str] = Field(None, description="DOB YYYY-MM-DD")
    policyholder_phone_last4: Optional[str] = Field(None, max_length=4, description="Last 4 digits of phone")
    is_active: bool = Field(True, description="Policy active status")


class UpdatePolicyRequest(BaseModel):
    policy_type: Optional[str] = Field(None, description="Canonical policy type")
    coverage_amount: Optional[float] = Field(None, gt=0, description="Maximum coverage amount")
    deductible: Optional[float] = Field(None, ge=0, description="Deductible amount")
    effective_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    expiry_date: Optional[str] = Field(None, description="End date YYYY-MM-DD")
    policyholder_name: Optional[str] = Field(None, max_length=255, description="Full name of policyholder")
    policyholder_dob: Optional[str] = Field(None, description="DOB YYYY-MM-DD")
    policyholder_phone_last4: Optional[str] = Field(None, max_length=4, description="Last 4 digits of phone")
    is_active: Optional[bool] = Field(None, description="Policy active status")


# ---------------------------------------------------------------------------
# Helper: resolve admin user
# ---------------------------------------------------------------------------
def _resolve_admin(request: Request, db: Session) -> User:
    """Ensure caller is an authenticated user with ADMIN role."""
    from src.api.main import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials

    auth_header = request.headers.get("authorization", "")
    credentials = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    current_user = get_current_user(request=request, credentials=credentials, db=db)
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Role '{current_user.role}' does not have administrative privileges.",
        )
    return current_user


def _find_policy(db: Session, identifier: str) -> Optional[Policy]:
    """Find policy safely by UUID id or policy_number without throwing Postgres UUID casting error."""
    clean_id = identifier.strip()
    try:
        val_uuid = uuid.UUID(clean_id)
        pol = db.query(Policy).filter(Policy.id == str(val_uuid)).first()
        if pol:
            return pol
    except (ValueError, AttributeError):
        pass

    return db.query(Policy).filter(Policy.policy_number == clean_id.upper()).first()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/policies/import")
@router.post("/policies/import-csv")
async def import_policies_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import policies from a CSV file.
    Upserts policy details. For existing policies, NEVER overwrites customer_id or linked_at.
    """
    _resolve_admin(request, db)

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv files are supported.",
        )

    try:
        contents = await file.read()
        text_stream = io.StringIO(contents.decode("utf-8-sig"))
        reader = csv.DictReader(text_stream)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read CSV file: {str(exc)}",
        )

    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty or headers are missing.",
        )

    # Normalize header mapping
    header_map = {name.strip().lower(): name for name in reader.fieldnames if name}
    required_fields = ["policy_number", "policy_type", "coverage_amount", "deductible", "effective_date", "expiry_date"]

    for req in required_fields:
        if req not in header_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required CSV column: '{req}'. Found: {list(header_map.keys())}",
            )

    created_count = 0
    updated_count = 0
    errors: List[Dict[str, Any]] = []

    for row_idx, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k}
        policy_num = row.get("policy_number", "").upper()

        if not policy_num:
            errors.append({"row": row_idx, "error": "Missing policy_number"})
            continue

        policy_type = row.get("policy_type", "").lower()
        if policy_type not in CANONICAL_POLICY_TYPES:
            errors.append({
                "row": row_idx,
                "policy_number": policy_num,
                "error": f"Invalid policy_type '{policy_type}'. Must be one of {sorted(CANONICAL_POLICY_TYPES)}",
            })
            continue

        try:
            cov_amount = float(row.get("coverage_amount", 0))
            deductible = float(row.get("deductible", 0))
            eff_date = datetime.strptime(row.get("effective_date", ""), "%Y-%m-%d").date()
            exp_date = datetime.strptime(row.get("expiry_date", ""), "%Y-%m-%d").date()
        except ValueError as val_err:
            errors.append({"row": row_idx, "policy_number": policy_num, "error": f"Value parsing error: {str(val_err)}"})
            continue

        holder_name = row.get("policyholder_name") or None
        holder_dob_str = row.get("policyholder_dob") or None
        holder_dob = None
        if holder_dob_str:
            try:
                holder_dob = datetime.strptime(holder_dob_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append({"row": row_idx, "policy_number": policy_num, "error": "Invalid policyholder_dob format (YYYY-MM-DD required)"})
                continue

        phone_last4 = row.get("policyholder_phone_last4") or None
        if phone_last4 and len(phone_last4) > 4:
            phone_last4 = phone_last4[-4:]

        is_active_val = row.get("is_active", "true").lower() in ("true", "1", "yes", "t")

        existing_policy = db.query(Policy).filter(Policy.policy_number == policy_num).first()

        if existing_policy:
            # Update policy fields WITHOUT overwriting customer_id or linked_at
            existing_policy.policy_type = policy_type  # type: ignore[assignment]
            existing_policy.coverage_amount = cov_amount  # type: ignore[assignment]
            existing_policy.deductible = deductible  # type: ignore[assignment]
            existing_policy.effective_date = eff_date  # type: ignore[assignment]
            existing_policy.expiry_date = exp_date  # type: ignore[assignment]
            existing_policy.is_active = is_active_val  # type: ignore[assignment]
            if holder_name is not None:
                existing_policy.policyholder_name = holder_name  # type: ignore[assignment]
            if holder_dob is not None:
                existing_policy.policyholder_dob = holder_dob  # type: ignore[assignment]
            if phone_last4 is not None:
                existing_policy.policyholder_phone_last4 = phone_last4  # type: ignore[assignment]
            updated_count += 1
        else:
            # Create new unlinked policy
            new_policy = Policy(
                id=str(uuid.uuid4()),
                policy_number=policy_num,
                customer_id=None,
                policy_type=policy_type,
                coverage_amount=cov_amount,
                deductible=deductible,
                effective_date=eff_date,
                expiry_date=exp_date,
                is_active=is_active_val,
                policyholder_name=holder_name,
                policyholder_dob=holder_dob,
                policyholder_phone_last4=phone_last4,
                link_attempts=0,
            )
            db.add(new_policy)
            created_count += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to commit CSV imported policies")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save imported policies to database.",
        )

    return {
        "imported": created_count,
        "updated": updated_count,
        "total_processed": created_count + updated_count,
        "errors": errors,
    }


@router.post("/adjusters")
def add_adjuster(
    payload: AddAdjusterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a new Adjuster user account and associated adjuster profile.
    Generates a secure temporary password for initial access.
    """
    _resolve_admin(request, db)

    try:
        clean_name = validate_full_name(payload.name)
        clean_email = validate_email(payload.email)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))

    spec = payload.specialization.strip().lower()
    if spec not in CANONICAL_POLICY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Specialization must be one of: {sorted(CANONICAL_POLICY_TYPES)}",
        )

    existing_user = db.query(User).filter(User.email == clean_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    # Generate a strong temporary password
    temp_password = f"Adj!{secrets.token_urlsafe(8)}9#"
    user_id = str(uuid.uuid4())

    new_user = User(
        id=user_id,
        full_name=clean_name,
        email=clean_email,
        password_hash=get_password_hash(temp_password),
        role="ADJUSTER",
        status="active",
    )
    new_adjuster = Adjuster(
        id=user_id,
        name=clean_name,
        email=clean_email,
        specialization=spec,
        claims_assigned=0,
        is_active=True,
    )

    db.add(new_user)
    db.add(new_adjuster)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create adjuster account")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create adjuster account.",
        )

    return {
        "id": user_id,
        "name": clean_name,
        "email": clean_email,
        "specialization": spec,
        "temporary_password": temp_password,
        "message": "Adjuster account created successfully. Provide the temporary password securely to the adjuster.",
    }


@router.get("/adjusters")
def list_adjusters(
    request: Request,
    db: Session = Depends(get_db),
):
    """List all registered adjusters and their assigned claims count."""
    _resolve_admin(request, db)

    adjusters = db.query(Adjuster).order_by(Adjuster.name.asc()).all()
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "email": a.email,
            "specialization": a.specialization,
            "claims_assigned": a.claims_assigned,
            "is_active": a.is_active,
        }
        for a in adjusters
    ]


@router.get("/adjusters/{adjuster_id}")
def get_adjuster(
    adjuster_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Retrieve details of a single adjuster."""
    _resolve_admin(request, db)

    adjuster = db.query(Adjuster).filter(Adjuster.id == adjuster_id).first()
    if not adjuster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adjuster not found.",
        )

    return {
        "id": str(adjuster.id),
        "name": adjuster.name,
        "email": adjuster.email,
        "specialization": adjuster.specialization,
        "claims_assigned": adjuster.claims_assigned,
        "is_active": adjuster.is_active,
    }


@router.put("/adjusters/{adjuster_id}")
def update_adjuster(
    adjuster_id: str,
    payload: UpdateAdjusterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Update an adjuster's information (name, email, specialization, active status).
    Synchronizes the corresponding User account.
    """
    _resolve_admin(request, db)

    adjuster = db.query(Adjuster).filter(Adjuster.id == adjuster_id).first()
    if not adjuster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adjuster not found.",
        )

    user = db.query(User).filter(User.id == adjuster_id).first()

    if payload.name is not None:
        try:
            clean_name = validate_full_name(payload.name)
            adjuster.name = clean_name  # type: ignore[assignment]
            if user:
                user.full_name = clean_name  # type: ignore[assignment]
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    if payload.email is not None:
        try:
            clean_email = validate_email(payload.email)
            if clean_email != adjuster.email:
                existing = db.query(User).filter(User.email == clean_email, User.id != adjuster_id).first()
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Another user with this email already exists.",
                    )
                adjuster.email = clean_email  # type: ignore[assignment]
                if user:
                    user.email = clean_email  # type: ignore[assignment]
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    if payload.specialization is not None:
        spec = payload.specialization.strip().lower()
        if spec not in CANONICAL_POLICY_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Specialization must be one of: {sorted(CANONICAL_POLICY_TYPES)}",
            )
        adjuster.specialization = spec  # type: ignore[assignment]

    if payload.is_active is not None:
        adjuster.is_active = payload.is_active  # type: ignore[assignment]
        if user:
            user.status = "active" if payload.is_active else "inactive"  # type: ignore[assignment]

    try:
        db.commit()
        db.refresh(adjuster)
    except Exception:
        db.rollback()
        logger.exception(f"Failed to update adjuster {adjuster_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update adjuster.",
        )

    return {
        "id": str(adjuster.id),
        "name": adjuster.name,
        "email": adjuster.email,
        "specialization": adjuster.specialization,
        "claims_assigned": adjuster.claims_assigned,
        "is_active": adjuster.is_active,
        "message": "Adjuster updated successfully.",
    }


@router.post("/adjusters/{adjuster_id}/reset-password")
def reset_adjuster_password(
    adjuster_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reset an adjuster's password and generate a new temporary password.
    """
    _resolve_admin(request, db)

    adjuster = db.query(Adjuster).filter(Adjuster.id == adjuster_id).first()
    if not adjuster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adjuster not found.",
        )

    user = db.query(User).filter(User.id == adjuster_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Linked user account not found.",
        )

    temp_password = f"Adj!{secrets.token_urlsafe(8)}9#"
    user.password_hash = get_password_hash(temp_password)  # type: ignore[assignment]

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Failed to reset password for adjuster {adjuster_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset adjuster password.",
        )

    return {
        "id": str(adjuster.id),
        "email": adjuster.email,
        "temporary_password": temp_password,
        "message": "Password reset successfully. Provide the new temporary password to the adjuster.",
    }


@router.delete("/adjusters/{adjuster_id}")
def delete_adjuster(
    adjuster_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Delete an adjuster and their associated user record.
    Prevents deletion if active claims are assigned (suggests deactivation instead).
    """
    _resolve_admin(request, db)

    adjuster = db.query(Adjuster).filter(Adjuster.id == adjuster_id).first()
    if not adjuster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adjuster not found.",
        )

    if (adjuster.claims_assigned or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete adjuster with {adjuster.claims_assigned} active assigned claims. Deactivate the adjuster account instead.",
        )

    user = db.query(User).filter(User.id == adjuster_id).first()

    try:
        db.delete(adjuster)
        if user:
            db.delete(user)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Failed to delete adjuster {adjuster_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete adjuster.",
        )

    return {
        "id": adjuster_id,
        "message": "Adjuster deleted successfully.",
    }


@router.get("/policies")
def list_all_policies(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """Overview list of all policies in the system and their linking status."""
    _resolve_admin(request, db)

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 50

    query = db.query(Policy).order_by(Policy.created_at.desc())
    total = query.count()
    offset = (page - 1) * page_size
    policies = query.offset(offset).limit(page_size).all()

    items = []
    for p in policies:
        cov_val = float(getattr(p, "coverage_amount", 0) or 0)
        ded_val = float(getattr(p, "deductible", 0) or 0)
        linked_at_val = getattr(p, "linked_at", None)
        items.append({
            "id": str(p.id),
            "policy_number": p.policy_number,
            "policy_type": p.policy_type,
            "coverage_amount": cov_val,
            "deductible": ded_val,
            "effective_date": str(p.effective_date),
            "expiry_date": str(p.expiry_date),
            "is_active": p.is_active,
            "policyholder_name": p.policyholder_name,
            "policyholder_phone_last4": p.policyholder_phone_last4,
            "is_linked": p.customer_id is not None,
            "customer_id": str(p.customer_id) if p.customer_id else None,
            "linked_at": linked_at_val.isoformat() if linked_at_val else None,
            "link_attempts": p.link_attempts,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/policies")
def create_policy(
    payload: CreatePolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a single new policy record with validation."""
    _resolve_admin(request, db)

    policy_num = payload.policy_number.strip().upper()
    existing = db.query(Policy).filter(Policy.policy_number == policy_num).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Policy '{policy_num}' already exists.",
        )

    policy_type = payload.policy_type.strip().lower()
    if policy_type not in CANONICAL_POLICY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid policy_type '{policy_type}'. Must be one of {sorted(CANONICAL_POLICY_TYPES)}",
        )

    try:
        eff_date = datetime.strptime(payload.effective_date.strip(), "%Y-%m-%d").date()
        exp_date = datetime.strptime(payload.expiry_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Effective date and expiry date must be in YYYY-MM-DD format.",
        )

    holder_dob = None
    if payload.policyholder_dob:
        try:
            holder_dob = datetime.strptime(payload.policyholder_dob.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Policyholder date of birth must be in YYYY-MM-DD format.",
            )

    phone_last4 = payload.policyholder_phone_last4
    if phone_last4 and len(phone_last4) > 4:
        phone_last4 = phone_last4[-4:]

    new_policy = Policy(
        id=str(uuid.uuid4()),
        policy_number=policy_num,
        customer_id=None,
        policy_type=policy_type,
        coverage_amount=payload.coverage_amount,
        deductible=payload.deductible,
        effective_date=eff_date,
        expiry_date=exp_date,
        is_active=payload.is_active,
        policyholder_name=payload.policyholder_name.strip() if payload.policyholder_name else None,
        policyholder_dob=holder_dob,
        policyholder_phone_last4=phone_last4,
        link_attempts=0,
    )

    db.add(new_policy)
    try:
        db.commit()
        db.refresh(new_policy)
    except Exception:
        db.rollback()
        logger.exception("Failed to create policy")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create policy in database.",
        )

    return {
        "id": str(new_policy.id),
        "policy_number": new_policy.policy_number,
        "policy_type": new_policy.policy_type,
        "coverage_amount": float(new_policy.coverage_amount),
        "deductible": float(new_policy.deductible),
        "effective_date": str(new_policy.effective_date),
        "expiry_date": str(new_policy.expiry_date),
        "is_active": new_policy.is_active,
        "policyholder_name": new_policy.policyholder_name,
        "policyholder_phone_last4": new_policy.policyholder_phone_last4,
        "message": "Policy created successfully.",
    }


@router.put("/policies/{policy_id_or_number}")
def update_policy(
    policy_id_or_number: str,
    payload: UpdatePolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update existing policy details safely."""
    _resolve_admin(request, db)

    policy = _find_policy(db, policy_id_or_number)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id_or_number}' not found.",
        )

    if payload.policy_type is not None:
        ptype = payload.policy_type.strip().lower()
        if ptype not in CANONICAL_POLICY_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid policy_type '{ptype}'. Must be one of {sorted(CANONICAL_POLICY_TYPES)}",
            )
        policy.policy_type = ptype  # type: ignore[assignment]

    if payload.coverage_amount is not None:
        policy.coverage_amount = payload.coverage_amount  # type: ignore[assignment]

    if payload.deductible is not None:
        policy.deductible = payload.deductible  # type: ignore[assignment]

    if payload.effective_date is not None:
        try:
            policy.effective_date = datetime.strptime(payload.effective_date.strip(), "%Y-%m-%d").date()  # type: ignore[assignment]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Effective date must be in YYYY-MM-DD format.",
            )

    if payload.expiry_date is not None:
        try:
            policy.expiry_date = datetime.strptime(payload.expiry_date.strip(), "%Y-%m-%d").date()  # type: ignore[assignment]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expiry date must be in YYYY-MM-DD format.",
            )

    if payload.policyholder_name is not None:
        policy.policyholder_name = payload.policyholder_name.strip() or None  # type: ignore[assignment]

    if payload.policyholder_dob is not None:
        if payload.policyholder_dob.strip():
            try:
                policy.policyholder_dob = datetime.strptime(payload.policyholder_dob.strip(), "%Y-%m-%d").date()  # type: ignore[assignment]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Policyholder date of birth must be in YYYY-MM-DD format.",
                )
        else:
            policy.policyholder_dob = None  # type: ignore[assignment]

    if payload.policyholder_phone_last4 is not None:
        p4 = payload.policyholder_phone_last4.strip()
        policy.policyholder_phone_last4 = p4[-4:] if p4 else None  # type: ignore[assignment]

    if payload.is_active is not None:
        policy.is_active = payload.is_active  # type: ignore[assignment]

    try:
        db.commit()
        db.refresh(policy)
    except Exception:
        db.rollback()
        logger.exception(f"Failed to update policy {policy_id_or_number}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update policy in database.",
        )

    return {
        "id": str(policy.id),
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "coverage_amount": float(policy.coverage_amount),
        "deductible": float(policy.deductible),
        "effective_date": str(policy.effective_date),
        "expiry_date": str(policy.expiry_date),
        "is_active": policy.is_active,
        "policyholder_name": policy.policyholder_name,
        "policyholder_phone_last4": policy.policyholder_phone_last4,
        "message": "Policy updated successfully.",
    }


@router.delete("/policies/{policy_id_or_number}")
def delete_policy(
    policy_id_or_number: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a policy record safely by ID or policy number."""
    _resolve_admin(request, db)

    policy = _find_policy(db, policy_id_or_number)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id_or_number}' not found.",
        )

    pol_num = policy.policy_number
    try:
        db.delete(policy)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(f"Failed to delete policy {policy_id_or_number}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete policy.",
        )

    return {
        "policy_number": pol_num,
        "message": f"Policy '{pol_num}' deleted successfully.",
    }
