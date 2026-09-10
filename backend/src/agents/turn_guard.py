"""Deterministic conversation-state guard for confirmation/rejection."""
from __future__ import annotations

import re

from src.agents import nodes


def _is_affirmative(text: str) -> bool:
    low = " ".join(text.strip().lower().split())
    return bool(re.match(r"^(yes|yeah|yep|correct|right|okay|ok|sure|looks good|all good|everything (is )?correct|that's correct|that is correct)(?:[.!?, ]|$)", low))


def _is_negative(text: str) -> bool:
    low = " ".join(text.strip().lower().split())
    return bool(re.match(r"^(no|nope|wrong|not correct|incorrect|that's wrong|that is wrong)(?:[.!?, ]|$)", low))


def _incident_description_from_text(text: str, state) -> str | None:
    """Recover a grounded incident narrative without depending on Ollama."""
    if not nodes._INCIDENT_TERMS.search(text):
        return None
    location = nodes._deterministic_location(text)
    candidates = [s for s in re.split(r"(?<=[.!?])\s+", text) if nodes._INCIDENT_TERMS.search(s)]
    candidate = " ".join(candidates).strip() or text
    candidate = nodes._strip_incident_noise(candidate)
    if location:
        candidate = re.sub(rf"\s+(?:in|at|near)\s+{re.escape(location)}(?=\b|[,.!?])", "", candidate, flags=re.I)
    candidate = re.sub(r"\s+(?:and|but)\s*$", "", candidate, flags=re.I).strip(" ,.-")
    return candidate if len(candidate) >= 4 and nodes._INCIDENT_TERMS.search(candidate) else None


def _requested_correction_field(text: str, state) -> str | None:
    low = text.lower()
    if re.search(r"amount|cost|loss|repair|price|rupees?|inr|₹", low):
        return "estimated_claim_amount"
    if re.search(r"policy", low):
        return "policy_id"
    if re.search(r"location|place|where", low):
        return "event_location"
    if re.search(r"date|day|when", low):
        return "event_date"
    if re.search(r"insurance|motor|health|home|travel|cyber", low):
        return "insurance_type"
    if re.search(r"happened|accident|incident|damage|crash|collision", low):
        return "event_description"
    return state.get("next_question_field") if state.get("next_question_field") not in {None, "confirmation"} else None


def _correction_prompt(field: str | None) -> str:
    return {
        "estimated_claim_amount": "No problem. What is the corrected loss or repair amount?",
        "policy_id": "No problem. What is the correct policy number?",
        "event_location": "No problem. What is the correct incident location?",
        "event_date": "No problem. What is the correct incident date?",
        "insurance_type": "No problem. What is the correct insurance type?",
        "event_description": "No problem. Please tell me the correct description of what happened.",
    }.get(field, "No problem. Tell me which detail you'd like to correct.")


def conversation_turn_processor(state):
    was_awaiting = bool(state.get("awaiting_confirmation"))
    raw = str(state.get("claim_text") or "")
    state = nodes.conversation_turn_processor(state)

    if not state.get("extracted_data", {}).get("event_description"):
        description = _incident_description_from_text(raw, state)
        if description:
            state.setdefault("extracted_data", {})["event_description"] = description
            state.setdefault("field_status", {})["event_description"] = "provided"
            state.setdefault("field_metadata", {})["event_description"] = {
                "status": "provided", "source_turn": state.get("turn_number", 0),
                "confidence": 0.95, "evidence": raw,
            }
            state.setdefault("recently_extracted_fields", []).append("event_description")
            state.setdefault("extraction_changes", []).append({
                "field": "event_description", "operation": "set", "value": description,
                "evidence": raw, "confidence": 0.95,
            })

    # Never repeat the old confirmation when the claimant starts a correction
    # but has not yet supplied the corrected value.
    if was_awaiting and not state.get("recently_extracted_fields"):
        if state.get("last_intent") == "confirmation" or _is_affirmative(raw):
            state["confirmed"] = True
            state["awaiting_confirmation"] = False
            state["conversation_status"] = "pending_verification"
            state["_skip_all"] = True
            state["next_question"] = "Thanks. I’ve confirmed those claim details. I’ll verify the policy next."
            state["message"] = state["next_question"]
        elif state.get("last_intent") == "rejection" or _is_negative(raw):
            state["confirmed"] = False
            state["awaiting_confirmation"] = False
            state["conversation_status"] = "collecting"
            state["_skip_all"] = True
            state["next_question"] = "No problem. Tell me which detail you'd like to correct."
            state["message"] = state["next_question"]
        elif re.search(r"\b(?:sorry|wrong|incorrect|mistake|correction|corrected|instead|change|update|revised?)\b", raw, re.I):
            state["confirmed"] = False
            state["awaiting_confirmation"] = False
            state["conversation_status"] = "collecting"
            state["_skip_all"] = True
            state["next_question"] = _correction_prompt(_requested_correction_field(raw, state))
            state["message"] = state["next_question"]

    return state


__all__ = ["conversation_turn_processor"]
