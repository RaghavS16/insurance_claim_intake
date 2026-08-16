from typing import List, Dict, Any, Optional, TypedDict


class ClaimState(TypedDict, total=False):
    # ---- Intake (Stage 1-2: FNOL, extraction, confirmation) ----
    claim_text: str
    input_mode: str  # "voice" or "text"
    claim_type_hint: Optional[str]  # optional, if user selects claim type in UI before speaking

    extracted_data: Dict[str, Any]
    missing_fields: List[str]          # fields still needed from user
    awaiting_confirmation: bool        # True once fields are complete and shown back to user
    confirmed: bool                    # True once user has confirmed the extracted data
    message: str                       # intake feedback message

    # R3-8: Proxy confidence score — ratio of required fields that are non-null
    # after extraction. Wired to the `extraction_confidence` DB column.
    # Range: 0.0 (all required fields missing) to 1.0 (all required fields present).
    extraction_confidence: float

    # ---- Documents (Stage 3) ----
    documents: List[Dict[str, Any]]        # [{document_type, filename, file_path}]
    required_documents: List[str]          # required doc types for this claim_type
    missing_documents: List[str]           # required but not yet uploaded
    uploaded_documents: List[str]          # document types already uploaded
    documents_needed: bool                 # False if this claim_type needs no documents at all

    # ---- Policy validation (Stage 4) ----
    policy_data: Optional[Dict[str, Any]]
    policy_valid: Optional[bool]
    policy_details: Optional[Dict[str, Any]]
    validation_status: str  # "valid" | "rejected" | "type_mismatch"

    # ---- Coverage + deductible (Stage 4) ----
    coverage_eligible: bool
    coverage_reasoning: str
    deductible_amount: float
    payout_amount: float

    # ---- Risk assessment (Stage 5) ----
    fraud_score: float
    fraud_flags: List[str]

    # ---- Decision + routing (Stage 6) ----
    assigned_adjuster: Optional[Dict[str, Any]]
    ticket_id: str
    final_decision: str  # "need_more_info" | "need_documents" | "approved" | "denied" | "flagged_for_review" | "manual_review"

    # ---- Closure + feedback (Stage 7) ----
    closure_status: str  # "closed" | "pending_review" | "awaiting_user"
    response_message: str   # shown as text
    spoken_response: str    # read aloud via TTS

    audit_log: List[str]

    # =========================================================
    # Conversational intake additions
    # =========================================================

    # ---- Conversation lifecycle ----
    conversation_status: str          # not_started | in_progress | awaiting_documents | intake_complete
    turn_number: int                  # incremented once per user utterance processed
    conversation_history: List[Dict[str, str]]  # [{turn, speaker, text}] mirror of DB rows

    # ---- Next-question / agent output for this turn ----
    next_question: str                # text the agent should say next (fed to TTS)
    next_question_field: str          # which field next_question targets
    awaiting_document_request: bool   # True when the agent's last utterance was a document request

    # ---- Correction / uncertainty handling ----
    last_user_utterance: str          # raw text of most recent turn
    unknown_fields: List[str]         # fields user explicitly said "I don't know" / "later" for
    _skip_extraction: bool            # internal routing flag