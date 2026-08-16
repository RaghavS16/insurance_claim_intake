"""
Conversation and Claim processing graph nodes.
"""
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from src.database.models import Policy, Adjuster
from src.agents.state import ClaimState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM — compiled once at module import so graph.compile() doesn't bear the
# repeated construction cost. timeout=10 enforces quick fallback execution
# when Ollama is offline or slow while allowing local Llama 3.1 inference.
# ---------------------------------------------------------------------------
llm = ChatOllama(model="llama3.1:8b", temperature=0, timeout=10)

def _sanitize_claim_text(text: str) -> str:
    """Sanitize user claim text before injecting into prompt templates."""
    if not text:
        return ""
    clean = text.replace("\x00", "").strip()
    clean = clean.replace("{", "{{").replace("}", "}}")
    return clean[:5000]


# Fields the system must have before it can evaluate a claim.
REQUIRED_FIELDS = ["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"]

# Which document types each claim_type requires.
DOCUMENT_REQUIREMENTS: Dict[str, List[str]] = {
    "auto": ["damage_photo", "repair_estimate"],
    "home": ["damage_photo"],
    "business": [],
}

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def _coerce_amount(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        match = re.search(r"(\d+(?:[,\s]\d+)*(?:\.\d+)?)", raw)
        if match:
            cleaned = match.group(1).replace(",", "").replace(" ", "")
            try:
                return float(cleaned)
            except ValueError:
                pass
        cleaned = re.sub(r"[^\d.]", "", raw)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


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

IMPORTANT: claimed_amount must be a number (not a string). If you cannot determine
a value, use null — do not guess.

Target question previously asked: "{target_field}"
Claim text: "{claim_text}"
"""

def _rule_based_fallback_extraction(claim_text: str, target_field: str | None) -> Dict[str, Any]:
    """Rule-based heuristic fallback to guarantee fast, reliable extraction on direct answers."""
    result: Dict[str, Any] = {}
    clean = claim_text.strip()
    lowered = clean.lower()

    if target_field == "policy_id" or not target_field:
        m = re.search(r"(?:policy|policy number|number)?\s*(?:is|:)?\s*([a-zA-Z0-9\-_]{3,20})", clean, re.IGNORECASE)
        if m:
            val = m.group(1).strip("-").upper()
            if val not in ("MY", "THE", "NUMBER", "IS", "PLEASE", "THAT", "WHAT"):
                result["policy_id"] = val

    if target_field == "claimed_amount" or not target_field:
        amt = _coerce_amount(clean)
        if amt is not None and amt > 0:
            result["claimed_amount"] = amt

    if target_field == "claim_type" or not target_field:
        if any(w in lowered for w in ("car", "auto", "vehicle", "motor", "bike", "accident")):
            result["claim_type"] = "auto"
        elif any(w in lowered for w in ("home", "house", "apartment", "property", "roof", "leak")):
            result["claim_type"] = "home"
        elif any(w in lowered for w in ("business", "shop", "office", "commercial")):
            result["claim_type"] = "business"

    if target_field == "incident_date" or not target_field:
        if "yesterday" in lowered:
            result["incident_date"] = (date.today() - timedelta(days=1)).isoformat()
        elif "today" in lowered:
            result["incident_date"] = date.today().isoformat()
        else:
            m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", clean)
            if m:
                result["incident_date"] = m.group(1)

    if target_field == "damage_description" and len(clean) > 3:
        result["damage_description"] = clean

    return result


def claim_extractor(state: ClaimState) -> ClaimState:
    if state.get("confirmed") or state.get("closure_status") in ("closed", "pending_review"):
        _audit(state, "claim_extractor skipped: claim already confirmed/evaluated")
        return state

    raw_text = state.get("claim_text", "")
    target_field = state.get("next_question_field")
    sanitized_text = _sanitize_claim_text(raw_text)

    prompt = EXTRACTION_PROMPT.format(
        claim_text=sanitized_text,
        target_field=target_field or "general",
    )

    extracted: Dict[str, Any] = {}
    try:
        response = llm.invoke(prompt)
        content = response.content
        raw = content if isinstance(content, str) else str(content)
        raw = raw.strip()
        raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
        extracted = json.loads(raw)
    except Exception as exc:
        logger.warning("claim_extractor LLM fallback: %s", exc)
        extracted = {}

    fallback = _rule_based_fallback_extraction(raw_text, target_field)
    for k, v in fallback.items():
        if v is not None and (extracted.get(k) is None):
            extracted[k] = v

    if "claimed_amount" in extracted:
        extracted["claimed_amount"] = _coerce_amount(extracted["claimed_amount"])

    prior: Dict[str, Any] = state.get("extracted_data") or {}
    locked_fields = {k for k, v in prior.items() if v is not None}

    merged = {**prior}
    for k, v in extracted.items():
        if v is not None and k not in locked_fields:
            merged[k] = v
        elif k not in merged:
            merged[k] = v

    non_null_required = sum(1 for f in REQUIRED_FIELDS if merged.get(f) is not None)
    state["extraction_confidence"] = non_null_required / len(REQUIRED_FIELDS)
    state["extracted_data"] = merged

    _audit(
        state,
        f"Extracted fields: {[k for k, v in merged.items() if v is not None]} "
        f"(confidence={state['extraction_confidence']:.0%})"
    )
    return state


# ---------- Node 2: Mandatory Field Checker ----------
def mandatory_field_checker(state: ClaimState) -> ClaimState:
    data: Dict[str, Any] = state.get("extracted_data") or {}
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    state["missing_fields"] = missing

    if not missing:
        state["awaiting_confirmation"] = True
        state["message"] = (
            f"All required fields received for ticket {state.get('ticket_id')}. "
            "Please confirm your claim details to proceed to evaluation."
        )
        _audit(state, "All mandatory fields present. Awaiting confirmation.")
    else:
        state["awaiting_confirmation"] = False
        state["message"] = (
            f"Claim details missing fields: {', '.join(missing)}. "
            f"Next question: {FIELD_PROMPTS.get(missing[0], missing[0])}"
        )
        _audit(state, f"Missing fields: {missing}")

    return state


# ---------- Node 3: Policy Validator ----------
def policy_validator(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    data: Dict[str, Any] = state.get("extracted_data") or {}
    policy_id = data.get("policy_id")
    if not policy_id:
        state["policy_valid"] = False
        state["policy_details"] = None
        _audit(state, "Policy validation failed: no policy_id provided")
        return state

    if db is None:
        state["policy_valid"] = True
        return state

    policy = db.query(Policy).filter(Policy.policy_id == policy_id).first()
    if not policy:
        state["policy_valid"] = False
        state["policy_details"] = None
        _audit(state, f"Policy validation failed: policy_id '{policy_id}' not found in database")
        return state

    today = date.today()
    is_active = policy.start_date <= today <= policy.end_date

    state["policy_valid"] = is_active
    state["policy_details"] = {
        "policy_id": str(getattr(policy, "policy_id", "")),
        "policy_type": str(getattr(policy, "policy_type", "")),
        "holder_name": str(getattr(policy, "holder_name", "")),
        "start_date": str(getattr(policy, "start_date", "")),
        "end_date": str(getattr(policy, "end_date", "")),
        "coverage_limit": float(getattr(policy, "coverage_limit", 0.0) or 0.0),
        "deductible": float(getattr(policy, "deductible", 0.0) or 0.0),
    }
    _audit(state, f"Policy '{policy_id}' validated: valid={is_active} (active window: {policy.start_date} to {policy.end_date})")
    return state


# ---------- Node 4: Coverage Checker ----------
def coverage_checker(state: ClaimState) -> ClaimState:
    if not state.get("policy_valid"):
        state["coverage_eligible"] = False
        state["deductible_amount"] = 0.0
        state["payout_amount"] = 0.0
        _audit(state, "Coverage check failed: policy is not valid")
        return state

    extracted: Dict[str, Any] = state.get("extracted_data") or {}
    policy: Dict[str, Any] = state.get("policy_details") or {}
    claim_type = extracted.get("claim_type", "")
    policy_type = policy.get("policy_type", "")

    if policy_type and claim_type != policy_type:
        state["coverage_eligible"] = False
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

    is_eligible = limit == 0 or claimed <= limit
    state["coverage_eligible"] = is_eligible
    state["deductible_amount"] = deductible
    state["payout_amount"] = max(0.0, min(claimed, limit) - deductible) if is_eligible and limit > 0 else claimed

    _audit(
        state,
        f"Coverage eligible: {is_eligible} (claimed={claimed}, limit={limit}, "
        f"deductible={deductible}, estimated payout={state['payout_amount']})"
    )
    return state


# ---------- Node 5: Document Requirement Checker ----------
def document_requirement_checker(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    extracted: Dict[str, Any] = state.get("extracted_data") or {}
    claim_type = extracted.get("claim_type", "")
    required_doc_types = DOCUMENT_REQUIREMENTS.get(str(claim_type), [])

    if not required_doc_types:
        state["missing_documents"] = []
        _audit(state, f"Document check: claim_type '{claim_type}' requires no documents")
        return state

    uploaded_list: List[str] = state.get("uploaded_documents") or []
    uploaded_types: Set[str] = set(uploaded_list)
    missing = [doc for doc in required_doc_types if doc not in uploaded_types]

    state["missing_documents"] = missing
    _audit(state, f"Document check: required={required_doc_types}, uploaded={list(uploaded_types)}, missing={missing}")
    return state


# ---------- Node 6: Fraud Detector ----------
FRAUD_PROMPT = """Analyze this insurance claim for fraud risk.
Evaluate:
1. Is the claimed amount unusually high for this incident type?
2. Does the damage description match the incident date/type?
3. Are there inconsistencies in the narrative?

Return ONLY valid JSON, no markdown, no explanation:
{{
  "fraud_score": <integer 0-100>,
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

def fraud_detector(state: ClaimState) -> ClaimState:
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

    try:
        response = llm.invoke(prompt)
        content = response.content
        raw = content if isinstance(content, str) else str(content)
        raw = raw.strip()
        raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        score = int(result.get("fraud_score", 0))
        flags = list(result.get("flags", []))
    except Exception as exc:
        logger.warning("fraud_detector LLM failed (%s), running heuristic rules", exc)
        score = 0
        flags = []

    claimed = float(extracted.get("claimed_amount") or 0.0)
    limit = float(policy.get("coverage_limit") or 0.0)
    if limit > 0 and claimed > 0.8 * limit:
        score = max(score, 45)
        flags.append("HIGH_CLAIM_AMOUNT_NEAR_LIMIT")

    state["fraud_score"] = float(score)
    state["fraud_flags"] = flags
    _audit(state, f"Fraud check complete: score={score}, flags={flags}")
    return state


# ---------- Node 7: Route Decision (Adjuster Assignment) ----------
def route_decision(state: ClaimState, db: Optional[Session] = None) -> ClaimState:
    if db is None:
        state["assigned_adjuster"] = None
        return state

    adjusters = db.query(Adjuster).filter(Adjuster.status == "active").all()
    if not adjusters:
        state["assigned_adjuster"] = None
        _audit(state, "Adjuster routing: no active adjusters found in database")
        return state

    least_loaded = min(adjusters, key=lambda a: a.current_cases)
    least_loaded.current_cases += 1
    db.commit()

    state["assigned_adjuster"] = {
        "id": str(least_loaded.id),
        "name": least_loaded.name,
        "email": least_loaded.email,
        "specialization": least_loaded.specialization,
        "current_cases": least_loaded.current_cases,
    }
    _audit(state, f"Assigned to adjuster '{least_loaded.name}' (current_cases now={least_loaded.current_cases})")
    return state


# ---------- Node 8: Response Formatter ----------
def response_formatter(state: ClaimState) -> ClaimState:
    if not state.get("policy_valid"):
        message = (
            f"Your claim under ticket {state.get('ticket_id')} has been denied. "
            "Reason: The policy ID provided could not be verified or is not currently active."
        )
        state["final_decision"] = "denied"
        state["closure_status"] = "closed"

    elif not state.get("coverage_eligible"):
        message = (
            f"Your claim under ticket {state.get('ticket_id')} has been denied. "
            "Reason: The claim details or amount do not meet the coverage terms of your policy."
        )
        state["final_decision"] = "denied"
        state["closure_status"] = "closed"

    elif state.get("missing_documents"):
        missing_labels = [DOCUMENT_LABELS.get(d, d.replace("_", " ")) for d in state.get("missing_documents", [])]
        message = (
            f"Your claim (ticket {state.get('ticket_id')}) is eligible for coverage, but requires additional documentation: "
            f"{', '.join(missing_labels)}. Please upload these documents to complete your claim."
        )
        state["final_decision"] = "manual_review"
        state["closure_status"] = "awaiting_user"

    elif state.get("fraud_score", 0) > 60:
        adjuster = state.get("assigned_adjuster") or {}
        message = (
            f"Your claim (ticket {state.get('ticket_id')}) has been flagged for adjuster review due to validation flags: "
            f"{', '.join(state.get('fraud_flags', []))}. Assigned to {adjuster.get('name', 'an adjuster')}."
        )
        state["final_decision"] = "flagged_for_review"
        state["closure_status"] = "pending_review"

    else:
        adjuster = state.get("assigned_adjuster") or {}
        message = (
            f"Your claim has been approved. Ticket {state.get('ticket_id')}. "
            f"Approved payout: ₹{state.get('payout_amount', 0):,.0f} "
            f"after a ₹{state.get('deductible_amount', 0):,.0f} deductible. "
            f"Assigned to {adjuster.get('name', 'an adjuster')} for processing."
        )
        state["final_decision"] = "approved"
        state["closure_status"] = "closed"

    state["response_message"] = message
    state["spoken_response"] = message
    _audit(state, f"Final decision: {state['final_decision']} ({state['closure_status']})")
    return state


# =============================================================================
# Conversational Turn Nodes
# =============================================================================

UNKNOWN_SENTINEL = "UNKNOWN"

CORRECTION_MARKERS = (
    "actually", "sorry, i meant", "i meant to say", "no wait", "correction",
    "let me correct", "scratch that", "i said that wrong",
)
DONT_KNOW_MARKERS = ("i don't know", "i dont know", "not sure", "no idea", "i'll check")
DEFER_MARKERS = ("i'll provide it later", "later", "not right now", "i'll get back to you")
REPEAT_MARKERS = ("repeat that", "say that again", "come again", "what was that", "pardon")


def _detect_utterance_intent(text: str) -> str:
    lowered = text.lower().strip()
    if any(m in lowered for m in REPEAT_MARKERS):
        return "repeat"
    if any(m in lowered for m in CORRECTION_MARKERS):
        return "correction"
    if any(m in lowered for m in DONT_KNOW_MARKERS):
        return "dont_know"
    if any(m in lowered for m in DEFER_MARKERS):
        return "defer"
    return "normal"


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    utterance = state.get("claim_text", "")
    state["last_user_utterance"] = utterance
    intent = _detect_utterance_intent(utterance)
    target_field = state.get("next_question_field")

    if intent == "repeat":
        _audit(state, f"User asked to repeat. Re-emitting question for '{target_field}'.")
        state["conversation_status"] = "in_progress"
        state["_skip_extraction"] = True
        return state

    if intent in ("dont_know", "defer") and target_field:
        extracted = dict(state.get("extracted_data") or {})
        extracted[target_field] = UNKNOWN_SENTINEL
        state["extracted_data"] = extracted
        unknowns = list(state.get("unknown_fields") or [])
        if target_field not in unknowns:
            unknowns.append(target_field)
        state["unknown_fields"] = unknowns
        _audit(state, f"User deferred field '{target_field}' (intent={intent}); marked UNKNOWN.")
        state["_skip_extraction"] = True
        return state

    if intent == "correction" and target_field:
        prior = dict(state.get("extracted_data") or {})
        prior[target_field] = None
        state["extracted_data"] = prior
        _audit(state, f"Detected correction for field '{target_field}'; unlocked for re-extraction.")

    state["_skip_extraction"] = False
    return state


def next_question_generator(state: ClaimState) -> ClaimState:
    if state.get("_skip_extraction") and state.get("next_question"):
        _audit(state, "Re-emitting previous question.")
        return state

    missing = state.get("missing_fields", [])
    if not missing:
        state["next_question"] = ""
        state["next_question_field"] = ""
        return state

    field = missing[0]
    state["next_question_field"] = field
    state["next_question"] = FIELD_PROMPTS.get(field, f"Could you tell me {field.replace('_', ' ')}?")
    state["conversation_status"] = "in_progress"
    _audit(state, f"Generated next question for '{field}': '{state['next_question']}'")
    return state


def document_request_generator(state: ClaimState) -> ClaimState:
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


def intake_completion_marker(state: ClaimState) -> ClaimState:
    ticket_id = state.get("ticket_id", "your claim")
    state["conversation_status"] = "intake_complete"
    state["next_question"] = (
        f"Thank you for reporting your claim. Your ticket ID is {ticket_id}. "
        "We have collected all your details and required documents. "
        "Your claim intake is complete and submitted for automated evaluation."
    )
    state["next_question_field"] = ""
    _audit(state, "Claim intake conversation complete; all mandatory fields & docs present.")
    return state