"""
Phase 2 Interface: Insurance Claim Evaluation Pipeline Placeholder.

Decoupled from Phase 1 (Intake & Voice Conversation).
Maintains clean interface for Phase 2:
- Policy validation
- Coverage eligibility
- Document requirements (strictly for 6 supported types: health, senior_health, home, travel, motor, cyber)
- Risk scoring
- Adjuster assignment
"""
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, cast

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from src.database.models import Policy, Adjuster
from src.agents.state import ClaimState
from src.utils.logger import app_logger

logger = app_logger

# Document requirements for strict 6 insurance types
DOCUMENT_REQUIREMENTS: Dict[str, List[str]] = {
    "motor": ["damage_photo", "repair_estimate"],
    "home": ["damage_photo"],
    "health": ["medical_bill"],
    "senior_health": ["medical_bill"],
    "travel": ["boarding_pass"],
    "cyber": ["incident_report"],
}

DOCUMENT_LABELS = {
    "damage_photo": "photos of the damage",
    "repair_estimate": "a repair cost estimate",
    "fir": "a police FIR / report",
    "medical_bill": "medical bills / hospital discharge summary",
    "boarding_pass": "boarding pass or flight ticket",
    "incident_report": "cyber forensic / IT incident report",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def policy_validator(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    """Validate policy existence and active coverage dates."""
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
    state["policy_details"] = {
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "coverage_amount": coverage_limit,
        "deductible": deductible_amt,
        "effective_date": str(eff_date),
        "expiry_date": str(exp_date),
        "is_active": policy.is_active,
    }
    _audit(state, f"Policy validation: valid={is_active}")
    return state


def document_requirement_checker(state: ClaimState) -> ClaimState:
    """Evaluate uploaded documents against mandatory requirements."""
    ctype = (state.get("extracted_data") or {}).get("claim_type", "motor")
    required = DOCUMENT_REQUIREMENTS.get(ctype, ["damage_photo"])
    uploaded = set(state.get("uploaded_documents") or [])

    missing = [doc for doc in required if doc not in uploaded]
    state["required_documents"] = required
    state["missing_documents"] = missing
    state["documents_needed"] = len(missing) > 0
    _audit(state, f"Document check: {len(missing)} missing documents ({missing})")
    return state


def coverage_eligibility_calculator(state: ClaimState) -> ClaimState:
    """Calculate coverage eligibility and deductible amounts."""
    if not state.get("policy_valid", False):
        state["coverage_eligible"] = False
        state["coverage_reasoning"] = "Policy is invalid or expired."
        state["payout_amount"] = 0.0
        state["deductible_amount"] = 0.0
        return state

    claimed_raw = (state.get("extracted_data") or {}).get("claimed_amount", 0.0)
    try:
        claimed_amt = float(claimed_raw)
    except (ValueError, TypeError):
        claimed_amt = 0.0

    pdetails = state.get("policy_details") or {}
    coverage_limit = float(pdetails.get("coverage_amount", 0.0))
    deductible = float(pdetails.get("deductible", 0.0))

    if claimed_amt > coverage_limit:
        state["coverage_eligible"] = False
        state["coverage_reasoning"] = f"Claimed amount (₹{claimed_amt:,.2f}) exceeds policy coverage limit (₹{coverage_limit:,.2f})."
        state["payout_amount"] = 0.0
        state["deductible_amount"] = deductible
    else:
        payout = max(0.0, claimed_amt - deductible)
        state["coverage_eligible"] = True
        state["coverage_reasoning"] = "Claim amount is within policy coverage limits."
        state["deductible_amount"] = deductible
        state["payout_amount"] = payout

    _audit(state, f"Coverage evaluated: eligible={state['coverage_eligible']}, payout={state['payout_amount']}")
    return state


def fraud_risk_evaluator(state: ClaimState) -> ClaimState:
    """Evaluate basic anomaly and fraud indicators."""
    flags: List[str] = []
    score = 0.0

    data = state.get("extracted_data") or {}
    inc_date_str = data.get("incident_date")

    if inc_date_str:
        try:
            inc_date = datetime.strptime(inc_date_str, "%Y-%m-%d").date()
            if inc_date > date.today():
                flags.append("future_incident_date")
                score += 0.6
        except ValueError:
            pass

    state["fraud_score"] = min(1.0, score)
    state["fraud_flags"] = flags
    _audit(state, f"Fraud evaluation: score={state['fraud_score']}, flags={flags}")
    return state


def adjuster_router(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    """Route claim to an adjuster based on specialization."""
    if db is None:
        state["assigned_adjuster"] = {"id": "ADJ-DEFAULT", "name": "Claims Team", "email": "claims@insure.co"}
        return state

    ctype = (state.get("extracted_data") or {}).get("claim_type", "motor")
    adj = (
        db.query(Adjuster)
        .filter(Adjuster.is_active == True, Adjuster.specialization == ctype)
        .order_by(Adjuster.claims_assigned.asc())
        .first()
    )
    if not adj:
        adj = db.query(Adjuster).filter(Adjuster.is_active == True).order_by(Adjuster.claims_assigned.asc()).first()

    if adj:
        current_assigned = int(getattr(adj, "claims_assigned", 0) or 0)
        setattr(adj, "claims_assigned", current_assigned + 1)
        db.commit()
        state["assigned_adjuster"] = {
            "id": str(adj.id),
            "name": adj.name,
            "email": adj.email,
            "specialization": adj.specialization,
        }
    else:
        state["assigned_adjuster"] = {"id": "UNASSIGNED", "name": "Claims Queue", "email": "queue@insure.co"}

    _audit(state, f"Assigned adjuster: {state['assigned_adjuster']}")
    return state


def decision_and_payout_formatter(state: ClaimState) -> ClaimState:
    """Format final decision and user message."""
    if not state.get("policy_valid", False):
        state["final_decision"] = "manual_review"
        state["closure_status"] = "pending_review"
        state["response_message"] = "Your policy could not be verified automatically. A claims specialist will review your claim."
    elif state.get("fraud_score", 0.0) >= 0.5:
        state["final_decision"] = "flagged_for_review"
        state["closure_status"] = "pending_review"
        state["response_message"] = "Your claim has been submitted and flagged for expedited specialist review."
    elif not state.get("coverage_eligible", False):
        state["final_decision"] = "denied"
        state["closure_status"] = "closed"
        state["response_message"] = f"Claim denied: {state.get('coverage_reasoning', 'Not eligible under current terms.')}"
    elif state.get("documents_needed", False):
        state["final_decision"] = "need_documents"
        state["closure_status"] = "awaiting_user"
        missing_docs = state.get("missing_documents", [])
        labels = [DOCUMENT_LABELS.get(d, d.replace("_", " ")) for d in missing_docs]
        state["response_message"] = f"Please upload the following required documents: {', '.join(labels)}."
    else:
        state["final_decision"] = "approved"
        state["closure_status"] = "closed"
        payout = state.get("payout_amount", 0.0)
        state["response_message"] = f"Your claim has been approved! Estimated settlement: ₹{payout:,.2f}."

    state["spoken_response"] = state["response_message"]
    _audit(state, f"Final decision: {state['final_decision']}, closure_status: {state['closure_status']}")
    return state


def build_evaluation_graph(db: Optional[Session] = None):
    """Build LangGraph for claim evaluation."""
    graph = StateGraph(ClaimState)  # type: ignore

    def _validate_policy(s: ClaimState) -> ClaimState:
        return policy_validator(s, db=db)

    def _route_adjuster(s: ClaimState) -> ClaimState:
        return adjuster_router(s, db=db)

    graph.add_node("policy_validator", cast(Any, _validate_policy))
    graph.add_node("document_checker", cast(Any, document_requirement_checker))
    graph.add_node("coverage_calculator", cast(Any, coverage_eligibility_calculator))
    graph.add_node("fraud_evaluator", cast(Any, fraud_risk_evaluator))
    graph.add_node("adjuster_router", cast(Any, _route_adjuster))
    graph.add_node("decision_formatter", cast(Any, decision_and_payout_formatter))

    graph.set_entry_point("policy_validator")
    graph.add_edge("policy_validator", "document_checker")
    graph.add_edge("document_checker", "coverage_calculator")
    graph.add_edge("coverage_calculator", "fraud_evaluator")
    graph.add_edge("fraud_evaluator", "adjuster_router")
    graph.add_edge("adjuster_router", "decision_formatter")
    graph.add_edge("decision_formatter", END)

    return graph.compile()
