"""
Review 1: Natural Conversational Claim Intake Graph Nodes.

Implements a human-like, empathetic voice insurance claim conversation:
1. Free-form narrative first: opens with an invitation to describe the incident naturally.
2. Complete multi-field semantic extraction from natural speech.
3. Six supported insurance types ONLY: Health, Senior Health, Home, Travel, Motor, Cyber.
4. Input quality gate rejecting filler words ("you", "uh"), noise, and pure greetings from becoming claim data.
5. Contextual conversational acknowledgements without robotic questionnaires.
6. Inquires ONLY for missing mandatory fields.
7. Flexible natural corrections across any field at any time.
8. Graceful "don't know" / deferral tracking.
9. Conversational confirmation summary and intake completion.
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

AFFIRMATION_MARKERS = (
    "yes", "yeah", "yep", "yup", "looks good", "correct", "confirm", "that's correct",
    "that is correct", "everything is correct", "all good", "sure", "ok", "okay",
    "proceed", "submit", "that's right", "thats right", "sounds good", "perfect", "it is correct",
)

REJECTION_MARKERS = (
    "no", "nope", "not right", "that's wrong", "thats wrong", "incorrect", "not correct",
    "mistake", "wait", "hold on",
)

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

# Common filler, greeting, or noise words that must NEVER become claim data
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


def _infer_insurance_type(text: str) -> Optional[str]:
    """
    Infer one of the six supported insurance types strictly:
    - health
    - senior_health
    - home
    - travel
    - motor
    - cyber
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

    # Direct keyword matches
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
    Extracts all possible fields present in the text simultaneously.
    Guarantees that generic words ("YOU", "HELLO", etc.) are NEVER extracted as policy IDs or values.
    """
    result: Dict[str, Any] = {}
    clean = claim_text.strip()

    # 1. Policy ID Extraction (Strict: requires explicit prefix or alphanumeric code with both letters and digits)
    m_explicit = re.search(
        r"\b(?:policy\s*number\s*(?:is|:)?|policy\s*id\s*(?:is|:)?|policy\s*#\s*(?:is|:)?|policy\s*(?:is|:)?)\s*[:#-]?\s*([A-Za-z0-9\-_]{3,20})\b",
        clean,
        re.IGNORECASE,
    )
    if m_explicit and m_explicit.group(1).upper() not in FILLER_OR_GREETING_WORDS:
        result["policy_id"] = m_explicit.group(1).strip("-#_ ").upper()
    else:
        # Match alphanumeric codes containing BOTH letters and digits (e.g., ABC12345, POL-9921)
        m_code = re.search(r"\b((?=[A-Za-z0-9\-_]*[A-Za-z])(?=[A-Za-z0-9\-_]*\d)[A-Za-z0-9\-_]{4,15})\b", clean)
        if m_code and m_code.group(1).upper() not in FILLER_OR_GREETING_WORDS:
            result["policy_id"] = m_code.group(1).upper()

    # 2. Claimed Amount Extraction
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

    # 3. Claim Type Extraction (Only 6 supported types: health, senior_health, home, travel, motor, cyber)
    inferred_type = _infer_insurance_type(clean)
    if inferred_type:
        result["claim_type"] = inferred_type

    # 4. Incident Date Extraction
    norm_date = _normalize_date(clean)
    if norm_date:
        result["incident_date"] = norm_date

    # 5. Damage / Incident Description Extraction
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
    words = set(re.findall(r"\b\w+\b", lowered))

    if any(m in lowered for m in REPEAT_MARKERS):
        return "repeat"
    if any(m in lowered for m in DONT_KNOW_MARKERS):
        return "dont_know"
    if any(m in lowered for m in DEFER_MARKERS):
        return "defer"
    if any(m in lowered for m in CORRECTION_MARKERS):
        return "correction"
    if any(m == lowered or m in words for m in AFFIRMATION_MARKERS):
        return "affirmation"
    if any(m == lowered or m in words for m in REJECTION_MARKERS):
        return "rejection"
    return "normal"


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    """
    Process conversational turn intents, filter low-quality input, and route.
    """
    utterance = state.get("claim_text", "").strip()
    state["last_user_utterance"] = utterance
    intent = _detect_utterance_intent(utterance)
    target_field = state.get("next_question_field")
    current_status = state.get("conversation_status", "not_started")

    # A. Handling Confirmation State
    if current_status == "confirming" or state.get("awaiting_confirmation"):
        if intent == "affirmation":
            ticket_id = state.get("ticket_id", "your claim")
            state["conversation_status"] = "intake_complete"
            state["confirmed"] = True
            state["awaiting_confirmation"] = False
            state["_rejection_active"] = False
            state["next_question"] = (
                f"Perfect! Your claim intake is complete under ticket {ticket_id}. "
                "Our claims team has received all your details."
            )
            state["next_question_field"] = ""
            state["_skip_extraction"] = True
            _audit(state, f"User confirmed claim summary. Intake sealed for ticket {ticket_id}.")
            return state

        if intent == "rejection":
            state["conversation_status"] = "collecting"
            state["awaiting_confirmation"] = False
            state["_rejection_active"] = True
            state["next_question"] = "No problem. What details should we correct?"
            state["_skip_extraction"] = True
            _audit(state, "User rejected confirmation; asking for corrections.")
            return state

        if intent in ("correction", "normal") or any(f in utterance.lower() for f in ("no", "change", "amount", "date", "policy", "type", "damage", "health", "motor", "travel", "home", "cyber")):
            target = _identify_field_from_utterance(utterance, fallback_field=None)
            if target:
                extracted = dict(state.get("extracted_data") or {})
                extracted[target] = None
                state["extracted_data"] = extracted
                _audit(state, f"User requested correction for '{target}' during confirmation.")
            state["_skip_extraction"] = False
            state["_rejection_active"] = False
            state["conversation_status"] = "collecting"
            state["awaiting_confirmation"] = False
            return state

    # B. Repeat Request
    if intent == "repeat":
        prev_q = state.get("next_question", INITIAL_PROMPT)
        state["next_question"] = f"Of course. {prev_q}"
        state["_skip_extraction"] = True
        _audit(state, "Politely re-emitting previous question on repeat request.")
        return state

    # C. Pure Greeting / Filler / Meaningless utterance handling
    tokens = [t.strip(".,!?:;\"'").upper() for t in utterance.split() if t.strip(".,!?:;\"'")]
    if tokens and all(t in FILLER_OR_GREETING_WORDS for t in tokens) and not any(re.search(r"\d", t) for t in tokens):
        # User said "hello", "hi", "ok", "you", etc. without any claim content
        state["_skip_extraction"] = True
        if any(t in {"HELLO", "HI", "HEY"} for t in tokens):
            state["next_question"] = "Hello! Please tell me what happened. Describe the incident in your own words, and I'll collect the details I need."
        else:
            state["next_question"] = "Sure. Please tell me what happened in your own words."
        _audit(state, f"Conversational greeting/filler filtered: '{utterance}'")
        return state

    # D. "Don't Know" / Deferral
    if intent in ("dont_know", "defer"):
        field = _identify_field_from_utterance(utterance, fallback_field=target_field)
        if field:
            field_status = dict(state.get("field_status") or {})
            field_status[field] = "deferred"
            state["field_status"] = field_status

            unknowns = list(state.get("unknown_fields") or [])
            if field not in unknowns:
                unknowns.append(field)
            state["unknown_fields"] = unknowns

            human_name = FIELD_HUMAN_NAMES.get(field, field.replace("_", " "))
            state["deferral_message"] = f"That's okay, we can leave the {human_name} for now."
            _audit(state, f"User deferred field '{field}'. Marked as deferred.")
            state["_skip_extraction"] = False
            return state

    # E. Correction Intent
    if intent == "correction":
        target = _identify_field_from_utterance(utterance, fallback_field=target_field)
        if target:
            prior = dict(state.get("extracted_data") or {})
            prior[target] = None
            state["extracted_data"] = prior
            field_status = dict(state.get("field_status") or {})
            field_status[target] = "missing"
            state["field_status"] = field_status
            state["next_question_field"] = target
            _audit(state, f"Identified correction for field '{target}'; unlocked for re-extraction.")

    state["_skip_extraction"] = False
    return state


# ---------------------------------------------------------------------------
# Node 2: Claim Extractor (Multi-field Semantic Extraction)
# ---------------------------------------------------------------------------
def claim_extractor(state: ClaimState) -> ClaimState:
    """
    Extract structured claim fields from raw user text using deterministic rules with LLM fallback.
    Extracts all possible fields present in free-form narration simultaneously.
    """
    if state.get("confirmed") or state.get("conversation_status") == "intake_complete":
        _audit(state, "claim_extractor skipped: claim intake already complete")
        return state

    raw_text = state.get("claim_text", "")
    target_field = state.get("next_question_field")
    sanitized_text = _sanitize_claim_text(raw_text)

    # Input quality gate: skip extraction on meaningless noise/single filler words
    if not _is_meaningful_claim_utterance(sanitized_text):
        _audit(state, "claim_extractor skipped: utterance does not meet minimum claim quality threshold")
        state["recently_extracted_fields"] = []
        return state

    # 1. Deterministic Extraction (instant, zero-latency)
    extracted = _rule_based_fallback_extraction(raw_text, target_field)

    # 2. LLM fallback if nothing extracted deterministically and text has substantive words
    if not any(extracted.values()) and len(sanitized_text.split()) >= 2:
        prompt = EXTRACTION_PROMPT.format(
            claim_text=sanitized_text,
            target_field=target_field or "general narration",
        )
        try:
            response = llm.invoke(prompt)
            content = response.content
            raw = content if isinstance(content, str) else str(content)
            raw = raw.strip()
            raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
            llm_extracted = json.loads(raw)
            for k, v in llm_extracted.items():
                if v is not None and extracted.get(k) is None:
                    # Sanitize LLM results against filler words
                    if k == "policy_id" and str(v).upper() in FILLER_OR_GREETING_WORDS:
                        continue
                    if k == "claim_type" and str(v).lower() not in VALID_CLAIM_TYPES:
                        continue
                    extracted[k] = v
        except Exception as exc:
            logger.warning("claim_extractor LLM invocation error: %s", exc)

    if "claimed_amount" in extracted and extracted["claimed_amount"] is not None:
        extracted["claimed_amount"] = _coerce_amount(extracted["claimed_amount"])

    # 3. Merge with prior extracted data and lock valid fields
    prior: Dict[str, Any] = dict(state.get("extracted_data") or {})
    locked_fields = {k for k, v in prior.items() if v is not None and v != UNKNOWN_SENTINEL}

    recently_captured: List[str] = []
    merged = {**prior}

    for k, v in extracted.items():
        if v is not None and v != UNKNOWN_SENTINEL:
            if k not in locked_fields or prior.get(k) is None:
                merged[k] = v
                recently_captured.append(k)

    state["recently_extracted_fields"] = recently_captured
    state["extracted_data"] = merged

    # Update field status mapping
    field_status = dict(state.get("field_status") or {})
    for f in REQUIRED_FIELDS:
        val = merged.get(f)
        if val is not None and val != UNKNOWN_SENTINEL:
            field_status[f] = "provided"
        elif field_status.get(f) != "deferred":
            field_status[f] = "missing"
    state["field_status"] = field_status

    provided_count = sum(1 for f in REQUIRED_FIELDS if field_status.get(f) == "provided")
    state["extraction_confidence"] = provided_count / float(len(REQUIRED_FIELDS))

    _audit(
        state,
        f"Extracted fields: {recently_captured} | Total provided: {provided_count}/5 "
        f"(confidence={state['extraction_confidence']:.0%})"
    )
    return state


# ---------------------------------------------------------------------------
# Node 3: Mandatory Field Checker & Confirmation Coordinator
# ---------------------------------------------------------------------------
def mandatory_field_checker(state: ClaimState) -> ClaimState:
    """
    Evaluate missing mandatory fields and coordinate transition between COLLECTING and CONFIRMING.
    """
    field_status: Dict[str, str] = state.get("field_status") or {}
    missing = [f for f in REQUIRED_FIELDS if field_status.get(f) != "provided"]
    state["missing_fields"] = missing

    ticket_id = state.get("ticket_id", "N/A")

    if state.get("_rejection_active"):
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "collecting"
        state["message"] = "Awaiting user corrections."
        return state

    if not missing:
        state["awaiting_confirmation"] = True
        if state.get("conversation_status") != "intake_complete":
            state["conversation_status"] = "confirming"
        state["message"] = f"All required details captured for ticket {ticket_id}. Ready for confirmation."
        _audit(state, "All 5 mandatory fields captured. Entering CONFIRMING state.")
    else:
        state["awaiting_confirmation"] = False
        if state.get("conversation_status") != "intake_complete":
            state["conversation_status"] = "collecting"
        state["message"] = f"Claim in progress ({len(missing)} fields remaining)."
        _audit(state, f"Missing fields remaining: {missing}")

    return state


# ---------------------------------------------------------------------------
# Node 4: Natural Conversational Response & Next Question Generator
# ---------------------------------------------------------------------------
def _build_natural_acknowledgement(state: ClaimState) -> str:
    """Build a natural, friendly acknowledgement for recently captured or corrected fields."""
    deferral_ack = state.get("deferral_message")
    if deferral_ack:
        return str(deferral_ack)

    recent = state.get("recently_extracted_fields") or []
    extracted = state.get("extracted_data") or {}

    if not recent:
        return ""

    if len(recent) == 1:
        field = recent[0]
        val = extracted.get(field)
        if field == "policy_id":
            return f"Thanks, I've got policy {val}."
        if field == "incident_date":
            return f"Got it, incident date {val}."
        if field == "claim_type":
            display_type = CLAIM_TYPE_DISPLAY.get(str(val).lower(), str(val).title())
            return f"Understood, this is a {display_type} claim."
        if field == "claimed_amount":
            return f"Thanks, recorded the estimate of ₹{val:,.0f}."
        if field == "damage_description":
            return "Thanks, I understand what happened and I've noted the incident details."

    parts = []
    if "damage_description" in recent or "claim_type" in recent:
        parts.append("the incident details")
    if "incident_date" in recent:
        parts.append(f"date {extracted.get('incident_date')}")
    if "policy_id" in recent:
        parts.append(f"policy {extracted.get('policy_id')}")
    if "claimed_amount" in recent:
        parts.append(f"the estimate of ₹{extracted.get('claimed_amount'):,.0f}")

    if parts:
        ack_body = ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]
        return f"Thanks, I've recorded {ack_body}."

    return "Thank you."


def _build_confirmation_summary(state: ClaimState) -> str:
    """Construct a clean, human-like confirmation summary for the claimant."""
    extracted = state.get("extracted_data") or {}
    policy_id = extracted.get("policy_id", "N/A")
    incident_date = extracted.get("incident_date", "N/A")
    raw_type = str(extracted.get("claim_type", "motor")).lower().replace(" ", "_")
    claim_type = CLAIM_TYPE_DISPLAY.get(raw_type, raw_type.replace("_", " ").title())
    description = extracted.get("damage_description", "incident reported")
    amount = extracted.get("claimed_amount", 0.0)

    ack = _build_natural_acknowledgement(state)
    prefix = f"{ack} " if ack else ""

    return (
        f"{prefix}Let me make sure I have everything right. You are reporting a {claim_type} incident on {incident_date}, "
        f"your policy number is {policy_id}, the incident description is {description}, "
        f"and you estimate the loss at ₹{amount:,.0f}. Does everything look correct?"
    )


def next_question_generator(state: ClaimState) -> ClaimState:
    """
    Generate the user-facing natural conversational response.
    """
    if state.get("_skip_extraction") and state.get("next_question"):
        _audit(state, "Emitting active question on control turn.")
        return state

    status = state.get("conversation_status")

    # 1. State: Intake Complete
    if status == "intake_complete":
        ticket_id = state.get("ticket_id", "your claim")
        state["next_question"] = (
            f"Perfect! Your claim intake is complete under ticket {ticket_id}. "
            "Our claims team has received all your details."
        )
        state["next_question_field"] = ""
        _audit(state, f"Intake completed response set for ticket {ticket_id}.")
        return state

    # 2. State: Confirming (All fields provided)
    if status == "confirming" or state.get("awaiting_confirmation"):
        state["next_question"] = _build_confirmation_summary(state)
        state["next_question_field"] = ""
        _audit(state, "Generated confirmation summary prompt.")
        return state

    # 3. State: Collecting (Missing fields remain)
    missing = state.get("missing_fields") or []
    if not missing:
        state["conversation_status"] = "confirming"
        state["awaiting_confirmation"] = True
        state["next_question"] = _build_confirmation_summary(state)
        state["next_question_field"] = ""
        return state

    # If no fields have been extracted yet and user hasn't provided details, open with free-form prompt
    if len(missing) == len(REQUIRED_FIELDS) and not state.get("recently_extracted_fields"):
        state["next_question"] = INITIAL_PROMPT
        state["next_question_field"] = ""
        state["conversation_status"] = "collecting"
        return state

    next_field = missing[0]
    state["next_question_field"] = next_field

    ack = _build_natural_acknowledgement(state)
    question = FIELD_NATURAL_QUESTIONS.get(next_field, f"Could you provide your {next_field.replace('_', ' ')}?")

    full_response = f"{ack} {question}".strip() if ack else question

    state["next_question"] = full_response
    state["conversation_status"] = "collecting"
    _audit(state, f"Generated next question for '{next_field}': '{full_response}'")
    return state


# ---------------------------------------------------------------------------
# Node 5: Intake Completion Marker
# ---------------------------------------------------------------------------
def intake_completion_marker(state: ClaimState) -> ClaimState:
    """
    Mark intake complete when user confirms.
    """
    ticket_id = state.get("ticket_id", "your claim")
    state["conversation_status"] = "intake_complete"
    state["confirmed"] = True
    state["awaiting_confirmation"] = False
    state["next_question"] = (
        f"Perfect! Your claim intake is complete under ticket {ticket_id}. "
        "Our claims team has received all your details."
    )
    state["next_question_field"] = ""
    _audit(state, f"Claim intake sealed for ticket {ticket_id}.")
    return state