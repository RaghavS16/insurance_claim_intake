"""
Review 1: Conversational Claim Intake Graph Nodes.

Implements:
- Sanitized LLM prompt invocation with fast fallback
- Deterministic heuristic field extraction (policy_id, incident_date, claim_type, description, amount)
- Mandatory field validation & confidence scoring
- Intent detection (normal, repeat, correction, dont_know, defer)
- Dynamic next-question generation
- State updates and field-locking
"""
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langchain_ollama import ChatOllama

from src.agents.state import ClaimState

logger = logging.getLogger(__name__)

# Configurable Ollama connection with quick fallback
_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
llm = ChatOllama(base_url=_OLLAMA_URL, model="llama3.1:8b", temperature=0, timeout=10)

# Mandatory fields required for Review 1 claim intake
REQUIRED_FIELDS = ["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"]

FIELD_PROMPTS = {
    "policy_id": "What is your policy number?",
    "incident_date": "What date did the incident occur?",
    "claim_type": "What type of claim is this (auto, home, or business)?",
    "damage_description": "Can you describe the damage or loss?",
    "claimed_amount": "What is the estimated cost or amount you are claiming?",
}

UNKNOWN_SENTINEL = "UNKNOWN"

CORRECTION_MARKERS = (
    "actually", "sorry, i meant", "i meant to say", "no wait", "correction",
    "let me correct", "scratch that", "i said that wrong", "mistake",
)
DONT_KNOW_MARKERS = ("i don't know", "i dont know", "not sure", "no idea", "i'll check", "dont know")
DEFER_MARKERS = ("i'll provide it later", "later", "not right now", "i'll get back to you", "skip", "pass")
REPEAT_MARKERS = ("repeat that", "say that again", "come again", "what was that", "pardon", "repeat")

COMMON_STOP_WORDS = {
    "MY", "THE", "NUMBER", "IS", "PLEASE", "THAT", "WHAT", "IT", "ITS",
    "CAR", "DAMAGE", "DAMAGED", "HIT", "ACCIDENT", "RUPEES", "RS", "TODAY", "YESTERDAY",
    "AUTO", "HOME", "BUSINESS", "YES", "NO", "HELLO", "HI", "THANKS", "THANK"
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def _sanitize_claim_text(text: str) -> str:
    """Sanitize user claim text before injecting into prompt templates."""
    if not text:
        return ""
    clean = text.replace("\x00", "").strip()
    clean = clean.replace("{", "{{").replace("}", "}}")
    return clean[:5000]


def _coerce_amount(raw: Any) -> float | None:
    """Safely coerce any numeric or string representation to a float amount."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None
    if isinstance(raw, str):
        match = re.search(r"(\d+(?:[,\s]\d+)*(?:\.\d+)?)", raw)
        if match:
            cleaned = match.group(1).replace(",", "").replace(" ", "")
            try:
                val = float(cleaned)
                return val if val >= 0 else None
            except ValueError:
                pass
        cleaned = re.sub(r"[^\d.]", "", raw)
        try:
            val = float(cleaned) if cleaned else None
            return val if val is not None and val >= 0 else None
        except ValueError:
            return None
    return None


def _normalize_date(raw_date: str) -> Optional[str]:
    """Parse and normalize date strings into ISO format YYYY-MM-DD."""
    if not raw_date:
        return None
    lowered = raw_date.strip().lower()
    if "today" in lowered:
        return date.today().isoformat()
    if "yesterday" in lowered:
        return (date.today() - timedelta(days=1)).isoformat()

    # Pattern: YYYY-MM-DD
    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw_date)
    if m_iso:
        return m_iso.group(1)

    # Pattern: DD-MM-YYYY or DD/MM/YYYY
    m_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", raw_date)
    if m_dmy:
        day, month, year = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    return None


def _rule_based_fallback_extraction(claim_text: str, target_field: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic rule-based extraction for fast, zero-dependency processing.
    """
    result: Dict[str, Any] = {}
    clean = claim_text.strip()
    lowered = clean.lower()

    # 1. Policy ID Extraction
    if target_field == "policy_id":
        m = re.search(r"(?:policy|policy\s*number|policy\s*id|number|it\s*is|is)?\s*[:#-]?\s*([a-zA-Z0-9\-_]{3,20})", clean, re.IGNORECASE)
        if m:
            val = m.group(1).strip("-#_ ").upper()
            if val not in COMMON_STOP_WORDS and len(val) >= 3:
                result["policy_id"] = val
        else:
            tokens = [t.strip(".,;:!") for t in clean.split()]
            for token in tokens:
                t_up = token.upper()
                if t_up not in COMMON_STOP_WORDS and len(t_up) >= 3 and any(c.isalnum() for c in t_up):
                    result["policy_id"] = t_up
                    break
    else:
        m_explicit = re.search(r"\b(?:policy|policy\s*number|policy\s*id|policy\s*#)\s*(?:is|:)?\s*([a-zA-Z0-9\-_]{3,20})\b", clean, re.IGNORECASE)
        if m_explicit:
            val = m_explicit.group(1).strip("-#_ ").upper()
            if val not in COMMON_STOP_WORDS:
                result["policy_id"] = val
        else:
            m_code = re.search(r"\b([A-Z]{2,6}[-_]?[0-9]{3,8})\b", clean, re.IGNORECASE)
            if m_code:
                result["policy_id"] = m_code.group(1).upper()

    # 2. Claimed Amount Extraction
    if target_field == "claimed_amount":
        amt = _coerce_amount(clean)
        if amt is not None and amt > 0:
            result["claimed_amount"] = amt
    else:
        m_amt = re.search(r"(?:cost|repair|damage|claimed|loss|estimate|amount|total|is|₹|rs\.?)\s*(?:is|of|around|about)?\s*[:]?\s*(\d+(?:[,\s]\d+)*(?:\.\d+)?)", clean, re.IGNORECASE)
        if m_amt:
            amt = _coerce_amount(m_amt.group(1))
            if amt is not None and amt > 0:
                result["claimed_amount"] = amt

    # 3. Claim Type Extraction
    m_type = re.search(r"\b(?:claim\s*type|type)\s*(?:is|:)?\s*(auto|home|business|car|vehicle|property)\b", lowered)
    if m_type:
        raw_t = m_type.group(1)
        result["claim_type"] = "auto" if raw_t in ("auto", "car", "vehicle") else ("home" if raw_t in ("home", "property") else "business")
    elif any(w in lowered for w in ("business", "commercial", "shop", "office", "store", "warehouse", "factory")):
        result["claim_type"] = "business"
    elif any(w in lowered for w in ("car", "auto", "vehicle", "motor", "bike", "truck", "collision", "accident", "crash", "driving")):
        result["claim_type"] = "auto"
    elif any(w in lowered for w in ("home", "house", "apartment", "property", "roof", "leak", "flood", "residence", "plumbing")):
        result["claim_type"] = "home"

    # 4. Incident Date Extraction
    norm_date = _normalize_date(clean)
    if norm_date:
        result["incident_date"] = norm_date

    # 5. Damage Description Extraction
    if target_field == "damage_description" and len(clean) >= 3:
        if clean.upper() not in COMMON_STOP_WORDS:
            result["damage_description"] = clean
    elif not target_field:
        if any(w in lowered for w in ("damage", "damaged", "hit", "accident", "crash", "broken", "leak", "flood", "dent", "loss", "scratch", "destroyed")):
            result["damage_description"] = clean

    return result


EXTRACTION_PROMPT = """Extract structured insurance claim information from the text below.
Return ONLY valid JSON with no markdown formatting and no extra text matching this schema:
{{
  "policy_id": "string or null",
  "incident_date": "YYYY-MM-DD or null",
  "claim_type": "auto|home|business or null",
  "damage_description": "string or null",
  "claimed_amount": number or null
}}

Rules:
1. claimed_amount must be a numeric value (not a string). If unknown, use null.
2. incident_date must be in ISO format YYYY-MM-DD.
3. If information is not explicitly provided in the text, use null. Do NOT hallucinate.

Target question context: "{target_field}"
Claim text: "{claim_text}"
"""


# ---------------------------------------------------------------------------
# Node 1: Claim Extractor
# ---------------------------------------------------------------------------
def claim_extractor(state: ClaimState) -> ClaimState:
    """
    Extract structured claim fields from raw user text using LLM with deterministic fallback.
    """
    if state.get("confirmed") or state.get("conversation_status") == "intake_complete":
        _audit(state, "claim_extractor skipped: claim intake already complete")
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
        logger.warning("claim_extractor LLM fallback active: %s", exc)
        extracted = {}

    fallback = _rule_based_fallback_extraction(raw_text, target_field)
    for k, v in fallback.items():
        if v is not None and (extracted.get(k) is None):
            extracted[k] = v

    if "claimed_amount" in extracted and extracted["claimed_amount"] is not None:
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
    state["extraction_confidence"] = non_null_required / float(len(REQUIRED_FIELDS))
    state["extracted_data"] = merged

    _audit(
        state,
        f"Extracted fields: {[k for k, v in merged.items() if v is not None]} "
        f"(confidence={state['extraction_confidence']:.0%})"
    )
    return state


# ---------------------------------------------------------------------------
# Node 2: Mandatory Field Checker
# ---------------------------------------------------------------------------
def mandatory_field_checker(state: ClaimState) -> ClaimState:
    """
    Check if all 5 mandatory fields are present.
    """
    data: Dict[str, Any] = state.get("extracted_data") or {}
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    state["missing_fields"] = missing

    ticket_id = state.get("ticket_id", "N/A")

    if not missing:
        state["awaiting_confirmation"] = True
        state["message"] = (
            f"All required fields received for ticket {ticket_id}. "
            "Please review and confirm your claim details."
        )
        _audit(state, "All mandatory fields present. Awaiting confirmation.")
    else:
        state["awaiting_confirmation"] = False
        next_prompt = FIELD_PROMPTS.get(missing[0], missing[0].replace("_", " "))
        state["message"] = (
            f"Claim details missing fields: {', '.join(missing)}. "
            f"Next question: {next_prompt}"
        )
        _audit(state, f"Missing fields: {missing}")

    return state


# ---------------------------------------------------------------------------
# Node 3: Conversational Turn Processor
# ---------------------------------------------------------------------------
def _detect_utterance_intent(text: str) -> str:
    """Classify user utterance into conversational control intents."""
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
    """
    Process conversational turn intents.
    """
    utterance = state.get("claim_text", "")
    state["last_user_utterance"] = utterance
    intent = _detect_utterance_intent(utterance)
    target_field = state.get("next_question_field")

    if intent == "repeat":
        _audit(state, f"User requested repeat. Re-emitting question for '{target_field}'.")
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


# ---------------------------------------------------------------------------
# Node 4: Next Question Generator
# ---------------------------------------------------------------------------
def next_question_generator(state: ClaimState) -> ClaimState:
    """
    Generate targeted voice prompt for the first missing required field.
    """
    if state.get("_skip_extraction") and state.get("next_question"):
        _audit(state, "Re-emitting previous question on repeat turn.")
        return state

    missing = state.get("missing_fields", [])
    if not missing:
        state["next_question"] = ""
        state["next_question_field"] = ""
        return state

    field = missing[0]
    state["next_question_field"] = field
    state["next_question"] = FIELD_PROMPTS.get(field, f"Could you provide your {field.replace('_', ' ')}?")
    state["conversation_status"] = "in_progress"
    _audit(state, f"Generated next question for '{field}': '{state['next_question']}'")
    return state


# ---------------------------------------------------------------------------
# Node 5: Intake Completion Marker
# ---------------------------------------------------------------------------
def intake_completion_marker(state: ClaimState) -> ClaimState:
    """
    Mark conversation intake as complete once all mandatory fields are collected.
    """
    ticket_id = state.get("ticket_id", "your claim")
    state["conversation_status"] = "intake_complete"
    state["next_question"] = (
        f"Thank you for providing all the required details. Your ticket ID is {ticket_id}. "
        "Your claim intake is complete and submitted for review."
    )
    state["next_question_field"] = ""
    _audit(state, f"Claim intake conversation complete for ticket {ticket_id}.")
    return state