from typing import List, Dict, Any, TypedDict

class ClaimState(TypedDict, total=False):
    claim_text: str
    input_mode: str  # "voice" or "text"
    extracted_data: Dict[str, Any]
    policy_data: Dict[str, Any]
    coverage_eligible: bool
    fraud_score: float
    fraud_flags: List[str]
    assigned_adjuster: Dict[str, Any]
    ticket_id: str
    audit_log: List[str]
    validation_status: str  # "approved", "rejected", "review"
    final_decision: str
    response_message: str