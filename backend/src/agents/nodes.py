"""Deterministic-first conversational claim intake for Phase 1.

The LLM interprets meaning. Application code owns normalization, validation,
state transitions and persistence. A turn produces a patch; it never replaces
the complete claim state.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.agents.constants import COMMON_REQUIRED_FIELDS, INSURANCE_TYPE_KEYS, SUPPORTED_INSURANCE_TYPES
from src.agents.llm_factory import get_configured_llm
from src.agents.state import ClaimState
from src.config import settings
from src.utils.logger import app_logger

logger = app_logger
llm = get_configured_llm()
T = TypeVar("T", bound=BaseModel)
REQUIRED_FIELDS = list(COMMON_REQUIRED_FIELDS)
UNKNOWN_SENTINEL = "UNKNOWN"
FIELD_HUMAN_NAMES = {
    "policy_id": "policy number",
    "event_date": "incident date",
    "insurance_type": "insurance type",
    "event_description": "what happened",
    "event_location": "incident location",
    "estimated_claim_amount": "estimated loss or damage amount",
}
IntentType = Literal["claim_detail", "correction", "confirmation", "rejection", "question", "repeat", "defer", "filler", "greeting", "gratitude", "closing", "escalation", "unclear"]


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: Literal["policy_id", "event_date", "insurance_type", "event_description", "event_location", "estimated_claim_amount"]
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


EXTRACTION_SYSTEM = """You are a production insurance claim intake assistant.
Interpret ONLY the claimant's latest utterance in context. Never invent facts.
Return a patch containing only facts explicitly stated or unambiguously expressed in the latest utterance.
Resolve relative dates such as yesterday/today/tomorrow using the supplied reference date.
Extract every independently supported common field in one utterance.
For corrections, use replace only when the claimant explicitly corrects a previous value.
For event description, use append for genuinely new details and replace for an explicit correction.
For insurance_type use only: health, senior_health, home, travel, motor, cyber.
For estimated_claim_amount return the actual loss/repair estimate, not dates, IDs, years, phone numbers, or unrelated numbers.
For confirmation, classify clear affirmative/negative answers as confirmation/rejection and do not create field changes unless the user also explicitly corrects something.
Keep spoken_reply natural, concise, human, and based only on verified/current information. Ask at most one focused next question when information is missing.
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit(state: ClaimState, message: str) -> None:
    state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")


def _text_from_response(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, list):
        return " ".join(str(x) for x in content).strip()
    return str(content).strip()


def _invoke_structured(model: Any, prompt: str, schema: type[T]) -> Optional[T]:
    try:
        structured = model.with_structured_output(schema)
        result = structured.invoke(prompt)
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema.model_validate(result)
    except Exception as exc:
        logger.warning("Structured extraction failed; trying JSON fallback: %s", exc)
    try:
        json_model = model.bind(format=schema.model_json_schema())
        return schema.model_validate(json.loads(_text_from_response(json_model.invoke(prompt))))
    except Exception as exc:
        logger.error("JSON extraction fallback failed: %s", exc)
        return None


def _history_text(state: ClaimState, limit: int = 6) -> str:
    history = state.get("conversation_history", [])[-limit:]
    return "\n".join(f"{h.get('speaker', 'unknown')}: {h.get('text', '')}" for h in history) or "No previous turns."


def _safe_date(raw: Any, reference: date) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().lower().replace(",", "")
    if not text:
        return None
    aliases = {
        "today": reference,
        "this day": reference,
        "yesterday": reference - timedelta(days=1),
        "the day before": reference - timedelta(days=1),
        "tomorrow": reference + timedelta(days=1),
        "the next day": reference + timedelta(days=1),
    }
    if text in aliases:
        return aliases[text].isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _deterministic_date(text: str, reference: date) -> Optional[str]:
    low = text.lower()
    if re.search(r"\b(yesterday|the day before)\b", low):
        return (reference - timedelta(days=1)).isoformat()
    if re.search(r"\b(today|this day)\b", low):
        return reference.isoformat()
    if re.search(r"\b(tomorrow|the next day)\b", low):
        return (reference + timedelta(days=1)).isoformat()
    patterns = [
        r"\b(\d{4}-\d{1,2}-\d{1,2})\b",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b",
        r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b",
        r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\s+\d{4})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, low)
        if m:
            normalized = _safe_date(m.group(1), reference)
            if normalized:
                return normalized
    return None


def _parse_indian_amount(text: str) -> Optional[float]:
    s = text.lower().replace(",", "").replace("₹", " ")
    m = re.search(r"(?:rs\.?|inr|rupees?|₹)?\s*(\d+(?:\.\d+)?)\s*(crore|crores|cr|lakh|lakhs|lac|lacs|k|thousand)?\b", s)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2) or ""
    mult = {"k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000}.get(unit, 1)
    return value * mult


def _safe_amount(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None
    text = str(raw).strip().lower()
    if not text:
        return None
    amount = _parse_indian_amount(text)
    if amount is None:
        m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
        if not m:
            return None
        amount = float(m.group())
    return amount if amount >= 0 else None


def _deterministic_amount(text: str) -> Optional[float]:
    low = text.lower()
    # Prefer numbers near financial/loss language to avoid extracting dates/IDs.
    patterns = [
        r"(?:₹|rs\.?|inr|rupees?|repair cost|repair|damage|loss|claim|estimated cost|cost|worth|bill)[^\d]{0,20}(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|k|thousand)?\b",
        r"(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|k|thousand)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, low)
        if m:
            return _safe_amount(" ".join(x for x in m.groups() if x))
    return None


def _deterministic_type(text: str) -> Optional[str]:
    low = text.lower()
    if re.search(r"\b(bike|bicycle|motorcycle|scooter|car|vehicle|auto|collision|crash|road accident)\b", low):
        return "motor"
    if re.search(r"\b(luggage|baggage|flight|trip|travel|passport|hotel booking)\b", low):
        return "travel"
    if re.search(r"\b(ransomware|hacked|phishing|cyber|server breach|data breach)\b", low):
        return "cyber"
    if re.search(r"\b(house|home|apartment|roof|fire|burglary|property)\b", low):
        return "home"
    if re.search(r"\b(hospital|doctor|treatment|medical|surgery|illness|diagnosed)\b", low):
        return "health"
    if re.search(r"\b(senior|elderly|father|mother|pensioner)\b.*\b(hospital|medical|treatment|surgery)\b", low):
        return "senior_health"
    return None


def _deterministic_policy(text: str) -> Optional[str]:
    patterns = [r"\b(?:policy(?:\s+(?:number|no|id))?|pol)\s*(?:is|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})\b"]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = m.group(1).upper()
            if value not in {"NUMBER", "NO", "ID", "IS", "MY"}:
                return value
    return None


def _deterministic_location(text: str) -> Optional[str]:
    m = re.search(r"\b(?:in|at|near|around|on)\s+([A-Z][A-Za-z .'-]{2,50})(?=[,.!?]|\s+(?:yesterday|today|last|on|and|where)\b|$)", text)
    if m:
        candidate = " ".join(m.group(1).split()).strip(" .")
        if candidate.lower() not in {"the road", "home", "work"} or candidate:
            return candidate
    return None


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
            metadata[change.field] = {"status": "removed", "source_turn": turn, "confidence": change.confidence, "evidence": change.evidence}
            return True
        return False
    if change.field != "event_description" and old not in (None, "", UNKNOWN_SENTINEL) and change.operation != "replace":
        return False
    if change.field == "event_description" and change.operation == "append" and old not in (None, "", UNKNOWN_SENTINEL):
        new_value = str(change.value).strip()
        if new_value.casefold() in str(old).casefold():
            return False
        value = f"{str(old).rstrip('.')} {new_value}".strip()
    else:
        value = change.value
    data[change.field] = value
    statuses[change.field] = "corrected" if change.operation == "replace" and old not in (None, "", UNKNOWN_SENTINEL) else "provided"
    metadata[change.field] = {"status": statuses[change.field], "source_turn": turn, "confidence": change.confidence, "evidence": change.evidence, "updated_at": _now_iso()}
    return True


def _validate_change(change: FieldChange, state: ClaimState) -> Optional[FieldChange]:
    if change.operation == "ignore":
        return change
    if change.confidence < 0.55:
        return None
    value = change.value
    if change.field == "policy_id":
        if change.operation == "remove": return change
        if not isinstance(value, str) or len(value.strip()) < 3: return None
        return change.model_copy(update={"value": value.strip().upper()})
    if change.field == "event_date":
        if change.operation == "remove": return change
        normalized = _safe_date(value, date.today())
        return change.model_copy(update={"value": normalized}) if normalized else None
    if change.field == "insurance_type":
        if change.operation == "remove": return change
        normalized = str(value).strip().lower()
        return change.model_copy(update={"value": normalized}) if normalized in INSURANCE_TYPE_KEYS else None
    if change.field == "estimated_claim_amount":
        if change.operation == "remove": return change
        amount = _safe_amount(value)
        return change.model_copy(update={"value": amount}) if amount is not None else None
    if change.field in {"event_description", "event_location"}:
        if change.operation == "remove": return change
        if not isinstance(value, str): return None
        clean = " ".join(value.split()).strip()
        if len(clean) < 2: return None
        return change.model_copy(update={"value": clean})
    return None


def _rule_changes(raw: str, state: ClaimState) -> List[FieldChange]:
    changes: List[FieldChange] = []
    current = state.get("extracted_data", {})
    d = _deterministic_date(raw, date.today())
    if d and not current.get("event_date"):
        changes.append(FieldChange(field="event_date", operation="set", value=d, evidence=raw, confidence=0.99))
    policy = _deterministic_policy(raw)
    if policy and not current.get("policy_id"):
        changes.append(FieldChange(field="policy_id", operation="set", value=policy, evidence=raw, confidence=0.99))
    itype = _deterministic_type(raw)
    if itype and not current.get("insurance_type"):
        changes.append(FieldChange(field="insurance_type", operation="set", value=itype, evidence=raw, confidence=0.93))
    amount = _deterministic_amount(raw)
    if amount is not None and current.get("estimated_claim_amount") in (None, "", UNKNOWN_SENTINEL):
        changes.append(FieldChange(field="estimated_claim_amount", operation="set", value=amount, evidence=raw, confidence=0.98))
    location = _deterministic_location(raw)
    if location and not current.get("event_location"):
        changes.append(FieldChange(field="event_location", operation="set", value=location, evidence=raw, confidence=0.80))
    # The utterance itself is the strongest evidence for the incident narrative.
    if len(raw.split()) >= 4 and not re.fullmatch(r"(?:hello|hi|hey|thanks|thank you|okay|ok|yes|no|yeah)[.! ]*", raw, re.I):
        changes.append(FieldChange(field="event_description", operation="append" if current.get("event_description") else "set", value=raw, evidence=raw, confidence=0.94))
    return changes


def _fallback_patch(state: ClaimState, raw: str) -> ExtractionPatch:
    changes = _rule_changes(raw, state)
    if changes:
        return ExtractionPatch(intent="claim_detail", changes=changes, spoken_reply="")
    low = raw.lower().strip(" .!?")
    if low in {"yes", "yeah", "yep", "correct", "that's correct", "that is correct", "looks good", "everything looks good", "okay"}:
        return ExtractionPatch(intent="confirmation", changes=[], spoken_reply="")
    if low in {"no", "nope", "not correct", "that's wrong", "that is wrong"}:
        return ExtractionPatch(intent="rejection", changes=[], spoken_reply="")
    if low in {"hi", "hello", "hey"}:
        return ExtractionPatch(intent="greeting", changes=[], spoken_reply="")
    if low in {"thanks", "thank you", "thx"}:
        return ExtractionPatch(intent="gratitude", changes=[], spoken_reply="")
    return ExtractionPatch(intent="unclear", changes=[], spoken_reply="")


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    raw = (state.get("claim_text") or "").strip()
    state["last_user_utterance"] = raw
    state["turn_number"] = int(state.get("turn_number", 0)) + 1
    state.setdefault("conversation_history", []).append({"turn": state["turn_number"], "speaker": "user", "text": raw})
    state.setdefault("extracted_data", {})
    state.setdefault("field_status", {})
    state.setdefault("field_metadata", {})
    state.setdefault("audit_log", [])
    state["recently_extracted_fields"] = []
    state["extraction_changes"] = []
    state["_skip_all"] = False
    state["_confirmation_pending"] = False
    if not raw:
        state["last_intent"] = "filler"
        return state

    prompt = f"""{EXTRACTION_SYSTEM}
Reference date: {date.today().isoformat()}
Current extracted facts: {json.dumps(state.get('extracted_data', {}), ensure_ascii=False, default=str)}
Current missing fields: {json.dumps(state.get('missing_fields', []))}
Recent conversation:
{_history_text(state)}
Latest claimant utterance:
{raw}
"""
    patch = _invoke_structured(llm, prompt, ExtractionPatch)
    if patch is None:
        patch = _fallback_patch(state, raw)
    state["last_intent"] = patch.intent
    state["spoken_response"] = patch.spoken_reply.strip() if patch.spoken_reply else ""

    # Deterministic signals supplement the model. They are applied only when the
    # field is absent; existing values are never overwritten without correction.
    model_changes = list(patch.changes)
    existing_fields = {c.field for c in model_changes}
    for change in _rule_changes(raw, state):
        if change.field not in existing_fields:
            model_changes.append(change)

    for raw_change in model_changes:
        change = _validate_change(raw_change, state)
        if not change:
            _audit(state, f"Rejected invalid extraction for '{raw_change.field}'.")
            continue
        if _merge_change(state, change, state["turn_number"]):
            state["recently_extracted_fields"].append(change.field)
            state["extraction_changes"].append(change.model_dump())

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
        state["next_question"] = "Of course. We can continue whenever you're ready."
        state["message"] = state["next_question"]
        return state
    if patch.intent == "defer":
        target = state.get("next_question_field")
        if target:
            state.setdefault("unknown_fields", []).append(target) if target not in state.setdefault("unknown_fields", []) else None
            state["extracted_data"][target] = UNKNOWN_SENTINEL
            state["field_status"][target] = "deferred"
        return state
    if patch.intent == "confirmation" and not patch.changes:
        state["_confirmation_pending"] = True
    if patch.intent == "rejection" and not patch.changes:
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
    confidences = [float(metadata.get(f, {}).get("confidence", 0.0)) for f in REQUIRED_FIELDS if f not in missing]
    state["extraction_confidence"] = round(min(confidences), 2) if len(confidences) == len(REQUIRED_FIELDS) else round(sum(confidences) / len(REQUIRED_FIELDS), 2) if confidences else 0.0
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
    lines = []
    for field in REQUIRED_FIELDS:
        value = data.get(field, "Not provided")
        if field == "insurance_type":
            value = SUPPORTED_INSURANCE_TYPES.get(value, value)
        elif field == "estimated_claim_amount" and isinstance(value, (int, float)):
            value = f"₹{value:,.0f}"
        lines.append(f"{FIELD_HUMAN_NAMES[field].title()}: {value}")
    return "\n".join(lines)


def _deterministic_response(state: ClaimState) -> str:
    if state.get("_skip_all"):
        return state.get("next_question", "")
    if state.get("_confirmation_pending") and state.get("awaiting_confirmation"):
        return "Thanks. I have all the details I need. Here’s the summary:\n" + _confirmation_summary(state.get("extracted_data", {})) + "\nDoes everything look correct?"
    if state.get("awaiting_confirmation"):
        return "I have all the details I need. Here’s the summary:\n" + _confirmation_summary(state.get("extracted_data", {})) + "\nDoes everything look correct?"
    missing = state.get("missing_fields", [])
    target = state.get("next_question_field") or (missing[0] if missing else None)
    prompts = {
        "policy_id": "What is the policy number?",
        "event_date": "When did the incident happen?",
        "insurance_type": "What type of insurance is this claim under?",
        "event_description": "Could you tell me what happened?",
        "event_location": "Where did the incident happen?",
        "estimated_claim_amount": "What is the approximate loss or repair cost?",
    }
    return prompts.get(target, "What else can you tell me about the incident?")


def next_question_generator(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state
    if state.get("awaiting_confirmation"):
        state["next_question_field"] = "confirmation"
        state["next_question"] = _deterministic_response(state)
        state["message"] = state["next_question"]
        return state
    missing = state.get("missing_fields", [])
    if missing:
        hinted = state.get("current_field_hint")
        target = hinted if hinted in missing else missing[0]
        state["next_question_field"] = target
    else:
        state["next_question_field"] = "confirmation"
    if state.get("spoken_response") and not state.get("recently_extracted_fields") and state.get("last_intent") not in {"unclear", "claim_detail"}:
        state["next_question"] = state["spoken_response"]
    else:
        state["next_question"] = _deterministic_response(state)
    state["message"] = state["next_question"]
    return state


def natural_response_generator(state: ClaimState) -> ClaimState:
    # Kept as a compatibility node; response generation is deterministic and
    # already completed by next_question_generator to avoid a second LLM call.
    return state
