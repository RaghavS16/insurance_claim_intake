"""
Review 2 / Review 3: Insurance Claim Evaluation Pipeline.

Isolated from Review 1 (Intake & Voice Conversation).
Contains:
- Policy validation against database
- Coverage eligibility and deductible calculations
- Document requirement checking
- Fraud risk scoring
- Adjuster routing and load balancing
- Final payout and decision formatting
"""
import json
import logging
import os
import re
from datetime import date, datetime, timezone
from functools import partial
from typing import Any, Dict, List, Optional, Set

from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from src.database.models import Policy, Adjuster
from src.agents.state import ClaimState

logger = logging.getLogger(__name__)

_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
llm = ChatOllama(base_url=_OLLAMA_URL, model="llama3.1:8b", temperature=0, timeout=10)

DOCUMENT_REQUIREMENTS: Dict[str, List[str]] = {
    "motor": ["damage_photo", "repair_estimate"],
    "home": ["damage_photo"],
    "health": ["medical_bill"],
    "senior_health": ["medical_bill"],
    "travel": ["boarding_pass"],
    "cyber": ["incident_report"],
    "auto": ["damage_photo", "repair_estimate"],
}

DOCUMENT_LABELS = {
    "damage_photo": "photos of the damage",
    "repair_estimate": "a repair cost estimate",
    "fir": "a police FIR / report",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


# ---------------------------------------------------------------------------
# Node 1: Policy Validator (Review 2)
# ---------------------------------------------------------------------------
def policy_validator(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    data: Dict[str, Any] = state.get("extracted_data") or {}
    policy_id = data.get("policy_id")
    if not policy_id:
        state["policy_valid"] = False
        state["policy_details"] = None
        state["validation_status"] = "rejected"
        _audit(state, "Policy validation failed: no policy_id provided")
        return state

    if db is None:
        state["policy_valid"] = True
        state["validation_status"] = "valid"
        return state

    policy = db.query(Policy).filter(Policy.policy_number == str(policy_id).strip().upper()).first()
    if not policy:
        state["policy_valid"] = False
        state["policy_details"] = None
        state["validation_status"] = "rejected"
        _audit(state, f"Policy validation failed: policy '{policy_id}' not found in database")
        return state

    today = date.today()
    eff_date = getattr(policy, "effective_date", None)
    exp_date = getattr(policy, "expiry_date", None)
    is_active: bool = bool(
        policy.is_active
        and eff_date is not None
        and exp_date is not None
        and eff_date <= today <= exp_date
    )

    coverage_val = getattr(policy, "coverage_amount", None)
    deductible_val = getattr(policy, "deductible", None)
    coverage_limit = float(coverage_val) if coverage_val is not None else 0.0
    deductible_amt = float(deductible_val) if deductible_val is not None else 0.0

    state["policy_valid"] = is_active
    state["validation_status"] = "valid" if is_active else "rejected"
    state["policy_data"] = {"id": str(policy.id)}
    state["policy_details"] = {
        "policy_id": str(policy.policy_number),
        "policy_type": str(policy.policy_type),
        "start_date": str(eff_date),
        "end_date": str(exp_date),
        "coverage_limit": coverage_limit,
        "deductible": deductible_amt,
    }
    _audit(
        state,
        f"Policy '{policy_id}' validated: active={is_active} "
        f"(valid window: {eff_date} to {exp_date})"
    )
    return state


# ---------------------------------------------------------------------------
# Node 2: Coverage Checker (Review 2)
# ---------------------------------------------------------------------------
def coverage_checker(state: ClaimState) -> ClaimState:
    if not state.get("policy_valid"):
        state["coverage_eligible"] = False
        state["deductible_amount"] = 0.0
        state["payout_amount"] = 0.0
        _audit(state, "Coverage check failed: policy is invalid or expired")
        return state

    extracted: Dict[str, Any] = state.get("extracted_data") or {}
    policy: Dict[str, Any] = state.get("policy_details") or {}
    claim_type = str(extracted.get("claim_type") or "").strip().lower()
    policy_type = str(policy.get("policy_type") or "").strip().lower()

    norm_claim = "motor" if claim_type in ("auto", "motor", "car") else claim_type
    norm_policy = "motor" if policy_type in ("auto", "motor", "car") else policy_type

    if norm_policy and norm_claim and norm_claim != norm_policy:
        state["coverage_eligible"] = False
        state["validation_status"] = "type_mismatch"
        state["deductible_amount"] = 0.0
        state["payout_amount"] = 0.0
        _audit(state, f"Coverage check failed: claim_type '{claim_type}' does not match policy_type '{policy_type}'")
        return state

    incident_date_str = extracted.get("incident_date")
    if incident_date_str and policy.get("start_date") and policy.get("end_date"):
        try:
            inc_date = datetime.strptime(str(incident_date_str), "%Y-%m-%d").date()
            start = datetime.strptime(str(policy["start_date"]), "%Y-%m-%d").date()
            end = datetime.strptime(str(policy["end_date"]), "%Y-%m-%d").date()
            if not (start <= inc_date <= end):
                state["coverage_eligible"] = False
                state["deductible_amount"] = 0.0
                state["payout_amount"] = 0.0
                _audit(state, f"Coverage check failed: incident_date {inc_date} outside policy window ({start} to {end})")
                return state
        except ValueError:
            pass

    claimed = float(extracted.get("claimed_amount") or 0.0)
    limit = float(policy.get("coverage_limit", 0.0))
    deductible = float(policy.get("deductible", 0.0))

    is_eligible = (limit == 0 or claimed <= limit)
    state["coverage_eligible"] = is_eligible
    state["deductible_amount"] = deductible
    state["payout_amount"] = max(0.0, min(claimed, limit) - deductible) if (is_eligible and limit > 0) else claimed

    _audit(
        state,
        f"Coverage eligible: {is_eligible} (claimed={claimed}, limit={limit}, "
        f"deductible={deductible}, payout={state['payout_amount']})"
    )
    return state


# ---------------------------------------------------------------------------
# Node 3: Document Requirement Checker (Review 2)
# ---------------------------------------------------------------------------
def document_requirement_checker(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    extracted: Dict[str, Any] = state.get("extracted_data") or {}
    claim_type = str(extracted.get("claim_type") or "").strip().lower()
    required_doc_types = DOCUMENT_REQUIREMENTS.get(claim_type, [])

    if not required_doc_types:
        state["missing_documents"] = []
        state["documents_needed"] = False
        _audit(state, f"Document check: claim_type '{claim_type}' requires no documents")
        return state

    uploaded_list: List[str] = state.get("uploaded_documents") or []
    if not uploaded_list and state.get("documents"):
        uploaded_list = [d.get("document_type") for d in state["documents"] if d.get("document_type")]

    uploaded_types: Set[str] = set(uploaded_list)
    missing = [doc for doc in required_doc_types if doc not in uploaded_types]

    state["documents_needed"] = True
    state["required_documents"] = required_doc_types
    state["missing_documents"] = missing
    _audit(state, f"Document check: required={required_doc_types}, uploaded={list(uploaded_types)}, missing={missing}")
    return state


def document_request_generator(state: ClaimState) -> ClaimState:
    """Prompt user for missing documents during conversational flow (optional later phase)."""
    missing_docs = state.get("missing_documents", [])
    if missing_docs:
        labels = [DOCUMENT_LABELS.get(d, d.replace("_", " ")) for d in missing_docs]
        prompt = (
            f"Thank you. I have all the claim details. To complete your claim, please upload: "
            f"{', '.join(labels)}. You can use the upload button on your screen."
        )
        state["next_question"] = prompt
        state["next_question_field"] = "documents"
        state["awaiting_document_request"] = True
        state["conversation_status"] = "awaiting_documents"
        _audit(state, f"Prompting user for missing documents: {missing_docs}")
    else:
        state["awaiting_document_request"] = False
        state["conversation_status"] = "intake_complete"

    return state


# ---------------------------------------------------------------------------
# Node 4: Fraud Detector (Review 3)
# ---------------------------------------------------------------------------
FRAUD_PROMPT = """Analyze this insurance claim for fraud risk.
Evaluate:
1. Is the claimed amount unusually high for this incident type?
2. Does the damage description match the incident date/type?
3. Are there inconsistencies in the narrative?

Return ONLY valid JSON, no markdown, no explanation:
{{
  "fraud_score": <float 0.0 to 1.0>,
  "flags": ["list of string flags, empty if none"]
}}

Claim Details:
- Policy ID: {policy_id}
- Policy Type: {policy_type}
- Coverage Limit: {coverage_limit}
- Claimed Amount: {claimed_amount}
- Incident Date: {incident_date}
- Damage Description: {damage_description}
"""

def fraud_detector(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    extracted: Dict[str, Any] = state.get("extracted_data") or {}
    policy: Dict[str, Any] = state.get("policy_details") or {}

    prompt = FRAUD_PROMPT.format(
        policy_id=extracted.get("policy_id", "N/A"),
        policy_type=policy.get("policy_type", "N/A"),
        coverage_limit=policy.get("coverage_limit", "N/A"),
        claimed_amount=extracted.get("claimed_amount", "N/A"),
        incident_date=extracted.get("incident_date", "N/A"),
        damage_description=extracted.get("damage_description", "N/A"),
    )

    score = 0.0
    flags: List[str] = []

    try:
        response = llm.invoke(prompt)
        content = response.content
        raw = content if isinstance(content, str) else str(content)
        raw = raw.strip()
        raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        raw_score = float(result.get("fraud_score", 0.0))
        score = raw_score / 100.0 if raw_score > 1.0 else raw_score
        flags = list(result.get("flags", []))
    except Exception as exc:
        logger.warning("fraud_detector LLM unavailable (%s), applying heuristic rules", exc)
        score = 0.0
        flags = []

    claimed = float(extracted.get("claimed_amount") or 0.0)
    limit = float(policy.get("coverage_limit") or 0.0)
    if limit > 0 and claimed > 0.8 * limit:
        score = max(score, 0.5)
        if "HIGH_CLAIM_AMOUNT_NEAR_LIMIT" not in flags:
            flags.append("HIGH_CLAIM_AMOUNT_NEAR_LIMIT")

    incident_date_str = extracted.get("incident_date")
    if incident_date_str:
        try:
            inc_date = datetime.strptime(str(incident_date_str), "%Y-%m-%d").date()
            if inc_date > date.today():
                score = max(score, 0.85)
                if "future_incident_date" not in flags:
                    flags.append("future_incident_date")
        except ValueError:
            pass

    state["fraud_score"] = score
    state["fraud_flags"] = flags
    _audit(state, f"Fraud check complete: score={score:.2f}, flags={flags}")
    return state


# ---------------------------------------------------------------------------
# Node 5: Route Decision (Review 3)
# ---------------------------------------------------------------------------
def route_decision(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    if db is None:
        state["assigned_adjuster"] = {}
        return state

    try:
        adjusters = db.query(Adjuster).filter(Adjuster.is_active == True).all()
        if not adjusters:
            state["assigned_adjuster"] = {}
            _audit(state, "Adjuster routing: No active adjuster found in database")
            return state

        least_loaded = min(adjusters, key=lambda a: int(getattr(a, "claims_assigned", 0) or 0))
        current_assigned = int(getattr(least_loaded, "claims_assigned", 0) or 0)
        setattr(least_loaded, "claims_assigned", current_assigned + 1)
        db.commit()

        state["assigned_adjuster"] = {
            "id": str(least_loaded.id),
            "name": str(least_loaded.name),
            "email": str(least_loaded.email),
            "specialization": str(least_loaded.specialization),
            "claims_assigned": current_assigned + 1,
        }
        _audit(state, f"Assigned to adjuster '{least_loaded.name}' (assigned total={current_assigned + 1})")
    except Exception as exc:
        logger.exception("route_decision encountered error: %s", exc)
        state["assigned_adjuster"] = {}
        _audit(state, f"Adjuster routing error: {exc}")

    return state


# ---------------------------------------------------------------------------
# Node 6: Response Formatter (Review 2/3)
# ---------------------------------------------------------------------------
def response_formatter(state: ClaimState) -> ClaimState:
    ticket_id = state.get("ticket_id", "N/A")

    if not state.get("policy_valid"):
        message = (
            f"Your claim under ticket {ticket_id} has been routed for manual review. "
            "Reason: The policy ID provided could not be verified or is not currently active."
        )
        state["final_decision"] = "manual_review"
        state["closure_status"] = "pending_review"

    elif state.get("validation_status") == "type_mismatch":
        message = (
            f"Your claim under ticket {ticket_id} has been routed for manual review. "
            "Reason: Declared claim type does not match the policy coverage type."
        )
        state["final_decision"] = "manual_review"
        state["closure_status"] = "pending_review"

    elif state.get("missing_documents"):
        missing_labels = [DOCUMENT_LABELS.get(d, d.replace("_", " ")) for d in state.get("missing_documents", [])]
        message = (
            f"Your claim (ticket {ticket_id}) is eligible for coverage, but requires additional documentation: "
            f"{', '.join(missing_labels)}. Please upload these documents to complete your claim."
        )
        state["final_decision"] = "need_documents"
        state["closure_status"] = "awaiting_user"

    elif state.get("coverage_eligible") is False:
        message = (
            f"Your claim under ticket {ticket_id} has been denied. "
            "Reason: The claim details or amount exceed the coverage terms of your policy."
        )
        state["final_decision"] = "denied"
        state["closure_status"] = "closed"

    elif state.get("fraud_score", 0.0) >= 0.6:
        adjuster = state.get("assigned_adjuster") or {}
        message = (
            f"Your claim (ticket {ticket_id}) has been flagged for adjuster review due to validation flags: "
            f"{', '.join(state.get('fraud_flags', []))}. Assigned to {adjuster.get('name', 'an adjuster')}."
        )
        state["final_decision"] = "flagged_for_review"
        state["closure_status"] = "pending_review"

    else:
        adjuster = state.get("assigned_adjuster") or {}
        payout = state.get("payout_amount", 0.0)
        deductible = state.get("deductible_amount", 0.0)
        message = (
            f"Your claim has been approved. Ticket {ticket_id}. "
            f"Approved payout: ₹{payout:,.0f} after a ₹{deductible:,.0f} deductible. "
            f"Assigned to {adjuster.get('name', 'an adjuster')} for processing."
        )
        state["final_decision"] = "approved"
        state["closure_status"] = "closed"

    state["response_message"] = message
    state["spoken_response"] = message
    _audit(state, f"Final decision: {state['final_decision']} ({state['closure_status']})")
    return state


# ---------------------------------------------------------------------------
# Evaluation Graph Builder (Review 2/3)
# ---------------------------------------------------------------------------
def build_evaluation_graph(db: Session):
    """
    Construct the evaluation graph with request-scoped DB session injection.
    Topology:
      policy_validator
        |-- valid --> coverage_checker
        |                 |-- covered --> document_requirement_checker
        |                 |                   |-- ready --> fraud_detector --> route_decision --> response_formatter
        |                 |                   |-- missing --> response_formatter (need_documents)
        |                 |-- not_covered / mismatch --> response_formatter
        |-- rejected --> response_formatter
    """
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("policy_validator",             partial(policy_validator, db=db))
    graph.add_node("coverage_checker",              coverage_checker)
    graph.add_node("document_requirement_checker",  partial(document_requirement_checker, db=db))
    graph.add_node("fraud_detector",               partial(fraud_detector, db=db))
    graph.add_node("route_decision",               partial(route_decision, db=db))
    graph.add_node("response_formatter",            response_formatter)

    graph.set_entry_point("policy_validator")

    graph.add_conditional_edges(
        "policy_validator",
        lambda s: "valid" if s.get("validation_status") == "valid" else "rejected",
        {"valid": "coverage_checker", "rejected": "response_formatter"},
    )

    graph.add_conditional_edges(
        "coverage_checker",
        lambda s: "covered" if s.get("coverage_eligible") else "not_covered",
        {"covered": "document_requirement_checker", "not_covered": "response_formatter"},
    )

    graph.add_conditional_edges(
        "document_requirement_checker",
        lambda s: "missing" if s.get("missing_documents") else "ready",
        {"ready": "fraud_detector", "missing": "response_formatter"},
    )

    graph.add_edge("fraud_detector", "route_decision")
    graph.add_edge("route_decision", "response_formatter")
    graph.add_edge("response_formatter", END)

    return graph.compile()
