import json
import re
import uuid
from datetime import date
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from src.database.models import Policy, Adjuster
from src.agents.state import ClaimState

llm = ChatOllama(model="llama3.1:8b", temperature=0)

# Fields the system must have before it can evaluate a claim.
REQUIRED_FIELDS = ["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"]

# Which document types each claim_type requires. Empty list = documents not needed;
# document_requirement_checker will skip the whole check for that claim_type.
DOCUMENT_REQUIREMENTS = {
    "auto": ["damage_photo", "repair_estimate"],
    "home": ["damage_photo"],
    "business": [],   # example of a claim_type that legitimately needs no documents
}

# Human-readable prompts for missing fields (used for both text display and TTS in Sept)
FIELD_PROMPTS = {
    "policy_id": "What is your policy number?",
    "incident_date": "What date did the incident occur?",
    "claim_type": "What type of claim is this (auto, home, or business)?",
    "damage_description": "Can you describe the damage or loss?",
    "claimed_amount": "What is the estimated cost or amount you are claiming?",
}

DOCUMENT_LABELS = {
    "damage_photo": "photos of the damage",
    "repair_estimate": "a repair cost estimate",
    "fir": "a police FIR / report",
}


# ---------- Node 1: Claim Extractor ----------
EXTRACTION_PROMPT = """Extract structured claim information from the text below.
Return ONLY valid JSON, no markdown, no explanation, matching this schema:
{{
  "policy_id": "string or null",
  "incident_date": "YYYY-MM-DD or null",
  "claim_type": "auto|home|business or null",
  "damage_description": "string or null",
  "claimed_amount": number or null
}}

Claim text: "{claim_text}"
"""

def claim_extractor(state: ClaimState) -> ClaimState:
    prompt = EXTRACTION_PROMPT.format(claim_text=state["claim_text"])
    response = llm.invoke(prompt)
    content = response.content
    raw = content if isinstance(content, str) else str(content)
    raw = raw.strip()
    raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        extracted = {
            "policy_id": None, "incident_date": None,
            "claim_type": state.get("claim_type_hint"), "damage_description": state["claim_text"],
            "claimed_amount": None,
        }

    # Merge with anything already known (e.g. answers supplied in a previous confirm-loop turn)
    merged = {**state.get("extracted_data", {}), **{k: v for k, v in extracted.items() if v is not None}}
    state["extracted_data"] = merged
    state.setdefault("audit_log", []).append(f"Extracted: {merged}")
    return state


# ---------- Node 2: Mandatory Field Checker ----------
def mandatory_field_checker(state: ClaimState) -> ClaimState:
    data = state.get("extracted_data", {})
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    state["missing_fields"] = missing
    state["awaiting_confirmation"] = len(missing) == 0
    if missing:
        state.setdefault("audit_log", []).append(f"Missing required fields: {missing}")
    else:
        state.setdefault("audit_log", []).append("All mandatory fields present")
    return state


# ---------- Node 3: Policy Validator ----------
def policy_validator(state: ClaimState, db: Session) -> ClaimState:
    policy_id = state["extracted_data"].get("policy_id")
    policy = db.query(Policy).filter(Policy.policy_number == policy_id).first() if policy_id else None

    if not policy or not policy.is_active or policy.expiry_date < date.today():
        state["policy_data"] = {}
        state["validation_status"] = "rejected"
        state.setdefault("audit_log", []).append(f"Policy validation failed for {policy_id}")
        return state

    state["policy_data"] = {
        "id": str(policy.id),
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "coverage_amount": float(policy.coverage_amount),  # type: ignore
        "deductible": float(policy.deductible),  # type: ignore
    }
    state["validation_status"] = "valid"
    state.setdefault("audit_log", []).append(f"Policy {policy_id} validated")
    return state


def document_requirement_checker(state: ClaimState) -> ClaimState:
    extracted = state.get("extracted_data") or {}
    claim_type = str(extracted.get("claim_type") or "")
    required = DOCUMENT_REQUIREMENTS.get(claim_type, [])
    state["required_documents"] = required
    state["documents_needed"] = len(required) > 0

    if not required:
        state["missing_documents"] = []
        state.setdefault("audit_log", []).append(f"No documents required for claim_type={claim_type}")
        return state

    uploaded_types = {d.get("document_type") for d in state.get("documents", [])}
    missing = [d for d in required if d not in uploaded_types]
    state["missing_documents"] = missing
    state.setdefault("audit_log", []).append(
        f"Required documents: {required}, missing: {missing}"
    )
    return state


# ---------- Node 5: Coverage Checker (STUBBED — real RAG in September) ----------
def coverage_checker(state: ClaimState) -> ClaimState:
    # TODO (September): replace amount-only check with pgvector similarity search over
    # policy_embeddings + LLM reasoning over retrieved clauses to determine peril coverage,
    # not just the amount ceiling checked here.
    claimed_amount = state["extracted_data"].get("claimed_amount") or 0
    coverage_amount = state["policy_data"]["coverage_amount"]
    deductible = state["policy_data"].get("deductible", 0)

    eligible = claimed_amount <= coverage_amount
    state["coverage_eligible"] = eligible
    state["coverage_reasoning"] = (
        f"[STUB] Claimed amount ₹{claimed_amount} is within policy limit ₹{coverage_amount}."
        if eligible else
        f"[STUB] Claimed amount ₹{claimed_amount} exceeds policy limit ₹{coverage_amount}."
    )

    if eligible:
        state["deductible_amount"] = deductible
        state["payout_amount"] = max(claimed_amount - deductible, 0)
    else:
        state["deductible_amount"] = 0
        state["payout_amount"] = 0

    state.setdefault("audit_log", []).append(
        f"[STUB] Coverage check: claimed={claimed_amount}, limit={coverage_amount}, "
        f"deductible={state['deductible_amount']}, payout={state['payout_amount']}"
    )
    return state


# ---------- Node 6: Fraud Detector (rule-based only, per your scoping) ----------
def fraud_detector(state: ClaimState, db: Session) -> ClaimState:
    flags = []
    score = 0.0
    amount = state["extracted_data"].get("claimed_amount") or 0
    coverage_amount = state["policy_data"]["coverage_amount"]

    if amount > coverage_amount * 0.9:
        flags.append("claim_near_policy_limit")
        score += 0.3

    incident_date_str = state["extracted_data"].get("incident_date")
    if incident_date_str:
        try:
            incident = date.fromisoformat(incident_date_str)
            if incident > date.today():
                flags.append("future_incident_date")
                score += 0.4
        except ValueError:
            flags.append("unparseable_incident_date")
            score += 0.1

    if not state["extracted_data"].get("damage_description"):
        flags.append("missing_description")
        score += 0.1

    # Document-based signal: only meaningful once documents actually exist in state.
    if state.get("documents_needed") and not state.get("documents"):
        flags.append("no_supporting_documents")
        score += 0.1

    state["fraud_score"] = min(score, 1.0)
    state["fraud_flags"] = flags
    state.setdefault("audit_log", []).append(f"Fraud score: {state['fraud_score']}, flags: {flags}")
    return state


# ---------- Node 7: Route Decision ----------
def route_decision(state: ClaimState, db: Session) -> ClaimState:
    claim_type = state["extracted_data"].get("claim_type", "auto")
    adjuster = (
        db.query(Adjuster)
        .filter(Adjuster.specialization == claim_type, Adjuster.is_active == True)
        .first()
    ) or db.query(Adjuster).filter(Adjuster.specialization == "complex").first()

    state["assigned_adjuster"] = {
        "id": str(adjuster.id), "name": adjuster.name, "email": adjuster.email,
    } if adjuster else {}

    if not state.get("ticket_id"):
        state["ticket_id"] = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    state.setdefault("audit_log", []).append(f"Routed to {state['assigned_adjuster']}, ticket {state['ticket_id']}")
    return state


# ---------- Node 8: Response Formatter (closure + feedback text/speech) ----------
def response_formatter(state: ClaimState) -> ClaimState:
    # 1. Still missing mandatory fields -> ask user, nothing else has run yet
    if state.get("missing_fields"):
        prompts = [FIELD_PROMPTS.get(f, f"Please provide {f}.") for f in state["missing_fields"]]
        message = "I need a bit more information. " + " ".join(prompts)
        state["final_decision"] = "need_more_info"
        state["closure_status"] = "awaiting_user"

    # 2. Fields complete but required documents missing -> ask user to upload
    elif state.get("missing_documents"):
        labels = [DOCUMENT_LABELS.get(d, d) for d in state["missing_documents"]]
        message = (
            "Before I can evaluate your claim, please upload: " + ", ".join(labels) +
            ". If a document you attached doesn't match what's required, please re-upload the correct one."
        )
        state["final_decision"] = "need_documents"
        state["closure_status"] = "awaiting_user"

    # 3. Policy invalid -> manual review, cannot auto-decide
    elif state.get("validation_status") == "rejected":
        message = "We couldn't validate your policy. Your claim has been sent for manual review."
        state["final_decision"] = "manual_review"
        state["closure_status"] = "pending_review"

    # 4. Not covered -> denied, closed immediately with reasoning
    elif not state.get("coverage_eligible", False):
        reasoning = state.get("coverage_reasoning", "This claim does not appear to be covered under your policy.")
        message = f"Your claim has been denied. {reasoning}"
        state["final_decision"] = "denied"
        state["closure_status"] = "closed"

    # 5. High fraud/risk score -> flagged, routed to adjuster/insurer, NOT closed yet
    elif state.get("fraud_score", 0) >= 0.7:
        message = (
            "Your claim requires additional review due to some unusual patterns. "
            f"It has been routed to {state.get('assigned_adjuster', {}).get('name', 'an adjuster')} "
            "for manual review. You'll be notified once a decision is made."
        )
        state["final_decision"] = "flagged_for_review"
        state["closure_status"] = "pending_review"

    # 6. Covered, low risk -> auto-approved, routed for processing
    else:
        message = (
            f"Your claim has been approved. Ticket {state.get('ticket_id')}. "
            f"Approved payout (before final adjuster sign-off): ₹{state.get('payout_amount', 0)} "
            f"after a ₹{state.get('deductible_amount', 0)} deductible. "
            f"Assigned to {state.get('assigned_adjuster', {}).get('name', 'an adjuster')} for processing."
        )
        state["final_decision"] = "approved"
        state["closure_status"] = "closed"  # pipeline's job is done; payment/finance handled outside system (stub)

    state["response_message"] = message
    state["spoken_response"] = message  # identical for now; kept separate for Sept TTS phrasing tweaks
    state.setdefault("audit_log", []).append(f"Final decision: {state['final_decision']} ({state['closure_status']})")
    return state