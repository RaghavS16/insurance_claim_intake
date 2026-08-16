"""
ClaimState schema defining the conversation and claim intake state.
"""
from typing import Any, Dict, List, Optional, TypedDict


class ClaimState(TypedDict, total=False):
    """
    Typed state container for LangGraph claim intake and conversation lifecycle.
    """
    # ---- Intake (FNOL, extraction, validation, confirmation) ----
    claim_text: str
    input_mode: str  # "voice" or "text"
    claim_type_hint: Optional[str]

    extracted_data: Dict[str, Any]
    missing_fields: List[str]          # Mandatory fields still required from user
    field_status: Dict[str, str]       # "missing" | "provided" | "unknown" | "deferred"
    recently_extracted_fields: List[str] # Fields extracted in current turn (for acknowledgement)
    deferral_message: Optional[str]    # Friendly acknowledgment when user defers a field
    awaiting_confirmation: bool        # True when state is in "confirming"
    confirmed: bool                    # True once user explicitly confirms data
    message: str                       # User-facing summary / feedback message

    # Confidence score: ratio of required fields successfully extracted (0.0 - 1.0)
    extraction_confidence: float

    # ---- Conversational Turn Management ----
    conversation_status: str           # "not_started" | "collecting" | "confirming" | "intake_complete"
    turn_number: int                   # Monotonically increasing turn count
    conversation_history: List[Dict[str, str]]  # [{turn, speaker, text}]
    next_question: str                 # Natural question or confirmation prompt to be spoken via TTS / displayed
    next_question_field: str           # Target field for next question (empty during confirmation/complete)
    awaiting_document_request: bool    # True when waiting for document upload prompt
    last_user_utterance: str           # Raw text of latest turn
    unknown_fields: List[str]          # Fields explicitly marked unknown/deferred by user
    _skip_extraction: bool             # Internal routing flag for repeat/defer turns
    _rejection_active: bool            # Internal flag when user rejects confirmation

    # ---- Review 2 / Review 3 (Documents, Policy, Risk, Evaluation) ----
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
    ticket_id: str
    final_decision: str
    closure_status: str
    response_message: str
    spoken_response: str

    audit_log: List[str]