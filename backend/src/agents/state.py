from typing import List, Dict, Any, TypedDict


class ClaimState(TypedDict, total=False):
    # ---- Intake (Stage 1-2: FNOL, extraction, confirmation) ----
    claim_text: str
    input_mode: str  # "voice" or "text"
    claim_type_hint: str  # optional, if user selects claim type in UI before speaking

    extracted_data: Dict[str, Any]
    missing_fields: List[str]          # fields still needed from user
    awaiting_confirmation: bool        # True once fields are complete and shown back to user
    confirmed: bool                    # True once user has confirmed the extracted data

    # ---- Documents (Stage 3) ----
    documents: List[Dict[str, Any]]        # [{document_type, filename, file_path}]
    required_documents: List[str]          # required doc types for this claim_type
    missing_documents: List[str]           # required but not yet uploaded
    documents_needed: bool                 # False if this claim_type needs no documents at all

    # ---- Policy validation (Stage 4) ----
    policy_data: Dict[str, Any]
    validation_status: str  # "valid" | "rejected"

    # ---- Coverage + deductible (Stage 4) ----
    coverage_eligible: bool
    coverage_reasoning: str
    deductible_amount: float
    payout_amount: float

    # ---- Risk assessment (Stage 5) ----
    fraud_score: float
    fraud_flags: List[str]

    # ---- Decision + routing (Stage 6) ----
    assigned_adjuster: Dict[str, Any]
    ticket_id: str
    final_decision: str  # "need_more_info" | "need_documents" | "approved" | "denied" | "flagged_for_review" | "manual_review"

    # ---- Closure + feedback (Stage 7) ----
    closure_status: str  # "closed" | "pending_review" | "awaiting_user"
    response_message: str   # shown as text
    spoken_response: str    # read aloud via TTS (Sept) -- same content, kept separate so
                             # voice phrasing can diverge from display text later without
                             # touching decision logic

    audit_log: List[str]