"""Typed state used by the conversational claim-intake graph."""
from typing import Any, Dict, List, Optional, TypedDict


class ClaimState(TypedDict, total=False):
    ticket_id: str
    claim_text: str
    input_mode: str
    insurance_type_hint: Optional[str]

    extracted_data: Dict[str, Any]
    field_status: Dict[str, str]
    field_metadata: Dict[str, Dict[str, Any]]
    missing_fields: List[str]
    recently_extracted_fields: List[str]
    extraction_changes: List[Dict[str, Any]]
    extraction_confidence: float
    deferral_message: Optional[str]
    awaiting_confirmation: bool
    confirmed: bool
    message: str

    conversation_status: str
    turn_number: int
    conversation_history: List[Dict[str, Any]]
    next_question: str
    next_question_field: Optional[str]
    last_user_utterance: str
    last_intent: str
    unknown_fields: List[str]
    current_field_hint: Optional[str]
    clarification_request: Optional[str]

    _skip_extraction: bool
    _skip_all: bool
    _rejection_active: bool
    _greeting_prefix: Optional[str]
    _gratitude_prefix: Optional[str]
    summary_already_shown: Optional[bool]

    escalate_to_human: bool
    escalation_reason: Optional[str]
    retry_count: int
    consecutive_field_retries: Dict[str, int]

    documents: List[Dict[str, Any]]
    required_documents: List[str]
    missing_documents: List[str]
    uploaded_documents: List[str]
    documents_needed: bool
    policy_data: Optional[Dict[str, Any]]
    policy_valid: Optional[bool]
    policy_details: Optional[Dict[str, Any]]
    validation_status: str
    coverage_eligible: bool
    coverage_reasoning: str
    deductible_amount: float
    payout_amount: float
    fraud_score: float
    fraud_flags: List[str]
    assigned_adjuster: Optional[Dict[str, Any]]
    final_decision: str
    closure_status: str
    response_message: str
    spoken_response: str

    audit_log: List[str]
