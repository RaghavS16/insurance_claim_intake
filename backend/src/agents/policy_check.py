from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from src.database.models import Policy

def verify_policy_basic(policy_id: Optional[str], db: Session) -> bool:
    """Lightweight Phase 1 check: does the policy exist and is it currently active?"""
    if not policy_id:
        return False
    policy = db.query(Policy).filter(
        Policy.policy_number == str(policy_id).strip().upper()
    ).first()
    if not policy:
        return False
    today = date.today()
    return bool(
        policy.is_active
        and policy.effective_date <= today <= policy.expiry_date
    )
