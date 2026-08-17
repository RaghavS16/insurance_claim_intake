"""
Phase 1: Voice-First Conversational Claim Intake Graph Nodes.
"""
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langchain_ollama import ChatOllama

from src.config import settings
from src.agents.state import ClaimState
from src.utils.logger import app_logger

logger = app_logger

llm = ChatOllama(
    base_url=settings.OLLAMA_BASE_URL,
    model=settings.OLLAMA_MODEL,
    temperature=0,
    timeout=10,
)

REQUIRED_FIELDS = ["policy_id", "incident_date", "claim_type", "damage_description", "claimed_amount"]

INITIAL_PROMPT = "Please tell me what happened. Describe the incident in your own words, and I'll collect the details I need."

FIELD_HUMAN_NAMES = {
    "policy_id": "policy number",
    "incident_date": "incident date",
    "claim_type": "insurance type",
    "damage_description": "incident description",
    "claimed_amount": "estimated loss or damage cost",
}

FIELD_NATURAL_QUESTIONS = {
    "policy_id": "Could you provide your policy number?",
    "incident_date": "When did the incident happen?",
    "claim_type": "What type of insurance policy is this for (Health, Senior Health, Home, Travel, Motor, or Cyber)?",
    "damage_description": "Can you describe what happened and the damage or loss caused?",
    "claimed_amount": "About how much do you estimate the cost or loss will be?",
}

CLAIM_TYPE_DISPLAY = {
    "health": "Health",
    "senior_health": "Senior Health",
    "home": "Home",
    "travel": "Travel",
    "motor": "Motor",
    "cyber": "Cyber",
}

VALID_CLAIM_TYPES = {"health", "senior_health", "home", "travel", "motor", "cyber"}

UNKNOWN_SENTINEL = "UNKNOWN"

REPEAT_MARKERS = (
    "repeat that", "say that again", "come again", "what was that", "pardon",
    "repeat", "what?", "sorry?", "i didn't hear", "didn't catch that", "say again",
    "can you repeat", "could you repeat",
)

DONT_KNOW_MARKERS = (
    "i don't know", "i dont know", "not sure", "no idea", "i'll check",
    "dont know", "i do not know", "i don't have", "dont have", "can't say",
    "cant say", "no estimate", "unsure",
)

DEFER_MARKERS = (
    "i'll provide it later", "later", "not right now", "i'll get back to you",
    "skip", "pass", "leave it for now", "we can skip", "provide later",
)

CORRECTION_MARKERS = (
    "actually", "sorry, i meant", "i meant to say", "no wait", "correction",
    "let me correct", "scratch that", "i said that wrong", "mistake", "change that to",
    "change the", "make the", "the amount is actually", "the date should be",
    "my policy is actually", "no, the", "no, make", "no, it",
)

AFFIRMATION_PHRASES = (
    "looks good", "that's correct", "that is correct", "everything is correct",
    "all good", "sounds good", "everything looks good", "thats right", "that's right",
    "it is correct",
)

AFFIRMATION_WORDS = {"yes", "yeah", "yep", "yup", "correct", "confirm", "sure", "ok", "okay", "proceed", "submit", "perfect"}

REJECTION_PHRASES = ("that's wrong", "thats wrong", "not right", "not correct", "hold on")
REJECTION_WORDS = {"no", "nope", "incorrect", "wrong", "mistake"}

FILLER_OR_GREETING_WORDS = {
    "YOU", "HELLO", "HI", "HEY", "GOOD", "MORNING", "AFTERNOON", "EVENING",
    "UH", "UM", "AH", "ER", "HMM", "YEAH", "YES", "NO", "OKAY", "OK",
    "SURE", "THANKS", "THANK", "PLEASE", "RIGHT", "WELL", "LIKE", "SO",
    "MY", "THE", "IS", "IT", "ITS", "WAS", "FOR", "AND", "A", "AN",
    "NUMBER", "POLICY", "OF", "IN", "AT", "ON", "WITH"
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def _sanitize_claim_text(text: str) -> str:
    if not text:
        return ""
    clean = text.replace("\x00", "").strip()
    clean = clean.replace("{", "{{").replace("}", "}}")
    return clean[:5000]


def _is_meaningful_claim_utterance(text: str) -> bool:
    """
    Quality gate: check if text contains meaningful words rather than
    single filler words, noise bursts, or greetings.
    """
    if not text or len(text.strip()) < 2:
        return False
    tokens = [t.strip(".,!?:;\"'").upper() for t in text.split() if t.strip(".,!?:;\"'")]
    if not tokens:
        return False
    has_non_filler = any(t not in FILLER_OR_GREETING_WORDS for t in tokens)
    has_digits = any(re.search(r"\d", t) for t in tokens)
    return has_non_filler or has_digits


def _coerce_amount(raw: Any) -> Optional[float]:
    """Safely coerce any numeric or currency representation to a float amount."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None
    if isinstance(raw, str):
        clean_str = raw.lower().replace("k", "000")
        match = re.search(r"(\d+(?:[,\s]\d+)*(?:\.\d+)?)", clean_str)
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

    m_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw_date)
    if m_iso:
        return m_iso.group(1)

    m_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", raw_date)
    if m_dmy:
        day, month, year = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    return None


def _infer_insurance_type(text: str) -> Optional[str]:
    """
    Infer one of the six supported insurance types strictly:
    - health, senior_health, home, travel, motor, cyber
    """
    lowered = text.lower()

    # 1. Cyber
    if any(w in lowered for w in ("hack", "hacked", "cyber", "ransomware", "phishing", "data breach", "malware", "virus", "server compromised", "online fraud", "identity theft")):
        return "cyber"

    # 2. Travel
    if any(w in lowered for w in ("luggage", "travel", "travelling", "traveling", "flight", "trip", "vacation", "airline", "baggage", "passport", "hotel", "airport", "tour", "abroad", "lost bag", "flight delayed")):
        return "travel"

    # 3. Senior Health vs Health
    health_cues = ("hospital", "hospitalized", "hospitalisation", "hospitalization", "surgery", "medical", "doctor", "illness", "treatment", "clinic", "health", "injury", "icu", "mediclaim", "admitted", "disease", "fracture")
    senior_cues = ("father", "mother", "parents", "parent", "senior", "elderly", "grandfather", "grandmother", "pensioner", "aged", "old age", "senior citizen", "grandma", "grandpa", "dad", "mom")

    if any(w in lowered for w in ("senior health", "senior citizen health", "senior citizen medical")):
        return "senior_health"

    if any(h in lowered for h in health_cues):
        if any(s in lowered for s in senior_cues):
            return "senior_health"
        return "health"

    # 4. Motor
    if any(w in lowered for w in ("car", "motor", "vehicle", "bike", "truck", "scooter", "driving", "bumper", "windshield", "collision", "hit from behind", "accident on road", "traffic accident", "fender", "dent")):
        return "motor"

    # 5. Home
    if any(w in lowered for w in ("home", "house", "apartment", "roof", "leak", "flood", "residence", "plumbing", "fire in house", "property damage", "burglary", "pipe burst", "kitchen fire")):
        return "home"

    for t in ("senior_health", "health", "home", "travel", "motor", "cyber"):
        if t in lowered or t.replace("_", " ") in lowered:
            return t

    return None


def _identify_field_from_utterance(text: str, fallback_field: Optional[str] = None) -> Optional[str]:
    """Identify which claim field a user is referring to in a correction or deferral."""
    lowered = text.lower()
    if any(w in lowered for w in ("amount", "cost", "rupees", "rs", "price", "estimate", "quote", "bill")):
        return "claimed_amount"
    if any(w in lowered for w in ("policy", "policy number", "policy id", "policy #")):
        return "policy_id"
    if any(w in lowered for w in ("date", "incident date", "happened on", "occurred on", "yesterday", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")):
        return "incident_date"
    if any(w in lowered for w in ("insurance type", "claim type", "health", "senior health", "home", "travel", "motor", "cyber")):
        return "claim_type"
    if any(w in lowered for w in ("damage", "description", "details", "hit", "crash", "collision", "bumper", "hospital", "luggage", "hacked", "fire", "accident")):
        return "damage_description"
    return fallback_field


def _rule_based_fallback_extraction(claim_text: str, target_field: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic rule-based extraction for fast, zero-dependency processing.
    """
    result: Dict[str, Any] = {}
    clean = claim_text.strip()

    # 1. Policy ID
    m_explicit = re.search(
        r"\b(?:policy\s*number\s*(?:is|:)?|policy\s*id\s*(?:is|:)?|policy\s*#\s*(?:is|:)?|policy\s*(?:is|:)?)\s*[:#-]?\s*([A-Za-z0-9\-_]{3,20})\b",
        clean,
        re.IGNORECASE,
    )
    if m_explicit and m_explicit.group(1).upper() not in FILLER_OR_GREETING_WORDS:
        result["policy_id"] = m_explicit.group(1).strip("-#_ ").upper()
    else:
        m_code = re.search(r"\b((?=[A-Za-z0-9\-_]*[A-Za-z])(?=[A-Za-z0-9\-_]*\d)[A-Za-z0-9\-_]{4,15})\b", clean)
        if m_code and m_code.group(1).upper() not in FILLER_OR_GREETING_WORDS:
            result["policy_id"] = m_code.group(1).upper()

    # 2. Claimed Amount
    if target_field == "claimed_amount":
        amt = _coerce_amount(clean)
        if amt is not None and amt > 0:
            result["claimed_amount"] = amt
    else:
        m_amt = re.search(
            r"(?:cost|repair|damage|claimed|loss|estimate|amount|total|bill|worth|value|around|about|₹|rs\.?)\s*(?:is|of|around|about)?\s*[:]?\s*(\d+(?:[,\s]\d+)*(?:\.\d+)?)",
            clean,
            re.IGNORECASE,
        )
        if m_amt:
            amt = _coerce_amount(m_amt.group(1))
            if amt is not None and amt > 0:
                result["claimed_amount"] = amt
        else:
            m_currency = re.search(r"(\d+(?:[,\s]\d+)*(?:\.\d+)?)\s*(?:rupees|rs\.?|inr|usd|\$)", clean, re.IGNORECASE)
            if m_currency:
                amt = _coerce_amount(m_currency.group(1))
                if amt is not None and amt > 0:
                    result["claimed_amount"] = amt

    # 3. Claim Type
    inferred_type = _infer_insurance_type(clean)
    if inferred_type:
        result["claim_type"] = inferred_type

    # 4. Incident Date
    norm_date = _normalize_date(clean)
    if norm_date:
        result["incident_date"] = norm_date

    # 5. Damage Description
    if target_field == "damage_description" and len(clean) >= 3:
        if clean.upper() not in FILLER_OR_GREETING_WORDS:
            result["damage_description"] = clean
    elif any(w in clean.lower() for w in ("damage", "damaged", "hit", "accident", "crash", "broken", "leak", "flood", "dent", "loss", "scratch", "destroyed", "bumper", "hospital", "luggage", "hacked", "fire", "stolen", "surgery", "injured")):
        if clean.upper() not in FILLER_OR_GREETING_WORDS:
            result["damage_description"] = clean

    return result


EXTRACTION_PROMPT = """Extract structured insurance claim information from the user utterance.
Our supported insurance types are ONLY: health, senior_health, home, travel, motor, cyber.
Return ONLY valid JSON matching this schema:
{{
  "policy_id": "string or null",
  "incident_date": "YYYY-MM-DD or null",
  "claim_type": "health|senior_health|home|travel|motor|cyber or null",
  "damage_description": "string or null",
  "claimed_amount": number or null
}}

Rules:
1. claim_type MUST be one of: health, senior_health, home, travel, motor, cyber. Do NOT use auto, car, or business.
2. claimed_amount must be a numeric value (not a string).
3. incident_date must be in ISO format YYYY-MM-DD. Convert 'yesterday' or 'today' relative to current context.
4. Do NOT extract generic words (e.g. 'YOU', 'HELLO', 'YES', 'OKAY') as policy IDs.

Current context question: "{target_field}"
User utterance: "{claim_text}"
"""


# ---------------------------------------------------------------------------
# Node 1: Intent & Turn Preprocessor
# ---------------------------------------------------------------------------
def _detect_utterance_intent(text: str) -> str:
    """Classify user utterance into conversational control intents."""
    lowered = text.lower().strip()
    if not lowered:
        return "empty"

    if any(m in lowered for m in REPEAT_MARKERS):
        return "repeat"

    if any(m in lowered for m in CORRECTION_MARKERS):
        return "correction"

    if any(m in lowered for m in DONT_KNOW_MARKERS) or any(m in lowered for m in DEFER_MARKERS):
        return "defer"

    words = set(re.findall(r"\b\w+\b", lowered))

    # Check rejection BEFORE affirmation so "incorrect" is rejected
    if any(p in lowered for p in REJECTION_PHRASES) or bool(words & REJECTION_WORDS):
        return "rejection"

    if any(p in lowered for p in AFFIRMATION_PHRASES) or bool(words & AFFIRMATION_WORDS):
        return "affirmation"

    return "normal"


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    """
    Evaluates conversational intent and updates conversation state machine.
    """
    raw_text = state.get("claim_text", "").strip()
    state["last_user_utterance"] = raw_text
    state["turn_number"] = state.get("turn_number", 0) + 1
    state.setdefault("conversation_history", [])
    state.setdefault("extracted_data", {})
    state.setdefault("field_status", {})
    state.setdefault("unknown_fields", [])
    state["_skip_extraction"] = False
    state["deferral_message"] = None

    if not raw_text:
        state["_skip_extraction"] = True
        return state

    state["conversation_history"].append({
        "turn": state["turn_number"],
        "speaker": "user",
        "text": raw_text,
    })

    intent = _detect_utterance_intent(raw_text)
    target_field = state.get("next_question_field")
    awaiting_conf = state.get("awaiting_confirmation", False)

    # 1. User in confirmation state
    if awaiting_conf:
        if intent == "affirmation":
            state["confirmed"] = True
            state["awaiting_confirmation"] = False
            state["conversation_status"] = "intake_complete"
            state["_skip_extraction"] = True
            _audit(state, "Claimant confirmed all extracted intake details.")
            return state

        if intent in ("rejection", "correction"):
            state["awaiting_confirmation"] = False
            state["confirmed"] = False
            state["conversation_status"] = "collecting"
            state["_rejection_active"] = True
            _audit(state, f"Claimant initiated correction during confirmation: '{raw_text}'")
            return state

    # 2. Repeat intent
    if intent == "repeat":
        state["_skip_extraction"] = True
        _audit(state, "Claimant requested repeat of previous prompt.")
        return state

    # 3. Defer intent
    if intent == "defer":
        target = _identify_field_from_utterance(raw_text, fallback_field=target_field)
        if target:
            state["field_status"][target] = "deferred"
            state["extracted_data"][target] = UNKNOWN_SENTINEL
            if target not in state["unknown_fields"]:
                state["unknown_fields"].append(target)
            state["deferral_message"] = f"No problem, we can provide the {FIELD_HUMAN_NAMES.get(target, target)} later."
            state["_skip_extraction"] = True
            _audit(state, f"Claimant deferred field '{target}'.")
            return state

    return state


# ---------------------------------------------------------------------------
# Node 2: Multi-Field Semantic Extractor
# ---------------------------------------------------------------------------
def claim_extractor(state: ClaimState) -> ClaimState:
    """
    Extracts structured fields from user utterance using LLM with deterministic fallback.
    Applies quality gate to filter out filler noise.
    """
    claim_text = state.get("claim_text", "")
    target_field = state.get("next_question_field")
    data: Dict[str, Any] = dict(state.get("extracted_data") or {})
    field_status: Dict[str, str] = dict(state.get("field_status") or {})
    recently_extracted: List[str] = []

    if not _is_meaningful_claim_utterance(claim_text):
        _audit(state, "Utterance did not pass input quality gate (filler/noise/greeting).")
        state["recently_extracted_fields"] = []
        return state

    heuristic = _rule_based_fallback_extraction(claim_text, target_field=target_field)

    llm_extracted: Dict[str, Any] = {}
    try:
        sanitized_text = _sanitize_claim_text(claim_text)
        prompt = EXTRACTION_PROMPT.format(
            target_field=target_field or "None",
            claim_text=sanitized_text,
        )
        resp = llm.invoke(prompt)
        raw_content = getattr(resp, "content", resp)
        content = " ".join(str(c) for c in raw_content) if isinstance(raw_content, list) else str(raw_content)
        m_json = re.search(r"\{.*\}", content, re.DOTALL)
        if m_json:
            parsed = json.loads(m_json.group(0))
            if isinstance(parsed, dict):
                llm_extracted = parsed
    except Exception as exc:
        logger.debug("LLM extraction unavailable (%s), using rule-based extraction.", exc)

    merged: Dict[str, Any] = {}

    # Policy ID
    pol_id = heuristic.get("policy_id") or llm_extracted.get("policy_id")
    if pol_id and isinstance(pol_id, str):
        clean_pol = pol_id.strip().upper()
        if clean_pol not in FILLER_OR_GREETING_WORDS and len(clean_pol) >= 3:
            merged["policy_id"] = clean_pol

    # Incident Date
    inc_date = heuristic.get("incident_date") or _normalize_date(str(llm_extracted.get("incident_date", "")))
    if inc_date:
        merged["incident_date"] = inc_date

    # Claim Type
    ctype = heuristic.get("claim_type") or llm_extracted.get("claim_type")
    if ctype and str(ctype).lower() in VALID_CLAIM_TYPES:
        merged["claim_type"] = str(ctype).lower()

    # Damage Description
    desc = heuristic.get("damage_description") or llm_extracted.get("damage_description")
    if desc and isinstance(desc, str) and len(desc.strip()) >= 3:
        if desc.strip().upper() not in FILLER_OR_GREETING_WORDS:
            merged["damage_description"] = desc.strip()

    # Claimed Amount
    amt = heuristic.get("claimed_amount") or _coerce_amount(llm_extracted.get("claimed_amount"))
    if amt is not None and amt > 0:
        merged["claimed_amount"] = amt

    for k, v in merged.items():
        if v is not None and v != UNKNOWN_SENTINEL:
            old_val = data.get(k)
            data[k] = v
            field_status[k] = "provided"
            recently_extracted.append(k)
            if old_val and old_val != v:
                _audit(state, f"Corrected field '{k}': '{old_val}' -> '{v}'")
            else:
                _audit(state, f"Extracted field '{k}': '{v}'")

    state["extracted_data"] = data
    state["field_status"] = field_status
    state["recently_extracted_fields"] = recently_extracted
    return state


# ---------------------------------------------------------------------------
# Node 3: Mandatory Field Checker
# ---------------------------------------------------------------------------
def mandatory_field_checker(state: ClaimState) -> ClaimState:
    """
    Evaluates required fields and computes extraction confidence.
    """
    data = state.get("extracted_data") or {}
    field_status = state.get("field_status") or {}
    unknowns = set(state.get("unknown_fields") or [])

    missing: List[str] = []
    for f in REQUIRED_FIELDS:
        val = data.get(f)
        if val is None or val == "" or val == UNKNOWN_SENTINEL:
            if f not in unknowns:
                missing.append(f)
                field_status[f] = "missing"
        else:
            field_status[f] = "provided"

    provided_count = len([f for f in REQUIRED_FIELDS if f not in missing])
    state["extraction_confidence"] = round(provided_count / len(REQUIRED_FIELDS), 2)
    state["missing_fields"] = missing
    state["field_status"] = field_status

    if state.get("confirmed"):
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "intake_complete"
    elif not missing:
        state["awaiting_confirmation"] = True
        state["conversation_status"] = "confirming"
    else:
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "collecting"

    return state


# ---------------------------------------------------------------------------
# Node 4: Dynamic Next Question & Response Generator
# ---------------------------------------------------------------------------
def next_question_generator(state: ClaimState) -> ClaimState:
    """
    Generates natural, empathetic voice prompts:
    - Contextual acknowledgements of newly received fields
    - Direct, friendly questions for missing fields
    - Structured confirmation prompt before final submission
    - Final intake completion message
    """
    # 1. Intake complete
    if state.get("confirmed"):
        summary = _build_confirmation_summary(state.get("extracted_data", {}))
        msg = f"Thank you! Your claim details have been confirmed and recorded.\n{summary}"
        state["next_question"] = msg
        state["next_question_field"] = ""
        state["message"] = msg
        return state

    # 2. Awaiting confirmation
    if state.get("awaiting_confirmation"):
        summary = _build_confirmation_summary(state.get("extracted_data", {}))
        msg = (
            f"I have collected all the basic details for your claim:\n{summary}\n"
            "Does everything look correct? Please say yes to confirm and submit, or let me know if you would like to change anything."
        )
        state["next_question"] = msg
        state["next_question_field"] = "confirmation"
        state["message"] = msg
        return state

    # 3. Missing fields follow-up
    missing = state.get("missing_fields", [])
    if not missing:
        state["next_question"] = INITIAL_PROMPT
        state["next_question_field"] = ""
        state["message"] = INITIAL_PROMPT
        return state

    if len(missing) == len(REQUIRED_FIELDS) and not state.get("extracted_data"):
        state["next_question"] = INITIAL_PROMPT
        state["next_question_field"] = "claim_type"
        state["message"] = INITIAL_PROMPT
        return state

    next_field = missing[0]
    state["next_question_field"] = next_field

    ack_prefix = ""
    deferral_msg = state.get("deferral_message")
    if deferral_msg:
        ack_prefix = f"{deferral_msg} "
    else:
        recent = state.get("recently_extracted_fields", [])
        if recent:
            first_ack = recent[0]
            ack_val = state.get("extracted_data", {}).get(first_ack)
            if first_ack == "claim_type" and ack_val:
                disp = CLAIM_TYPE_DISPLAY.get(str(ack_val), str(ack_val).title())
                ack_prefix = f"Got it, a {disp} insurance claim. "
            elif first_ack == "incident_date" and ack_val:
                ack_prefix = f"Thank you. "
            elif first_ack == "policy_id" and ack_val:
                ack_prefix = f"Got your policy number {ack_val}. "
            elif first_ack == "claimed_amount" and ack_val:
                ack_prefix = f"Understood, estimated at {ack_val}. "
            else:
                ack_prefix = "Thank you. "

    question = FIELD_NATURAL_QUESTIONS.get(next_field, f"Could you please provide the {FIELD_HUMAN_NAMES.get(next_field, next_field)}?")
    full_prompt = f"{ack_prefix}{question}".strip()

    state["next_question"] = full_prompt
    state["message"] = full_prompt
    return state


def _build_confirmation_summary(data: Dict[str, Any]) -> str:
    """Generate a clean human-readable summary of collected claim fields."""
    ctype_raw = data.get("claim_type", "")
    ctype_disp = CLAIM_TYPE_DISPLAY.get(ctype_raw, str(ctype_raw).title() if ctype_raw else "Not specified")
    pol_id = data.get("policy_id", "Not provided")
    date_val = data.get("incident_date", "Not provided")
    desc = data.get("damage_description", "Not provided")
    amt_val = data.get("claimed_amount")
    amt_disp = f"₹{amt_val:,.2f}" if isinstance(amt_val, (int, float)) else str(amt_val or "Not provided")

    return (
        f"• Insurance Type: {ctype_disp}\n"
        f"• Policy ID: {pol_id}\n"
        f"• Incident Date: {date_val}\n"
        f"• Incident Details: {desc}\n"
        f"• Estimated Amount: {amt_disp}"
    )