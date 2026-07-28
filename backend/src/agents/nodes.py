import json
import re
from datetime import date
from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session
# pyrefly: ignore [missing-import]
from src.database.models import Policy, Adjuster
# pyrefly: ignore [missing-import]
from src.agents.state import ClaimState

llm = ChatOllama(model="llama3.1:8b", temperature=0)

# ---------- Node 1: Claim Extractor ----------
EXTRACTION_PROMPT = """Extract structured claim information from the text below.
Return ONLY valid JSON, no markdown, no explanation, matching this schema:
{{
  "policy_id": "string or null",
  "incident_date": "YYYY-MM-DD or null",
  "claim_type": "auto|home|business or null",
  "damage_description": "string",
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
            "claim_type": None, "damage_description": state["claim_text"],
            "claimed_amount": None,
        }

    state["extracted_data"] = extracted
    state.setdefault("audit_log", []).append(f"Extracted: {extracted}")
    return state


# ---------- Node 2: Policy Validator ----------
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


# ---------- Node 3: Coverage Checker (STUBBED — real RAG in September) ----------
def coverage_checker(state: ClaimState) -> ClaimState:
    # TODO (September): replace with pgvector similarity search over
    # policy_embeddings + LLM reasoning over retrieved clauses.
    claimed_amount = state["extracted_data"].get("claimed_amount") or 0
    coverage_amount = state["policy_data"]["coverage_amount"]

    state["coverage_eligible"] = claimed_amount <= coverage_amount
    state.setdefault("audit_log", []).append(
        f"[STUB] Coverage check: claimed={claimed_amount}, limit={coverage_amount}"
    )
    return state


# ---------- Node 4: Fraud Detector (rule-based only, per your scoping) ----------
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

    state["fraud_score"] = min(score, 1.0)
    state["fraud_flags"] = flags
    state.setdefault("audit_log", []).append(f"Fraud score: {state['fraud_score']}, flags: {flags}")
    return state


# ---------- Node 5: Route Decision ----------
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

    import uuid
    state["ticket_id"] = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"
    state.setdefault("audit_log", []).append(f"Routed to {state['assigned_adjuster']}, ticket {state['ticket_id']}")
    return state


# ---------- Node 6: Response Formatter ----------
def response_formatter(state: ClaimState) -> ClaimState:
    if state.get("validation_status") == "rejected":
        decision = "manual_review"
        message = "We couldn't validate your policy. Your claim has been sent for manual review."
    elif not state.get("coverage_eligible", False):
        decision = "denied"
        message = "This claim does not appear to be covered under your policy."
    elif state.get("fraud_score", 0) >= 0.7:
        decision = "flagged_for_review"
        message = "Your claim requires additional review before approval."
    else:
        decision = "approved"
        message = f"Your claim has been approved and assigned ticket {state.get('ticket_id')}."

    state["final_decision"] = decision
    state["response_message"] = message
    return state