"""Production-oriented claim conversation engine.

The domain state is authoritative. Deterministic extraction handles high-risk
scalar fields while the LLM interprets conversational intent and incident
narrative. The assistant should collect multiple facts from natural speech,
ignore social chatter, confirm the complete baseline once, and never treat an
arbitrary utterance as an incident description.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.agents.constants import COMMON_REQUIRED_FIELDS, INSURANCE_TYPE_KEYS, SUPPORTED_INSURANCE_TYPES
from src.agents.llm_factory import get_configured_llm
from src.agents.state import ClaimState
from src.utils.logger import app_logger

logger = app_logger
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = get_configured_llm()
    return _llm


T = TypeVar("T", bound=BaseModel)
REQUIRED_FIELDS = list(COMMON_REQUIRED_FIELDS)
UNKNOWN_SENTINEL = "UNKNOWN"
IntentType = Literal[
    "claim_detail", "correction", "confirmation", "rejection", "question",
    "repeat", "defer", "filler", "greeting", "gratitude", "closing",
    "escalation", "unclear"
]


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: Literal[
        "policy_id", "event_date", "insurance_type", "event_description",
        "event_location", "estimated_claim_amount"
    ]
    operation: Literal["set", "replace", "append", "remove", "ignore"]
    value: Any = None
    evidence: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractionPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intent: IntentType
    changes: List[FieldChange] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification: str = ""
    spoken_reply: str = ""


SYSTEM_PROMPT = """You are the semantic layer for an insurance claim intake assistant.
Interpret ONLY the latest claimant utterance, using prior conversation only to resolve references.
The conversation is natural language, not a form. A claimant may greet you, thank you, ask a general question,
correct a field, or provide several claim facts in one sentence.

Rules:
1. Extract every independently supported fact from the latest utterance. Never invent facts.
2. Do not force every utterance into event_description. event_description is ONLY the actual incident narrative.
3. Short social utterances such as hello, thanks, okay, great, bye, or acknowledgements must not modify claim data.
4. Questions about the process must not modify claim data.
5. When the user provides corrections, replace ONLY the corrected field.
6. When the user gives additional incident facts that clearly belong to the same incident, append only the new narrative detail.
7. For confirmation/rejection, do not create facts unless the same utterance explicitly corrects something.
8. A policy identifier should normally contain digits. Never turn words like 'idea', 'number', 'id', or 'my policy' into a policy value.
9. For event_description, exclude policy identifiers, dates, locations, amounts, greetings, and assistant text.
10. Prefer concise semantic changes over copying the utterance wholesale.
spoken_reply is advisory only; the application constructs the final assistant response from verified state.
"""
_GENERIC_POLICY_WORDS = {"IDEA", "ID", "NUMBER", "NO", "IS", "MY", "POLICY", "TYPE", "THE", "A"}
_SOCIAL_EXACT = {
    "hi", "hello", "hey", "thanks", "thank you", "thx", "bye", "goodbye",
    "ok", "okay", "great", "fine", "perfect", "sure", "got it", "alright",
    "all right", "yes", "yeah", "yep", "no", "nope"
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def _invoke_structured(model: Any, prompt: str, schema: type[T]) -> Optional[T]:
    try:
        result = model.with_structured_output(schema).invoke(prompt)
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema.model_validate(result)
    except Exception as exc:
        logger.warning("Structured extraction failed: %s", exc)
    return None


def _history_text(state: ClaimState, limit: int = 8) -> str:
    history = state.get("conversation_history", [])[-limit:]
    return "\n".join(
        f"{h.get('speaker', 'unknown')}: {h.get('text', '')}"
        for h in history
    ) or "No previous turns."


def _safe_date(raw: Any, reference: date) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().lower().replace(",", "")
    aliases = {
        "today": reference,
        "this day": reference,
        "yesterday": reference - timedelta(days=1),
        "the day before": reference - timedelta(days=1),
        "day before yesterday": reference - timedelta(days=2),
        "tomorrow": reference + timedelta(days=1),
        "the next day": reference + timedelta(days=1),
    }
    if text in aliases:
        return aliases[text].isoformat()
    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y",
        "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _deterministic_date(text: str, reference: date) -> Optional[str]:
    low = text.lower()
    if re.search(r"\bday before yesterday\b", low):
        return (reference - timedelta(days=2)).isoformat()
    if re.search(r"\b(yesterday\s+(?:morning|afternoon|evening)|yesterday|the day before)\b", low):
        return (reference - timedelta(days=1)).isoformat()
    if re.search(r"\b(this\s+(?:morning|afternoon|evening|day)|today\s+(?:morning|afternoon|evening)|today|earlier today|just now)\b", low):
        return reference.isoformat()
    if re.search(r"\b(tomorrow|the next day)\b", low):
        return (reference + timedelta(days=1)).isoformat()
    for pattern in (
        r"\b(\d{4}-\d{1,2}-\d{1,2})\b",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b",
        r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b",
        r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\s+\d{4})\b",
    ):
        match = re.search(pattern, low)
        if match:
            normalized = _safe_date(match.group(1), reference)
            if normalized:
                return normalized
    return None


def _parse_indian_amount(text: str) -> Optional[float]:
    s = text.lower().replace(",", "").replace("₹", " ").strip()
    match = re.search(
        r"(?:rs\.?|inr|rupees?)?\s*(\d+(?:\.\d+)?)\s*"
        r"(crore|crores|cr|lakh|lakhs|lac|lacs|k|thousand)?\b",
        s,
    )
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or ""
    return value * {
        "k": 1000, "thousand": 1000,
        "lakh": 100000, "lakhs": 100000,
        "lac": 100000, "lacs": 100000,
        "crore": 10000000, "crores": 10000000, "cr": 10000000,
    }.get(unit, 1)


def _safe_amount(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None
    return _parse_indian_amount(str(raw))


def _deterministic_amount(text: str) -> Optional[float]:
    low = text.lower()
    for pattern in (
        r"(?:₹|rs\.?|inr|rupees?|repair\s+cost|repair|damage|loss|estimated\s+(?:cost|loss)|claim|cost|bill|worth)"
        r"[^\d]{0,25}(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|k|thousand)?\b",
        r"(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|k|thousand)\b",
    ):
        match = re.search(pattern, low)
        if match:
            return _safe_amount(" ".join(part for part in match.groups() if part))
    return None


def _deterministic_type(text: str) -> Optional[str]:
    low = text.lower()
    if re.search(r"\b(senior|elderly|pensioner)\b", low) and re.search(r"\b(hospital|medical|treatment|surgery|illness|doctor)\b", low):
        return "senior_health"
    if re.search(r"\b(bike|bicycle|motorcycle|scooter|car|vehicle|auto|collision|crash|road accident)\b", low):
        return "motor"
    if re.search(r"\b(luggage|baggage|flight|trip|travel|passport|hotel booking)\b", low):
        return "travel"
    if re.search(r"\b(ransomware|hacked|phishing|cyber|server breach|data breach)\b", low):
        return "cyber"
    if re.search(r"\b(home|house|apartment|roof|burglary|property)\b", low):
        return "home"
    if re.search(r"\b(hospital|doctor|treatment|medical|surgery|illness|diagnosed)\b", low):
        return "health"
    return None


def _clean_policy_candidate(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    raw = value.strip().upper()
    raw = re.sub(r"^(?:MY\s+)?POLICY\s*(?:NUMBER|NO\.?|ID|IDENTIFIER)?\s*(?:IS|:)?\s*", "", raw, flags=re.I).strip()
    raw = re.sub(r"\s+", "-", raw)
    clean = re.sub(r"[^A-Za-z0-9_-]", "", raw).upper()
    if len(clean) < 3 or clean in _GENERIC_POLICY_WORDS or not re.search(r"\d", clean):
        return None
    return clean


def _deterministic_policy(text: str) -> Optional[str]:
    for pattern in (
        r"\bpolicy\s*(?:number|no\.?|id|identifier)?\s*(?:is|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
        r"\bpolicy\s*(?:is|:)\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            candidate = _clean_policy_candidate(match.group(1))
            if candidate:
                return candidate
    for pattern in (
        r"\b([A-Za-z]{2,5}[-_ ]?\d{3,8}(?:[-_ ][A-Za-z0-9]{1,4})?)\b",
        r"\b([A-Za-z0-9]{2,8}[-_]\d{2,8}(?:[-_][A-Za-z0-9]{1,4})?)\b",
        r"\b([A-Za-z]{2,5}\d{3,8}[A-Za-z0-9]{0,4})\b",
    ):
        for match in re.finditer(pattern, text):
            candidate = _clean_policy_candidate(match.group(1))
            if candidate:
                return candidate
    return None


def _policy_is_suspicious(value: Any) -> bool:
    return _clean_policy_candidate(value) is None


_LOCATION_STOPWORDS = {
    "a car accident", "an accident", "a collision", "a crash", "a incident",
    "an event", "a damage", "damage", "the accident", "the incident", "a fight"
}


def _deterministic_location(text: str) -> Optional[str]:
    patterns = [
        r"\b(?:incident|accident|event|crash|collision)\s+(?:happened|occurred|took place)\s+(?:in|at|near|on)\s+(.+?)(?=\s+(?:and|but|with|my|the|this|yesterday)\b|[,.!?]|$)",
        r"\b(?:on the expressway|on highway\s*\w*|on\s+[A-Za-z0-9\s]+(?:road|street|avenue|expressway|highway))\b",
        r"\b(?:in|at|near)\s+([A-Za-z][A-Za-z .'-]{1,80}?)(?=\s+(?:and|but|with|my|the|this|yesterday)\b|[,.!?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = " ".join(match.group(1 if match.lastindex else 0).split()).strip(" .,")
        low = value.lower()
        if any(stop == low for stop in _LOCATION_STOPWORDS):
            continue
        if 2 <= len(value) <= 100 and not re.match(
            r"^(?:a|an|the|my|this|that)\s+(?:car|bike|vehicle|accident|incident|hospital|damage|doctor)\b",
            value, re.I,
        ):
            return value
    return None


def _strip_incident_noise(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    text = re.sub(
        r"\b(?:my\s+)?policy\s+(?:number|no\.?|id|identifier|idea)?\s*(?:is|:)?\s*[A-Za-z0-9_-]+[,.!?]?",
        "", text, flags=re.I,
    )
    text = re.sub(r"\b[A-Za-z]{2,5}[-_ ]?\d{3,8}(?:[-_ ][A-Za-z0-9]{1,4})?\b", "", text)
    text = re.sub(
        r"\b(?:₹|rs\.?|inr|rupees?|repair\s+cost|repair|damage|loss|estimated\s+(?:cost|loss)|claim|cost|bill)\s*"
        r"(?:is|was|of|around|about|approximately|:)?\s*\d[\d,]*(?:\.\d+)?\s*(?:crores?|cr|lakhs?|lacs?|lac|k|thousand)?\b",
        "", text, flags=re.I,
    )
    text = re.sub(r"\b(?:yesterday|today|tomorrow|the day before|day before yesterday|this morning|this afternoon|this evening)\b", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip(" ,.-")


def _normalize_description(value: Any, raw: str) -> Optional[str]:
    candidate = _strip_incident_noise(value)
    raw_clean = " ".join(raw.split()).strip()
    if not candidate or len(candidate) < 4:
        return None
    if candidate.casefold() == raw_clean.casefold():
        candidate = _strip_incident_noise(raw)
    return candidate if len(candidate) >= 4 else None


def _fallback_intent(text: str, awaiting: bool) -> IntentType:
    low = text.strip().lower().strip(" .!?")
    if low in {"thank you", "thanks", "thx"}:
        return "gratitude"
    if low in {"hi", "hello", "hey"}:
        return "greeting"
    if low in {"bye", "goodbye", "that's all", "that is all"}:
        return "closing"
    if awaiting:
        if low in {"yes", "yeah", "yep", "correct", "right", "okay", "ok", "looks good", "all good", "everything is correct", "that's correct", "that is correct"}:
            return "confirmation"
        if low in {"no", "nope", "wrong", "not correct", "that's wrong", "that is wrong", "incorrect"}:
            return "rejection"
    if low in _SOCIAL_EXACT:
        return "filler"
    return "claim_detail"


def _rule_changes(raw: str, state: ClaimState) -> List[FieldChange]:
    current = state.get("extracted_data", {})
    changes: List[FieldChange] = []
    # Social-only utterances must never add claim facts through deterministic rules.
    low = raw.strip().lower().strip(" .!?")
    if low in _SOCIAL_EXACT and len(low.split()) <= 4:
        return changes
    ref = date.today()
    d = _deterministic_date(raw, ref)
    if d and not current.get("event_date"):
        changes.append(FieldChange(field="event_date", operation="set", value=d, evidence=raw, confidence=.99))
    policy = _deterministic_policy(raw)
    if policy:
        old = current.get("policy_id")
        op = "replace" if old and _policy_is_suspicious(old) else ("set" if not old else "ignore")
        changes.append(FieldChange(field="policy_id", operation=op, value=policy, evidence=raw, confidence=.99))
    itype = _deterministic_type(raw)
    if itype and not current.get("insurance_type"):
        changes.append(FieldChange(field="insurance_type", operation="set", value=itype, evidence=raw, confidence=.95))
    amount = _deterministic_amount(raw)
    if amount is not None and current.get("estimated_claim_amount") in (None, "", UNKNOWN_SENTINEL):
        changes.append(FieldChange(field="estimated_claim_amount", operation="set", value=amount, evidence=raw, confidence=.99))
    location = _deterministic_location(raw)
    if location and not current.get("event_location"):
        changes.append(FieldChange(field="event_location", operation="set", value=location, evidence=raw, confidence=.92))
    return changes


def _merge_change(state: ClaimState, change: FieldChange, turn: int) -> bool:
    data = state.setdefault("extracted_data", {})
    metadata = state.setdefault("field_metadata", {})
    statuses = state.setdefault("field_status", {})
    old = data.get(change.field)
    if change.operation == "ignore":
        return False
    if change.operation == "remove":
        if change.field in data:
            data.pop(change.field, None)
            statuses[change.field] = "missing"
            metadata[change.field] = {
                "status": "removed", "source_turn": turn,
                "confidence": change.confidence, "evidence": change.evidence,
            }
            return True
        return False
    if change.field != "event_description" and old not in (None, "", UNKNOWN_SENTINEL) and change.operation != "replace":
        return False
    if change.field == "event_description" and change.operation == "append" and old not in (None, "", UNKNOWN_SENTINEL):
        new_value = str(change.value).strip()
        if not new_value or new_value.casefold() in str(old).casefold():
            return False
        value = f"{str(old).rstrip('.')} {new_value}".strip()
    else:
        value = change.value
    data[change.field] = value
    statuses[change.field] = "corrected" if change.operation == "replace" and old not in (None, "", UNKNOWN_SENTINEL) else "provided"
    metadata[change.field] = {
        "status": statuses[change.field], "source_turn": turn,
        "confidence": change.confidence, "evidence": change.evidence, "updated_at": _now_iso(),
    }
    return True


def _validate_change(change: FieldChange, state: ClaimState) -> Optional[FieldChange]:
    if change.operation == "ignore":
        return change
    if change.confidence < .55:
        return None
    if change.field == "policy_id":
        if change.operation == "remove":
            return change
        normalized = _clean_policy_candidate(change.value)
        return change.model_copy(update={"value": normalized}) if normalized else None
    if change.field == "event_date":
        if change.operation == "remove":
            return change
        normalized = _safe_date(change.value, date.today())
        return change.model_copy(update={"value": normalized}) if normalized else None
    if change.field == "insurance_type":
        if change.operation == "remove":
            return change
        normalized = str(change.value).strip().lower()
        return change.model_copy(update={"value": normalized}) if normalized in INSURANCE_TYPE_KEYS else None
    if change.field == "estimated_claim_amount":
        if change.operation == "remove":
            return change
        amount = _safe_amount(change.value)
        return change.model_copy(update={"value": amount}) if amount is not None else None
    if change.field == "event_location":
        if change.operation == "remove":
            return change
        clean = " ".join(str(change.value).split()).strip(" .,")
        return change.model_copy(update={"value": clean}) if 2 <= len(clean) <= 100 else None
    if change.field == "event_description":
        if change.operation == "remove":
            return change
        clean = _normalize_description(change.value, state.get("last_user_utterance") or "")
        return change.model_copy(update={"value": clean}) if clean else None
    return None


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    raw = (state.get("claim_text") or "").strip()
    state["last_user_utterance"] = raw
    state["turn_number"] = int(state.get("turn_number") or 0) + 1
    state.setdefault("conversation_history", []).append({
        "turn": state["turn_number"], "speaker": "user", "text": raw,
    })
    state.setdefault("extracted_data", {})
    state.setdefault("field_status", {})
    state.setdefault("field_metadata", {})
    state.setdefault("audit_log", [])
    state["recently_extracted_fields"] = []
    state["extraction_changes"] = []
    state["_skip_all"] = False
    state["_confirmation_pending"] = False
    state["_rejection_active"] = False
    if not raw:
        state["last_intent"] = "filler"
        state["_skip_all"] = True
        return state

    awaiting = bool(state.get("awaiting_confirmation"))
    # Social turns get an immediate deterministic intent and skip the expensive LLM call.
    if raw.lower().strip(" .!?") in _SOCIAL_EXACT:
        state["last_intent"] = _fallback_intent(raw, awaiting)
        state["spoken_response"] = ""
        if state["last_intent"] in {"greeting", "gratitude", "closing", "filler"}:
            state["_skip_all"] = True
            responses = {
                "greeting": "Hi. Tell me what happened and I'll collect the claim details as we go.",
                "gratitude": "You're welcome. We can continue whenever you're ready.",
                "closing": "Okay. We can continue whenever you're ready.",
                "filler": "I'm listening. Tell me what happened whenever you're ready.",
            }
            state["next_question"] = responses[state["last_intent"]]
            state["message"] = state["next_question"]
        return state

    prompt = (
        f"{SYSTEM_PROMPT}\nReference date: {date.today().isoformat()}\n"
        f"Current authoritative facts: {json.dumps(state.get('extracted_data', {}), ensure_ascii=False, default=str)}\n"
        f"Recent conversation:\n{_history_text(state)}\n"
        f"Latest claimant utterance:\n{raw}"
    )
    patch = _invoke_structured(_get_llm(), prompt, ExtractionPatch)
    if patch is None:
        patch = ExtractionPatch(intent=_fallback_intent(raw, awaiting), changes=[])
    state["last_intent"] = patch.intent
    state["spoken_response"] = ""

    deterministic = _rule_changes(raw, state)
    deterministic_fields = {c.field for c in deterministic}
    model_changes = [c for c in patch.changes if c.field not in deterministic_fields]
    for raw_change in deterministic + model_changes:
        change = _validate_change(raw_change, state)
        if not change:
            _audit(state, f"Rejected unsafe extraction for '{raw_change.field}'.")
            continue
        if _merge_change(state, change, state["turn_number"]):
            state["recently_extracted_fields"].append(change.field)
            state["extraction_changes"].append(change.model_dump())

    # If the model failed to identify intent but the utterance is clearly a conversational question,
    # do not convert the question into claim data.
    low = raw.lower().strip()
    if not state["recently_extracted_fields"] and re.match(r"^(what|why|how|when|where|can|could|will|do|does|is|are)\b", low):
        state["last_intent"] = "question"

    if patch.intent == "escalation":
        state["escalate_to_human"] = True
        state["escalation_reason"] = "user_requested"
        state["conversation_status"] = "escalated"
        state["_skip_all"] = True
        state["next_question"] = "I understand. I'll connect you with a claims specialist who can help you directly."
        state["message"] = state["next_question"]
        return state
    if patch.intent == "closing":
        state["_skip_all"] = True
        state["next_question"] = "Okay. We can continue whenever you're ready."
        state["message"] = state["next_question"]
        return state
    if patch.intent == "gratitude" and not state["recently_extracted_fields"]:
        state["_skip_all"] = True
        state["next_question"] = "You're welcome. Tell me what happened whenever you're ready."
        state["message"] = state["next_question"]
        return state
    if patch.intent == "greeting" and not state["recently_extracted_fields"]:
        state["_skip_all"] = True
        state["next_question"] = "Hi. Tell me what happened and I'll collect the claim details as we go."
        state["message"] = state["next_question"]
        return state
    if patch.intent == "defer":
        target = state.get("next_question_field")
        if target:
            state.setdefault("unknown_fields", [])
            if target not in state["unknown_fields"]:
                state["unknown_fields"].append(target)
            state["extracted_data"][target] = UNKNOWN_SENTINEL
            state["field_status"][target] = "deferred"
        return state
    if patch.intent == "confirmation" and not state["recently_extracted_fields"]:
        state["_confirmation_pending"] = True
    if patch.intent == "rejection" and not state["recently_extracted_fields"]:
        state["_rejection_active"] = True
    return state


def claim_extractor(state: ClaimState) -> ClaimState:
    return state


def mandatory_field_checker(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state
    data = state.get("extracted_data", {})
    statuses = dict(state.get("field_status", {}))
    metadata = state.setdefault("field_metadata", {})
    missing: List[str] = []
    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value in (None, "", UNKNOWN_SENTINEL):
            statuses[field] = "missing"
            missing.append(field)
        else:
            statuses[field] = statuses.get(field, "provided")
            metadata.setdefault(field, {"status": statuses[field], "confidence": 1.0})
    state["missing_fields"] = missing
    state["field_status"] = statuses
    confidences = [
        float(metadata.get(f, {}).get("confidence", 0.0))
        for f in REQUIRED_FIELDS if f not in missing
    ]
    state["extraction_confidence"] = (
        round(min(confidences), 2) if len(confidences) == len(REQUIRED_FIELDS)
        else round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    )
    if state.get("confirmed"):
        state["conversation_status"] = "pending_verification"
        state["awaiting_confirmation"] = False
    elif state.get("_rejection_active") and state.get("awaiting_confirmation"):
        state["conversation_status"] = "collecting"
        state["awaiting_confirmation"] = False
        state["confirmed"] = False
    elif not missing:
        state["conversation_status"] = "reviewing"
        state["awaiting_confirmation"] = True
    else:
        state["conversation_status"] = "collecting"
        state["awaiting_confirmation"] = False
    return state


def _confirmation_summary(data: Dict[str, Any]) -> str:
    label = SUPPORTED_INSURANCE_TYPES.get(data.get("insurance_type"), str(data.get("insurance_type"))) if data.get("insurance_type") else ""
    date_text = str(data.get("event_date") or "")
    location = str(data.get("event_location") or "")
    amount = data.get("estimated_claim_amount")
    policy = data.get("policy_id")
    description = str(data.get("event_description") or "").strip().rstrip(".")
    if description:
        lead = f"I have your {label.lower() if label else 'claim'} for {description}"
    else:
        lead = f"I have your {label.lower() if label else 'claim'}"
    details: List[str] = []
    if date_text:
        details.append(f"on {date_text}")
    if location:
        details.append(f"in {location}")
    if amount is not None:
        details.append(f"with an estimated loss of ₹{int(float(amount)):,}")
    if policy:
        details.append(f"under policy {policy}")
    return lead + (", " + ", ".join(details) if details else "") + "."


def _deterministic_response(state: ClaimState) -> str:
    if state.get("_skip_all"):
        return state.get("next_question", "")
    if state.get("awaiting_confirmation"):
        return _confirmation_summary(state.get("extracted_data", {})) + " Is everything correct?"
    target = state.get("next_question_field") or (state.get("missing_fields", [None])[0] if state.get("missing_fields") else None)
    prompts = {
        "policy_id": "What is your policy number?",
        "event_date": "When did the incident happen?",
        "insurance_type": "What type of insurance is this claim under?",
        "event_description": "Could you briefly tell me what happened?",
        "event_location": "Where did the incident happen?",
        "estimated_claim_amount": "What is the approximate loss or repair cost?",
    }
    return prompts.get(target, "Tell me a little more about what happened.") if isinstance(target, str) else "Tell me a little more about what happened."


def next_question_generator(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state
    missing = state.get("missing_fields", [])
    state["next_question_field"] = (
        "confirmation" if state.get("awaiting_confirmation")
        else ((state.get("current_field_hint") if state.get("current_field_hint") in missing else missing[0]) if missing else "confirmation")
    )
    state["next_question"] = _deterministic_response(state)
    state["message"] = state["next_question"]
    return state


def natural_response_generator(state: ClaimState) -> ClaimState:
    return state
