"""Production-oriented Phase 1 claim conversation engine.

Deterministic normalization owns high-risk scalar fields. The LLM is used as a
semantic interpreter for the latest utterance and produces a structured patch.
Application code owns the final response so the assistant cannot invent facts.
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
llm = get_configured_llm()
T = TypeVar("T", bound=BaseModel)
REQUIRED_FIELDS = list(COMMON_REQUIRED_FIELDS)
UNKNOWN_SENTINEL = "UNKNOWN"
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

SYSTEM_PROMPT = """You are the semantic layer of a production insurance claim intake assistant.
Interpret ONLY the latest claimant utterance. Never invent facts and never copy the whole utterance into a field.
Extract every independently supported fact in the latest utterance, including multiple fields in one sentence.
Use history only to resolve references such as 'the amount', 'that date', or 'the same policy'. Do not re-ask for facts already present.
For event_description, return only the incident narrative and exclude policy numbers, dates, locations, amounts, greetings, and assistant text.
For corrections, use replace only when the claimant clearly corrects a previous value. For new incident details, event_description may use append.
For confirmation/rejection, return the appropriate intent and no field changes unless the same utterance explicitly contains a correction.
For policy_id, never infer an identifier from words such as idea, number, id, my, or is. A plausible policy identifier normally contains digits.
spoken_reply is optional and is not authoritative; the application generates the final response from verified state.
"""
_GENERIC_POLICY_WORDS = {"IDEA", "ID", "NUMBER", "NO", "IS", "MY", "POLICY", "TYPE", "THE", "A"}


def _now_iso() -> str: return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _audit(state: ClaimState, message: str) -> None: state.setdefault("audit_log", []).append(f"[{_now_iso()}] {message}")

def _invoke_structured(model: Any, prompt: str, schema: type[T]) -> Optional[T]:
    try:
        result = model.with_structured_output(schema).invoke(prompt)
        if isinstance(result, schema): return result
        if isinstance(result, dict): return schema.model_validate(result)
    except Exception as exc: logger.warning("Structured extraction failed: %s", exc)
    return None

def _history_text(state: ClaimState, limit: int = 10) -> str:
    history = state.get("conversation_history", [])[-limit:]
    return "\n".join(f"{h.get('speaker', 'unknown')}: {h.get('text', '')}" for h in history) or "No previous turns."

def _safe_date(raw: Any, reference: date) -> Optional[str]:
    if raw is None: return None
    text = str(raw).strip().lower().replace(",", "")
    aliases = {"today": reference, "this day": reference, "yesterday": reference - timedelta(days=1), "the day before": reference - timedelta(days=1), "day before yesterday": reference - timedelta(days=2), "tomorrow": reference + timedelta(days=1), "the next day": reference + timedelta(days=1)}
    if text in aliases: return aliases[text].isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
        try: return datetime.strptime(text, fmt).date().isoformat()
        except ValueError: continue
    return None

def _deterministic_date(text: str, reference: date) -> Optional[str]:
    low = text.lower()
    if re.search(r"\bday before yesterday\b", low): return (reference - timedelta(days=2)).isoformat()
    if re.search(r"\b(yesterday|the day before)\b", low): return (reference - timedelta(days=1)).isoformat()
    if re.search(r"\b(today|this day)\b", low): return reference.isoformat()
    if re.search(r"\b(tomorrow|the next day)\b", low): return (reference + timedelta(days=1)).isoformat()
    for pattern in (r"\b(\d{4}-\d{1,2}-\d{1,2})\b", r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b", r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\s+\d{4})\b"):
        match = re.search(pattern, low)
        if match:
            normalized = _safe_date(match.group(1), reference)
            if normalized: return normalized
    return None

def _parse_indian_amount(text: str) -> Optional[float]:
    s = str(text).lower().replace(",", "").replace("₹", " ").strip()
    m = re.search(r"(?:rs\.?|inr|rupees?)?\s*(\d+(?:\.\d+)?)\s*(crore|crores|cr|lakh|lakhs|lac|lacs|k|thousand)?\b", s)
    if not m: return None
    value = float(m.group(1)); unit = m.group(2) or ""
    return value * {"k":1000,"thousand":1000,"lakh":100000,"lakhs":100000,"lac":100000,"lacs":100000,"crore":10000000,"crores":10000000,"cr":10000000}.get(unit, 1)

def _safe_amount(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool): return None
    if isinstance(raw, (int, float)): return float(raw) if raw >= 0 else None
    return _parse_indian_amount(str(raw))

def _deterministic_amount(text: str) -> Optional[float]:
    low = text.lower()
    for pattern in (r"(?:₹|rs\.?|inr|rupees?|repair\s+cost|repair|damage|loss|estimated\s+(?:cost|loss)|claim|cost|bill|worth)[^\d]{0,25}(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|k|thousand)?\b", r"(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|k|thousand)\b"):
        match = re.search(pattern, low)
        if match: return _safe_amount(" ".join(part for part in match.groups() if part))
    return None

def _deterministic_type(text: str) -> Optional[str]:
    low = text.lower()
    if re.search(r"\b(senior|elderly|pensioner)\b", low) and re.search(r"\b(hospital|medical|treatment|surgery|illness|doctor)\b", low): return "senior_health"
    if re.search(r"\b(bike|bicycle|motorcycle|scooter|car|vehicle|auto|collision|crash|road accident)\b", low): return "motor"
    if re.search(r"\b(luggage|baggage|flight|trip|travel|passport|hotel booking)\b", low): return "travel"
    if re.search(r"\b(ransomware|hacked|phishing|cyber|server breach|data breach)\b", low): return "cyber"
    if re.search(r"\b(home|house|apartment|roof|burglary|property)\b", low): return "home"
    if re.search(r"\b(hospital|doctor|treatment|medical|surgery|illness|diagnosed)\b", low): return "health"
    return None

def _clean_policy_candidate(value: Any) -> Optional[str]:
    if not isinstance(value, str): return None
    value = re.sub(r"[^A-Za-z0-9_-]", "", value).upper()
    if len(value) < 3 or value in _GENERIC_POLICY_WORDS or not re.search(r"\d", value): return None
    return value

def _deterministic_policy(text: str) -> Optional[str]:
    for pattern in (r"\bpolicy\s*(?:number|no\.?|id|identifier)\s*(?:is|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})", r"\bpolicy\s*(?:is|:)\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})"):
        match = re.search(pattern, text, re.I)
        if match:
            candidate = _clean_policy_candidate(match.group(1))
            if candidate: return candidate
    return None

def _policy_is_suspicious(value: Any) -> bool:
    return _clean_policy_candidate(value) is None

def _deterministic_location(text: str) -> Optional[str]:
    patterns = [r"\b(?:incident|accident|event)\s+(?:happened|occurred|took place)\s+(?:in|at|near)\s+(.+?)(?=\s+(?:and|but|with|my|the)\b|[,.!?]|$)", r"\b(?:in|at|near)\s+([A-Za-z][A-Za-z .'-]{1,80}?)(?=\s+(?:and|but|with|my|the)\b|[,.!?]|$)"]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = " ".join(match.group(1).split()).strip(" .,")
            if len(value) >= 2: return value
    return None

def _strip_incident_noise(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    text = re.sub(r"\b(?:my\s+)?policy\s+(?:number|no\.?|id|identifier|idea)\b[^,.!?]*[,.!?]?", "", text, flags=re.I)
    text = re.sub(r"\b(?:₹|rs\.?|inr|rupees?|repair\s+cost|repair|damage|loss|estimated\s+(?:cost|loss)|claim|cost|bill)\s*(?:is|was|of|around|about|approximately|:)?\s*\d[\d,]*(?:\.\d+)?\s*(?:crores?|cr|lakhs?|lacs?|lac|k|thousand)?\b", "", text, flags=re.I)
    text = re.sub(r"\b(?:yesterday|today|tomorrow|the day before|day before yesterday)\b", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip(" ,.-")

def _normalize_description(value: Any, raw: str) -> Optional[str]:
    candidate = _strip_incident_noise(value)
    raw_clean = " ".join(raw.split()).strip()
    if not candidate or len(candidate) < 4: return None
    if candidate.casefold() == raw_clean.casefold(): candidate = _strip_incident_noise(raw)
    if sum(bool(re.search(p, candidate, re.I)) for p in (r"\bpolicy\b", r"\b(?:rupees?|rs\.?|inr|₹)\b", r"\b(?:yesterday|today|tomorrow)\b")) >= 2: candidate = _strip_incident_noise(candidate)
    return candidate if len(candidate) >= 4 else None

def _fallback_intent(text: str, awaiting: bool) -> IntentType:
    low = text.strip().lower().strip(" .!?")
    if awaiting:
        if low in {"yes","yeah","yep","correct","right","okay","ok","looks good","all good","everything is correct","that's correct","that is correct"}: return "confirmation"
        if low in {"no","nope","wrong","not correct","that's wrong","that is wrong","incorrect"}: return "rejection"
    if low in {"hi","hello","hey"}: return "greeting"
    if low in {"thanks","thank you","thx"}: return "gratitude"
    if low in {"bye","goodbye","that's all","that is all"}: return "closing"
    return "claim_detail"

def _rule_changes(raw: str, state: ClaimState) -> List[FieldChange]:
    current = state.get("extracted_data", {}); changes: List[FieldChange] = []
    d = _deterministic_date(raw, date.today())
    if d and not current.get("event_date"): changes.append(FieldChange(field="event_date", operation="set", value=d, evidence=raw, confidence=.99))
    policy = _deterministic_policy(raw)
    if policy:
        old = current.get("policy_id"); operation = "replace" if old and _policy_is_suspicious(old) else ("set" if not old else "ignore")
        changes.append(FieldChange(field="policy_id", operation=operation, value=policy, evidence=raw, confidence=.99))
    itype = _deterministic_type(raw)
    if itype and not current.get("insurance_type"): changes.append(FieldChange(field="insurance_type", operation="set", value=itype, evidence=raw, confidence=.95))
    amount = _deterministic_amount(raw)
    if amount is not None and current.get("estimated_claim_amount") in (None, "", UNKNOWN_SENTINEL): changes.append(FieldChange(field="estimated_claim_amount", operation="set", value=amount, evidence=raw, confidence=.99))
    location = _deterministic_location(raw)
    if location and not current.get("event_location"): changes.append(FieldChange(field="event_location", operation="set", value=location, evidence=raw, confidence=.92))
    return changes

def _merge_change(state: ClaimState, change: FieldChange, turn: int) -> bool:
    data = state.setdefault("extracted_data", {}); metadata = state.setdefault("field_metadata", {}); statuses = state.setdefault("field_status", {}); old = data.get(change.field)
    if change.operation == "ignore": return False
    if change.operation == "remove":
        if change.field in data: data.pop(change.field, None); statuses[change.field] = "missing"; metadata[change.field] = {"status":"removed","source_turn":turn,"confidence":change.confidence,"evidence":change.evidence}; return True
        return False
    if change.field != "event_description" and old not in (None, "", UNKNOWN_SENTINEL) and change.operation != "replace": return False
    if change.field == "event_description" and change.operation == "append" and old not in (None, "", UNKNOWN_SENTINEL):
        new_value = str(change.value).strip()
        if not new_value or new_value.casefold() in str(old).casefold(): return False
        value = f"{str(old).rstrip('.')} {new_value}".strip()
    else: value = change.value
    data[change.field] = value; statuses[change.field] = "corrected" if change.operation == "replace" and old not in (None, "", UNKNOWN_SENTINEL) else "provided"; metadata[change.field] = {"status":statuses[change.field],"source_turn":turn,"confidence":change.confidence,"evidence":change.evidence,"updated_at":_now_iso()}; return True

def _validate_change(change: FieldChange, state: ClaimState) -> Optional[FieldChange]:
    if change.operation == "ignore": return change
    if change.confidence < .55: return None
    if change.field == "policy_id":
        if change.operation == "remove": return change
        normalized = _clean_policy_candidate(change.value); return change.model_copy(update={"value":normalized}) if normalized else None
    if change.field == "event_date":
        if change.operation == "remove": return change
        normalized = _safe_date(change.value, date.today()); return change.model_copy(update={"value":normalized}) if normalized else None
    if change.field == "insurance_type":
        if change.operation == "remove": return change
        normalized = str(change.value).strip().lower(); return change.model_copy(update={"value":normalized}) if normalized in INSURANCE_TYPE_KEYS else None
    if change.field == "estimated_claim_amount":
        if change.operation == "remove": return change
        amount = _safe_amount(change.value); return change.model_copy(update={"value":amount}) if amount is not None else None
    if change.field == "event_location":
        if change.operation == "remove": return change
        clean = " ".join(str(change.value).split()).strip(" .,"); return change.model_copy(update={"value":clean}) if 2 <= len(clean) <= 100 else None
    if change.field == "event_description":
        if change.operation == "remove": return change
        clean = _normalize_description(change.value, str(state.get("last_user_utterance") or "")); return change.model_copy(update={"value":clean}) if clean else None
    return None

def conversation_turn_processor(state: ClaimState) -> ClaimState:
    raw = str(state.get("claim_text") or "").strip(); state["last_user_utterance"] = raw; state["turn_number"] = int(state.get("turn_number",0))+1; state.setdefault("conversation_history",[]).append({"turn":state["turn_number"],"speaker":"user","text":raw}); state.setdefault("extracted_data",{}); state.setdefault("field_status",{}); state.setdefault("field_metadata",{}); state.setdefault("audit_log",[]); state["recently_extracted_fields"]=[]; state["extraction_changes"]=[]; state["_skip_all"]=False; state["_confirmation_pending"]=False; state["_rejection_active"]=False
    if not raw: state["last_intent"]="filler"; return state
    awaiting = bool(state.get("awaiting_confirmation")); prompt = f"{SYSTEM_PROMPT}\nReference date: {date.today().isoformat()}\nCurrent authoritative facts: {json.dumps(state.get('extracted_data',{}),ensure_ascii=False,default=str)}\nRecent conversation:\n{_history_text(state)}\nLatest claimant utterance:\n{raw}"; patch = _invoke_structured(llm,prompt,ExtractionPatch) or ExtractionPatch(intent=_fallback_intent(raw,awaiting),changes=[]); state["last_intent"]=patch.intent; state["spoken_response"]=""
    deterministic = _rule_changes(raw,state); deterministic_fields={c.field for c in deterministic}; model_changes=[c for c in patch.changes if c.field not in deterministic_fields]; all_changes=deterministic+model_changes
    for raw_change in all_changes:
        change=_validate_change(raw_change,state)
        if not change: _audit(state,f"Rejected unsafe extraction for '{raw_change.field}'."); continue
        if _merge_change(state,change,state["turn_number"]): state["recently_extracted_fields"].append(change.field); state["extraction_changes"].append(change.model_dump())
    if patch.intent == "escalation": state["escalate_to_human"]=True; state["escalation_reason"]="user_requested"; state["conversation_status"]="escalated"; state["_skip_all"]=True; state["next_question"]="I understand. I'll connect you with a claims specialist who can help you directly."; state["message"]=state["next_question"]; return state
    if patch.intent == "closing": state["_skip_all"]=True; state["next_question"]="Of course. We can continue whenever you're ready."; state["message"]=state["next_question"]; return state
    if patch.intent == "defer":
        target=state.get("next_question_field")
        if target: state.setdefault("unknown_fields",[]).append(target) if target not in state.setdefault("unknown_fields",[]) else None; state["extracted_data"][target]=UNKNOWN_SENTINEL; state["field_status"][target]="deferred"
        return state
    if patch.intent == "confirmation" and not state["recently_extracted_fields"]: state["_confirmation_pending"]=True
    if patch.intent == "rejection" and not state["recently_extracted_fields"]: state["_rejection_active"]=True
    return state

def claim_extractor(state: ClaimState) -> ClaimState: return state

def mandatory_field_checker(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"): return state
    data=state.get("extracted_data",{}); statuses=dict(state.get("field_status",{})); metadata=state.setdefault("field_metadata",{}); missing=[]
    for field in REQUIRED_FIELDS:
        value=data.get(field)
        if value in (None,"",UNKNOWN_SENTINEL): statuses[field]="missing"; missing.append(field)
        else: statuses[field]=statuses.get(field,"provided"); metadata.setdefault(field,{"status":statuses[field],"confidence":1.0})
    state["missing_fields"]=missing; state["field_status"]=statuses
    confidences=[float(metadata.get(f,{}).get("confidence",0.0)) for f in REQUIRED_FIELDS if f not in missing]; state["extraction_confidence"]=round(min(confidences),2) if len(confidences)==len(REQUIRED_FIELDS) else round(sum(confidences)/len(confidences),2) if confidences else 0.0
    if state.get("confirmed"): state["conversation_status"]="pending_verification"; state["awaiting_confirmation"]=False
    elif state.get("_rejection_active") and state.get("awaiting_confirmation"): state["conversation_status"]="collecting"; state["awaiting_confirmation"]=False; state["confirmed"]=False
    elif not missing: state["conversation_status"]="reviewing"; state["awaiting_confirmation"]=True
    else: state["conversation_status"]="collecting"; state["awaiting_confirmation"]=False
    return state

def _confirmation_summary(data: Dict[str, Any]) -> str:
    label = SUPPORTED_INSURANCE_TYPES.get(data.get("insurance_type"), str(data.get("insurance_type"))) if data.get("insurance_type") else ""
    date_text = str(data.get("event_date") or ""); location = str(data.get("event_location") or ""); amount = data.get("estimated_claim_amount"); policy = data.get("policy_id"); description = str(data.get("event_description") or "").strip().rstrip(".")
    if description: lead = f"I have your {label.lower() if label else 'claim'} for {description.lower()}"
    else: lead = f"I have your {label.lower() if label else 'claim'}"
    details=[]
    if date_text: details.append(f"on {date_text}")
    if location: details.append(f"in {location}")
    if amount is not None: details.append(f"with an estimated loss of ₹{float(amount):,.0f}")
    if policy: details.append(f"under policy {policy}")
    return lead + (", " + ", ".join(details) if details else "") + "."

def _deterministic_response(state: ClaimState) -> str:
    if state.get("_skip_all"): return state.get("next_question","")
    if state.get("awaiting_confirmation"): return _confirmation_summary(state.get("extracted_data",{})) + " Is everything correct?"
    target=state.get("next_question_field") or (state.get("missing_fields") or [None])[0]
    prompts={"policy_id":"What is your policy number?","event_date":"When did the incident happen?","insurance_type":"What type of insurance is this claim under?","event_description":"Could you briefly tell me what happened?","event_location":"Where did the incident happen?","estimated_claim_amount":"What is the approximate loss or repair cost?"}
    return prompts.get(target,"What else can you tell me about the incident?")

def next_question_generator(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"): return state
    missing=state.get("missing_fields",[]); state["next_question_field"]="confirmation" if state.get("awaiting_confirmation") else ((state.get("current_field_hint") if state.get("current_field_hint") in missing else missing[0]) if missing else "confirmation"); state["next_question"]=_deterministic_response(state); state["message"]=state["next_question"]; return state

def natural_response_generator(state: ClaimState) -> ClaimState: return state
