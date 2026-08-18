"""
ClaimState schema defining the conversation and claim intake state for Phase 1.
"""
from typing import Any, Dict, List, Optional, TypedDict


class ClaimState(TypedDict, total=False):
    """
    Typed state container for LangGraph claim intake and conversation lifecycle.
    """
    # ---- Intake (FNOL, extraction, validation, confirmation) ----
    ticket_id: str
    claim_text: str
    input_mode: str  # "voice" or "text"
    insurance_type_hint: Optional[str]

    extracted_data: Dict[str, Any]
    missing_fields: List[str]            # Mandatory fields still required from claimant
    field_status: Dict[str, str]         # "missing" | "provided" | "unknown" | "deferred"
    recently_extracted_fields: List[str] # Fields extracted in current turn (for acknowledgement)
    deferral_message: Optional[str]      # Friendly acknowledgment when user defers a field
    awaiting_confirmation: bool          # True when all required fields collected, waiting for user confirmation
    confirmed: bool                      # True once user explicitly confirms data
    message: str                         # User-facing summary / feedback message

    # Confidence score: ratio of required fields successfully extracted (0.0 - 1.0)
    extraction_confidence: float

    # ---- Conversational Turn Management ----
    conversation_status: str             # "not_started" | "collecting" | "confirming" | "intake_complete" | "submitted" | "completed"
    turn_number: int                     # Monotonically increasing turn count
    conversation_history: List[Dict[str, Any]]  # [{turn, speaker, text}]
    next_question: str                   # Natural question or confirmation prompt to be spoken via TTS / displayed
    next_question_field: str             # Target field for next question
    last_user_utterance: str             # Raw text of latest turn
    unknown_fields: List[str]            # Fields explicitly marked unknown/deferred by user
    _skip_extraction: bool               # Internal routing flag for repeat/defer turns
    _rejection_active: bool              # Internal flag when user rejects confirmation
    _skip_all: bool                      # Internal short-circuiting flag for post-intake turns
    _greeting_prefix: Optional[str]
    _gratitude_prefix: Optional[str]
    summary_already_shown: Optional[bool] # Track if confirmation summary has been displayed


    # ---- Phase 2 Extensibility Interfaces ----
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