"""Conversational claim-intake nodes.

The LLM owns semantic interpretation. Application code owns validation,
normalisation, provenance and state merging. A turn produces a *patch* rather
than a replacement claim object, so unrelated speech can never erase facts
already collected.
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
    "estimated_claim_amount": "estimated loss or damage amount",
}

IntentType = Literal[
    "claim_detail", "correction", "confirmation", "rejection",
    "question", "repeat", "defer", "filler", "greeting",
    "gratitude", "closing", "escalation", "unclear"
]


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: Literal[
        "policy_id", "event_date", "insurance_type",
        "event_description", "estimated_claim_amount"
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
    spoken_reply: str = Field(
        description="A natural, helpful conversational response to speak back to the user (1-2 clear, concise sentences)."
    )


class ConversationIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intent: IntentType
    target_field: Optional[str] = None


EXTRACTION_SYSTEM = """You are the semantic extraction and conversational voice engine for an insurance claim intake assistant.
Interpret the claimant's COMPLETE utterance in the context supplied below.
Do not guess, autocomplete, or manufacture facts.

Produce a PATCH and a SPOKEN_REPLY:
1. changes: Include ONLY fields whose meaning is supported by the current utterance. An empty changes array is correct for filler, greetings, thanks, repeat requests, questions, or unrelated speech.
2. spoken_reply: A natural, concise spoken response to the claimant (1-2 sentences). Acknowledge what they said and naturally ask for the next piece of missing information or confirm details.

Operations:
- set: provide a previously missing field.
- replace: explicitly correct/change an existing value.
- append: add genuinely new incident-description information without deleting prior description.
- remove: explicitly withdraw a previously supplied fact.
- ignore: mention a field but do not change its stored value.

Important:
- A new sentence does NOT automatically replace an existing value.
- Do not copy old values into changes unless the claimant is changing them.
- Resolve natural conversational references using the recent dialogue.
- Extract multiple fields when one utterance naturally provides multiple facts.
- For event_description, prefer actual incident facts.
- For insurance_type, choose only: {insurance_types}.
- For estimated_claim_amount, extract the numerical loss/claim estimate.
- For event_date, return the date meaning expressed by the claimant.

Return data matching the supplied schema.
"""

QUESTION_SYSTEM = """You are the conversational voice agent for an insurance claim intake assistant.
Generate ONE natural next response to the claimant.

Your response must:
- sound like a helpful human claims intake specialist, not a form;
- acknowledge useful information when appropriate;
- ask for the most useful missing detail next;
- ask ONE focused question unless the claimant's latest message naturally requires clarification;
- use the recent conversation so the question feels like a continuation;
- never invent or repeat a fact that is not in the verified extracted data;
- never ask for a field that is already known unless clarification/correction is required;
- avoid rigid labels such as "Field 1" or "provide the following";
- avoid repeatedly using the same acknowledgement;
- if the claimant supplied several facts, respond to what they said before moving on;
- if they are unsure, be reassuring and ask for what they can reasonably provide;
- if no claim details have been supplied yet, invite them to describe what happened naturally.

Output spoken text only, with no JSON, markdown, analysis, or quotation marks.
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
    """Prefer schema-constrained generation; fall back to strict JSON parsing."""
    model_name = getattr(model, "model_name", getattr(model, "model", "llm"))
    logger.info("Invoking LLM extraction with model=%s (provider=%s)", model_name, settings.LLM_PROVIDER)
    try:
        structured = model.with_structured_output(schema)
        result = structured.invoke(prompt)
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema.model_validate(result)
    except Exception as exc:
        logger.warning("Structured LLM call failed; trying JSON mode: %s", exc)

    try:
        json_model = model.bind(format=schema.model_json_schema())
        raw = _text_from_response(json_model.invoke(prompt))
        return schema.model_validate(json.loads(raw))
    except Exception as exc:
        logger.error("JSON extraction fallback failed: %s", exc, exc_info=True)
        return None


def _history_text(state: ClaimState, limit: int = 8) -> str:
    history = state.get("conversation_history", [])[-limit:]
    if not history:
        return "No previous turns."
    return "\n".join(f"{h.get('speaker', 'unknown')}: {h.get('text', '')}" for h in history)


def _safe_date(raw: Any, reference: date) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in {"today", "this day"}:
        return reference.isoformat()
    if text in {"yesterday", "the day before"}:
        return (reference - timedelta(days=1)).isoformat()
    if text in {"tomorrow", "the next day"}:
        return (reference + timedelta(days=1)).isoformat()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text.replace(",", ""), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _safe_amount(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None
    text = str(raw).strip().lower().replace(",", "")
    if not text:
        return None
    multiplier = 1000 if re.search(r"\b\d+(?:\.\d+)?\s*k\b", text) else 1
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group()) * multiplier
        return value if value >= 0 else None
    except ValueError:
        return None


def _validate_change(change: FieldChange, state: ClaimState) -> Optional[FieldChange]:
    value = change.value
    if change.operation in {"ignore"}:
        return change
    if change.confidence < 0.55:
        return None

    if change.field == "policy_id":
        if change.operation == "remove":
            return change
        if not isinstance(value, str) or len(value.strip()) < 3:
            return None
        value = value.strip()
        if not any(ch.isalnum() for ch in value):
            return None
        return change.model_copy(update={"value": value.upper()})

    if change.field == "event_date":
        if change.operation == "remove":
            return change
        normalized = _safe_date(value, date.today())
        return change.model_copy(update={"value": normalized}) if normalized else None

    if change.field == "insurance_type":
        if change.operation == "remove":
            return change
        normalized = str(value).strip().lower() if value is not None else ""
        return change.model_copy(update={"value": normalized}) if normalized in INSURANCE_TYPE_KEYS else None

    if change.field == "estimated_claim_amount":
        if change.operation == "remove":
            return change
        amount = _safe_amount(value)
        return change.model_copy(update={"value": amount}) if amount is not None and amount >= 0 else None

    if change.field == "event_description":
        if change.operation == "remove":
            return change
        if not isinstance(value, str):
            return None
        value = " ".join(value.split()).strip()
        if len(value) < 3:
            return None
        return change.model_copy(update={"value": value})

    return None


def _merge_change(state: ClaimState, change: FieldChange, turn: int) -> Optional[str]:
    data = state.setdefault("extracted_data", {})
    metadata = state.setdefault("field_metadata", {})
    status = state.setdefault("field_status", {})
    field = change.field
    old = data.get(field)

    if change.operation == "ignore":
        return None
    if change.operation == "remove":
        if field in data:
            data.pop(field, None)
            status[field] = "missing"
            metadata[field] = {"status": "removed", "source_turn": turn, "evidence": change.evidence, "confidence": change.confidence}
            return f"Removed '{field}' on explicit claimant request."
        return None

    # Never let an ordinary utterance overwrite an already known scalar.
    # A replacement must be semantically identified as a correction.
    if field != "event_description" and old not in (None, "", UNKNOWN_SENTINEL):
        if change.operation != "replace":
            _audit(state, f"Preserved existing '{field}' and ignored non-correction conflict.")
            return None

    if field == "event_description" and change.operation == "append":
        if old and old != UNKNOWN_SENTINEL:
            if str(change.value).casefold() in str(old).casefold():
                return None
            value = f"{str(old).rstrip('.')} {str(change.value).lstrip()}".strip()
        else:
            value = str(change.value)
    else:
        value = change.value

    data[field] = value
    status[field] = "corrected" if change.operation == "replace" and old not in (None, "", UNKNOWN_SENTINEL) else "provided"
    metadata[field] = {
        "status": status[field],
        "source_turn": turn,
        "evidence": change.evidence,
        "confidence": change.confidence,
        "updated_at": _now_iso(),
    }
    return f"{'Corrected' if status[field] == 'corrected' else 'Extracted'} '{field}' from turn {turn}."


def _fallback_patch(state: ClaimState) -> ExtractionPatch:
    return ExtractionPatch(intent="unclear", changes=[], needs_clarification=False, spoken_reply="")


def conversation_turn_processor(state: ClaimState) -> ClaimState:
    raw = (state.get("claim_text") or "").strip()
    state["last_user_utterance"] = raw
    state["turn_number"] = state.get("turn_number", 0) + 1
    state.setdefault("conversation_history", [])
    state.setdefault("extracted_data", {})
    state.setdefault("field_status", {})
    state.setdefault("field_metadata", {})
    state.setdefault("unknown_fields", [])
    state["recently_extracted_fields"] = []
    state["extraction_changes"] = []
    state["deferral_message"] = None
    state["_skip_extraction"] = False
    state["_skip_all"] = False

    if not raw:
        state["last_intent"] = "filler"
        state["_skip_extraction"] = True
        return state

    turn = state["turn_number"]
    state["conversation_history"].append({"turn": turn, "speaker": "user", "text": raw})

    prompt = f"""{EXTRACTION_SYSTEM}

Supported insurance types: {', '.join(sorted(INSURANCE_TYPE_KEYS))}
Reference date: {date.today().isoformat()}
Current question target: {state.get('next_question_field') or 'none'}
Current extracted facts: {json.dumps(state.get('extracted_data', {}), ensure_ascii=False, default=str)}
Recent conversation:
{_history_text(state)}

Claimant's latest utterance:
{raw}
"""
    patch = _invoke_structured(llm, prompt, ExtractionPatch) or _fallback_patch(state)
    state["last_intent"] = patch.intent
    state["current_field_hint"] = next((c.field for c in patch.changes if c.field), None)

    if patch.intent in {"filler", "greeting", "gratitude", "repeat", "question", "closing", "escalation", "confirmation", "rejection"} and not patch.changes:
        state["_skip_extraction"] = True

    if patch.intent == "escalation":
        state["escalate_to_human"] = True
        state["escalation_reason"] = "user_requested"
        state["conversation_status"] = "escalated"
        state["_skip_all"] = True
        state["next_question"] = "I understand. I'll connect you with a claims specialist who can help you directly."
        state["message"] = state["next_question"]
        state.setdefault("conversation_history", []).append({"turn": state.get("turn_number", 0), "speaker": "agent", "text": state["message"]})
        return state

    if patch.intent == "closing":
        state["_skip_all"] = True
        state["next_question"] = "Of course. We can continue whenever you're ready."
        state["message"] = state["next_question"]
        state.setdefault("conversation_history", []).append({"turn": state.get("turn_number", 0), "speaker": "agent", "text": state["message"]})
        return state

    if patch.intent == "defer":
        target = next((c.field for c in patch.changes if c.field), None) or state.get("next_question_field")
        if target:
            state.setdefault("unknown_fields", [])
            if target not in state["unknown_fields"]:
                state["unknown_fields"].append(target)
            state["field_status"][target] = "deferred"
            state["extracted_data"][target] = UNKNOWN_SENTINEL
            state["deferral_message"] = f"That's fine; we can come back to the {FIELD_HUMAN_NAMES.get(target, target)} later."
        state["_skip_extraction"] = True

    if patch.needs_clarification and patch.clarification:
        state["current_field_hint"] = state.get("current_field_hint") or state.get("next_question_field")
        state["clarification_request"] = patch.clarification

    if getattr(patch, "spoken_reply", None) and patch.spoken_reply.strip():
        state["spoken_response"] = patch.spoken_reply.strip()

    valid_changes: List[Dict[str, Any]] = []
    for raw_change in patch.changes:
        change = _validate_change(raw_change, state)
        if not change:
            _audit(state, f"Rejected low-confidence/invalid extraction for '{raw_change.field}'.")
            continue
        note = _merge_change(state, change, turn)
        if note:
            state["recently_extracted_fields"].append(change.field)
            valid_changes.append(change.model_dump())
            _audit(state, note)

    state["extraction_changes"] = valid_changes
    return state


def claim_extractor(state: ClaimState) -> ClaimState:
    """Compatibility node; semantic extraction is performed by the turn processor."""
    return state


def mandatory_field_checker(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    data = state.get("extracted_data", {})
    unknown = set(state.get("unknown_fields", []))
    missing: List[str] = []
    statuses = dict(state.get("field_status", {}))
    metadata = state.setdefault("field_metadata", {})

    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value in (None, "", UNKNOWN_SENTINEL):
            statuses[field] = "deferred" if field in unknown else "missing"
            if field not in unknown:
                missing.append(field)
        else:
            statuses[field] = statuses.get(field, "provided")
            metadata.setdefault(field, {"status": statuses[field], "confidence": 1.0})

    state["missing_fields"] = missing
    state["field_status"] = statuses
    confidences = [float(metadata.get(f, {}).get("confidence", 0.0)) for f in REQUIRED_FIELDS if f not in missing]
    state["extraction_confidence"] = round(sum(confidences) / len(REQUIRED_FIELDS), 2) if confidences else 0.0

    if state.get("confirmed"):
        state["conversation_status"] = "pending_verification"
        state["awaiting_confirmation"] = False
    elif not missing:
        state["conversation_status"] = "reviewing"
        state["awaiting_confirmation"] = True
    else:
        state["conversation_status"] = "collecting"
        state["awaiting_confirmation"] = False
    return state


def _confirmation_summary(data: Dict[str, Any]) -> str:
    values = []
    for field in REQUIRED_FIELDS:
        value = data.get(field, "Not provided")
        if field == "insurance_type" and value in SUPPORTED_INSURANCE_TYPES:
            value = SUPPORTED_INSURANCE_TYPES[value]
        if field == "estimated_claim_amount" and isinstance(value, (int, float)):
            value = f"₹{value:,.2f}"
        values.append(f"{FIELD_HUMAN_NAMES[field].title()}: {value}")
    return "\n".join(values)


def _generate_dynamic_response(state: ClaimState) -> Optional[str]:
    missing = state.get("missing_fields", [])
    recent = state.get("recently_extracted_fields", [])
    facts = state.get("extracted_data", {})
    target = state.get("next_question_field")
    clarification = state.get("clarification_request", "")

    prompt = f"""{QUESTION_SYSTEM}

Conversation status: {state.get('conversation_status', 'collecting')}
Latest user intent: {state.get('last_intent', 'unknown')}
Target field: {target or 'none'}
Missing fields: {json.dumps(missing)}
Newly extracted/corrected fields: {json.dumps(recent)}
Verified extracted facts: {json.dumps(facts, ensure_ascii=False, default=str)}
Existing field metadata: {json.dumps(state.get('field_metadata', {}), ensure_ascii=False, default=str)}
Clarification requested by semantic extractor: {clarification or 'none'}
Recent conversation:
{_history_text(state)}

Write the next response now.
"""
    try:
        return _text_from_response(llm.invoke(prompt)) or None
    except Exception as exc:
        logger.error("Dynamic response generation failed: %s", exc, exc_info=True)
        return None


def next_question_generator(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    state.pop("clarification_request", None) if state.get("last_intent") not in {"unclear"} else None

    if state.get("awaiting_confirmation"):
        state["next_question_field"] = "confirmation"
        if state.get("summary_already_shown"):
            fallback = "Does that all look right? If anything needs changing, just tell me what to correct."
        else:
            fallback = f"Here's what I have so far:\n{_confirmation_summary(state.get('extracted_data', {}))}\nDoes that all look right, or is there anything you'd like me to change?"
            state["summary_already_shown"] = True
        generated = _generate_dynamic_response(state)
        state["next_question"] = generated or fallback
        state["message"] = state["next_question"]
        return state

    missing = state.get("missing_fields", [])
    if missing:
        # Prefer the field most directly implied by the latest turn; otherwise
        # rotate through missing fields without hard-coded wording.
        hinted = state.get("current_field_hint")
        target = hinted if hinted in missing else missing[0]
        state["next_question_field"] = target
    else:
        state["next_question_field"] = "confirmation"

    if state.get("spoken_response") and state["spoken_response"].strip():
        state["next_question"] = state["spoken_response"].strip()
        state["message"] = state["next_question"]
        return state

    fallback = "Could you tell me a little more about what happened?" if not state.get("extracted_data") else "What else can you tell me about the incident?"
    generated = _generate_dynamic_response(state)
    state["next_question"] = generated or fallback
    state["message"] = state["next_question"]
    return state


def natural_response_generator(state: ClaimState) -> ClaimState:
    """Final response node kept for graph/API compatibility."""
    if not state.get("_skip_all"):
        state["message"] = state.get("next_question", "")
        state["spoken_response"] = state["message"]
    
    if state.get("message"):
        state.setdefault("conversation_history", []).append({
            "turn": state.get("turn_number", 0),
            "speaker": "agent",
            "text": state["message"]
        })
        
    return state


__all__ = [
    "conversation_turn_processor",
    "claim_extractor",
    "mandatory_field_checker",
    "next_question_generator",
    "natural_response_generator",
]
