import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict

from langchain_ollama import ChatOllama
from sqlalchemy.orm import Session

from src.database.models import Policy, Adjuster
from src.agents.state import ClaimState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM — compiled once at module import so graph.compile() doesn't bear the
# repeated construction cost.  timeout=60 enforces the <5s-per-node target;
# Ollama hangs will surface as a TimeoutError rather than blocking forever.
# ---------------------------------------------------------------------------
llm = ChatOllama(model="llama3.1:8b", temperature=0, timeout=60)

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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as an ISO-8601 string for audit log entries."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    """Append a timestamped entry to the audit log. R3-7 fix."""
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def _coerce_amount(raw: Any) -> float | None:
    """
    Safely coerce a claimed_amount value from the LLM into a float.

    The LLM sometimes returns:
      - A JSON number  → already float/int, just cast
      - A string like "50,000" or "₹50000" → strip non-numeric chars and cast
      - None           → return None (field still missing)

    R1-9 fix: without this, coverage_checker's `<=` raises TypeError on strings.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
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

Claim text: "{claim_text}"
"""

def claim_extractor(state: ClaimState) -> ClaimState:
    # R1-5: If the claim is already confirmed/evaluated, short-circuit to avoid
    # a re-submission or retry overwriting already-confirmed field data with
    # potentially worse re-extracted data from stale/empty text.
    if state.get("confirmed") or state.get("closure_status") in ("closed", "pending_review"):
        _audit(state, "claim_extractor skipped: claim already confirmed/evaluated")
        return state

    prompt = EXTRACTION_PROMPT.format(claim_text=state["claim_text"])
    try:
        response = llm.invoke(prompt)
        content = response.content
        raw = content if isinstance(content, str) else str(content)
        raw = raw.strip()
        raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("claim_extractor: JSON decode failed, using fallback extraction")
        extracted: Dict[str, Any] = {
            "policy_id": None, "incident_date": None,
            "claim_type": state.get("claim_type_hint"), "damage_description": state["claim_text"],
            "claimed_amount": None,
        }
    except Exception as exc:
        logger.error("claim_extractor: LLM invocation failed: %s", exc)
        extracted: Dict[str, Any] = {
            "policy_id": None, "incident_date": None,
            "claim_type": state.get("claim_type_hint"), "damage_description": state["claim_text"],
            "claimed_amount": None,
        }

    # R1-9: Coerce claimed_amount to float immediately after extraction so that
    # all downstream nodes always work with a numeric type.
    if "claimed_amount" in extracted:
        extracted["claimed_amount"] = _coerce_amount(extracted["claimed_amount"])

    # R1-4: Field-locking: once a field exists in prior state with a non-null
    # value, a second-turn re-extraction must NOT silently overwrite it.
    # Only merge fields that are currently absent or null in the existing data.
    prior = state.get("extracted_data") or {}
    locked_fields = {k for k, v in prior.items() if v is not None}

    merged = {**prior}
    for k, v in extracted.items():
        if v is not None and k not in locked_fields:
            merged[k] = v
        elif k not in merged:
            merged[k] = v  # allow writing null for absent keys so missing_fields works

    # R3-8: Populate extraction_confidence as a proxy — ratio of required fields
    # that are now non-null. This wires in the previously-dead schema column.
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
    data = state.get("extracted_data", {})
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    state["missing_fields"] = missing
    state["awaiting_confirmation"] = len(missing) == 0
    if missing:
        _audit(state, f"Missing required fields: {missing}")
    else:
        _audit(state, "All mandatory fields present")
    return state


# ---------- Node 3: Policy Validator ----------
def policy_validator(state: ClaimState, db: Session) -> ClaimState:
    policy_id = state["extracted_data"].get("policy_id")
    policy = db.query(Policy).filter(Policy.policy_number == policy_id).first() if policy_id else None

    if not policy or not policy.is_active or policy.expiry_date < date.today():
        state["policy_data"] = {}
        state["validation_status"] = "rejected"
        _audit(state, f"Policy validation failed for {policy_id}")
        return state

    # R2-3: Validate that the user-declared claim_type matches the policy's
    # actual policy_type.  Mismatched types (e.g. "business" claim on an "auto"
    # policy) are not a denial — but we flag it and route to manual review so
    # an adjuster can verify, rather than silently approving on wrong coverage.
    declared_claim_type = str(state["extracted_data"].get("claim_type") or "")
    if declared_claim_type and declared_claim_type != policy.policy_type:
        state["policy_data"] = {
            "id": str(policy.id),
            "policy_number": policy.policy_number,
            "policy_type": policy.policy_type,
            "coverage_amount": float(policy.coverage_amount),  # type: ignore
            "deductible": float(policy.deductible),  # type: ignore
        }
        state["validation_status"] = "type_mismatch"
        _audit(
            state,
            f"Claim type mismatch: declared='{declared_claim_type}', "
            f"policy type='{policy.policy_type}'. Routing to manual review."
        )
        return state

    state["policy_data"] = {
        "id": str(policy.id),
        "policy_number": policy.policy_number,
        "policy_type": policy.policy_type,
        "coverage_amount": float(policy.coverage_amount),  # type: ignore
        "deductible": float(policy.deductible),  # type: ignore
    }
    state["validation_status"] = "valid"
    _audit(state, f"Policy {policy_id} validated (type={policy.policy_type})")
    return state


# ---------- Node 4: Document Requirement Checker ----------
def document_requirement_checker(state: ClaimState) -> ClaimState:
    extracted = state.get("extracted_data") or {}
    # R1-2: Use the policy's actual type (already validated) as the canonical
    # source — falls back to the user-declared claim_type only if policy_data
    # is absent (e.g. during unit tests without DB).
    policy_type = (state.get("policy_data") or {}).get("policy_type")
    claim_type = str(policy_type or extracted.get("claim_type") or "")
    required = DOCUMENT_REQUIREMENTS.get(claim_type, [])
    state["required_documents"] = required
    state["documents_needed"] = len(required) > 0

    if not required:
        state["missing_documents"] = []
        _audit(state, f"No documents required for claim_type={claim_type}")
        return state

    uploaded_types = {d.get("document_type") for d in state.get("documents", [])}
    missing = [d for d in required if d not in uploaded_types]
    state["missing_documents"] = missing
    _audit(state, f"Required documents: {required}, missing: {missing}")
    return state


# ---------- Node 5: Coverage Checker (STUBBED — real RAG in September) ----------
def coverage_checker(state: ClaimState) -> ClaimState:
    # TODO (September): replace amount-only check with pgvector similarity search over
    # policy_embeddings + LLM reasoning over retrieved clauses to determine peril coverage,
    # not just the amount ceiling checked here.
    # NOTE: coverage_checker only runs for claims that reach this node (valid policy,
    # documents ready). manual_review claims short-circuit at policy_validator.
    # deductible_amount/payout_amount are explicitly absent for manual_review cases
    # by design, not by omission — see response_formatter branch 3.

    raw_amount = state["extracted_data"].get("claimed_amount")
    # R2-2: Sanity-check claimed_amount sign/magnitude.
    # _coerce_amount already ran in claim_extractor, but guard again defensively.
    claimed_amount = _coerce_amount(raw_amount) or 0.0
    if claimed_amount < 0:
        _audit(state, f"WARN: negative claimed_amount ({claimed_amount}) clamped to 0")
        claimed_amount = 0.0

    policy_data = state.get("policy_data") or {}
    coverage_amount = float(policy_data.get("coverage_amount") or 0)
    deductible = float(policy_data.get("deductible") or 0)

    eligible = claimed_amount <= coverage_amount
    state["coverage_eligible"] = eligible
    state["coverage_reasoning"] = (
        f"Claimed amount ₹{claimed_amount:,.0f} is within your policy limit of ₹{coverage_amount:,.0f}."
        if eligible else
        f"Claimed amount ₹{claimed_amount:,.0f} exceeds your policy limit of ₹{coverage_amount:,.0f}."
    )

    if eligible:
        state["deductible_amount"] = deductible
        state["payout_amount"] = max(claimed_amount - deductible, 0)
    else:
        state["deductible_amount"] = 0.0
        state["payout_amount"] = 0.0

    _audit(
        state,
        f"Coverage check: claimed=₹{claimed_amount:,.0f}, limit=₹{coverage_amount:,.0f}, "
        f"deductible=₹{state['deductible_amount']:,.0f}, payout=₹{state['payout_amount']:,.0f}"
    )
    return state


# ---------- Node 6: Fraud Detector (rule-based only, per scoping) ----------
def fraud_detector(state: ClaimState, db: Session) -> ClaimState:
    flags = []
    score = 0.0
    raw_amount = state["extracted_data"].get("claimed_amount")
    amount = _coerce_amount(raw_amount) or 0.0
    policy_data = state.get("policy_data") or {}
    coverage_amount = float(policy_data.get("coverage_amount") or 0)

    if amount > coverage_amount * 0.9:
        flags.append("claim_near_policy_limit")
        score += 0.3

    # R3-9: Robust date parsing — flag unparseable dates explicitly rather than
    # silently creating a two-truth situation (string in extracted_data vs None in DB).
    incident_date_str = state["extracted_data"].get("incident_date")
    if incident_date_str:
        try:
            incident = date.fromisoformat(incident_date_str)
            if incident > date.today():
                flags.append("future_incident_date")
                score += 0.4
        except (ValueError, TypeError):
            flags.append("unparseable_incident_date")
            score += 0.1
            _audit(state, f"WARN: incident_date '{incident_date_str}' could not be parsed as YYYY-MM-DD")

    if not state["extracted_data"].get("damage_description"):
        flags.append("missing_description")
        score += 0.1

    # NOTE (R1-11): The `no_supporting_documents` check below is intentionally
    # preserved for potential future graph redesigns where fraud_detector might
    # run before the documents-ready gate.  In the current graph, this branch
    # is unreachable because fraud_detector only runs after the documents-ready
    # conditional edge in graph.py.  It is a no-op at runtime, not a bug.
    if state.get("documents_needed") and not state.get("documents"):
        flags.append("no_supporting_documents")
        score += 0.1

    state["fraud_score"] = min(score, 1.0)
    state["fraud_flags"] = flags
    _audit(state, f"Fraud score: {state['fraud_score']:.2f}, flags: {flags}")
    return state


# ---------- Node 7: Route Decision ----------
def route_decision(state: ClaimState, db: Session) -> ClaimState:
    # R1-1: Use `or "auto"` so that a None claim_type (not just a missing key)
    # also triggers the default, preventing the adjuster query from matching nothing.
    claim_type = state["extracted_data"].get("claim_type") or "auto"

    # R2-6: Load-balance by ordering adjusters by claims_assigned ascending so
    # the least-loaded adjuster is always picked first, not just the first match.
    adjuster = (
        db.query(Adjuster)
        .filter(Adjuster.specialization == claim_type, Adjuster.is_active == True)  # noqa: E712
        .order_by(Adjuster.claims_assigned.asc())
        .first()
    ) or (
        db.query(Adjuster)
        .filter(Adjuster.specialization == "complex", Adjuster.is_active == True)  # noqa: E712
        .order_by(Adjuster.claims_assigned.asc())
        .first()
    )

    # R3-12: Guard against the case where no adjuster at all exists in the DB
    # (e.g. empty seed, or all adjusters deactivated).  Without this, the claim
    # would be approved with assigned_adjuster_id=NULL and no accountability trail.
    if not adjuster:
        _audit(
            state,
            "WARN: No active adjuster found for any specialization. "
            "Claim will proceed without an assigned adjuster — manual intervention required."
        )
        state["assigned_adjuster"] = {}
    else:
        state["assigned_adjuster"] = {
            "id": str(adjuster.id), "name": adjuster.name, "email": adjuster.email,
        }
        # R2-6: Increment claims_assigned so the next claim uses load balancing correctly.
        adjuster.claims_assigned = (adjuster.claims_assigned or 0) + 1  # type: ignore
        db.flush()  # write within the same transaction; committed in the API layer

    if not state.get("ticket_id"):
        state["ticket_id"] = f"CLAIM-{uuid.uuid4().hex[:8].upper()}"

    adjuster_name = state["assigned_adjuster"].get("name", "UNASSIGNED")
    _audit(state, f"Routed to adjuster '{adjuster_name}', ticket {state['ticket_id']}")
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
    elif state.get("validation_status") in ("rejected", "type_mismatch"):
        if state.get("validation_status") == "type_mismatch":
            policy_type = (state.get("policy_data") or {}).get("policy_type", "unknown")
            declared = state["extracted_data"].get("claim_type", "unknown")
            message = (
                f"Your claim type ('{declared}') does not match your policy type ('{policy_type}'). "
                "Your claim has been sent for manual review by an adjuster who will verify coverage."
            )
        else:
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
            f"Approved payout (before final adjuster sign-off): ₹{state.get('payout_amount', 0):,.0f} "
            f"after a ₹{state.get('deductible_amount', 0):,.0f} deductible. "
            f"Assigned to {state.get('assigned_adjuster', {}).get('name', 'an adjuster')} for processing."
        )
        state["final_decision"] = "approved"
        state["closure_status"] = "closed"  # pipeline's job is done; payment/finance handled outside system (stub)

    state["response_message"] = message
    state["spoken_response"] = message  # identical for now; kept separate for Sept TTS phrasing tweaks
    _audit(state, f"Final decision: {state['final_decision']} ({state['closure_status']})")
    return state