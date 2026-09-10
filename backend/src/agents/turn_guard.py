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
    candidates = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if nodes._INCIDENT_TERMS.search(sentence):
            candidates.append(sentence)
    candidate = " ".join(candidates).strip() or text
    candidate = nodes._strip_incident_noise(candidate)
    if location:
        candidate = re.sub(
            rf"\s+(?:in|at|near)\s+{re.escape(location)}(?=\b|[,.!?])",
            "",
            candidate,
            flags=re.I,
        )
    candidate = re.sub(r"\s+(?:and|but)\s*$", "", candidate, flags=re.I).strip(" ,.-")
    if len(candidate) < 4 or not nodes._INCIDENT_TERMS.search(candidate):
        return None
    return candidate


def conversation_turn_processor(state):
    was_awaiting = bool(state.get("awaiting_confirmation"))
    raw = str(state.get("claim_text") or "")
    state = nodes.conversation_turn_processor(state)

    # The deterministic extractor intentionally does not force descriptions from
    # every utterance. When the latest turn is an actual incident narration,
    # recover only the incident-bearing clauses so Phase 1 remains deterministic
    # even when the local LLM is unavailable in CI.
    if not state.get("extracted_data", {}).get("event_description"):
        description = _incident_description_from_text(raw, state)
        if description:
            state.setdefault("extracted_data", {})["event_description"] = description
            state.setdefault("field_status", {})["event_description"] = "provided"
            state.setdefault("field_metadata", {})["event_description"] = {
                "status": "provided",
                "source_turn": state.get("turn_number", 0),
                "confidence": 0.95,
                "evidence": raw,
            }
            state.setdefault("recently_extracted_fields", []).append("event_description")
            state.setdefault("extraction_changes", []).append({
                "field": "event_description",
                "operation": "set",
                "value": description,
                "evidence": raw,
                "confidence": 0.95,
            })

    if was_awaiting and not state.get("recently_extracted_fields"):
        if state.get("last_intent") == "confirmation" or _is_affirmative(raw):
            state["confirmed"] = True
            state["awaiting_confirmation"] = False
            state["conversation_status"] = "pending_verification"
        elif state.get("last_intent") == "rejection" or _is_negative(raw):
            state["confirmed"] = False
            state["awaiting_confirmation"] = False
            state["conversation_status"] = "collecting"
            state["_skip_all"] = True
            state["next_question"] = "No problem. Tell me what you'd like to correct."
            state["message"] = state["next_question"]
    return state


__all__ = ["conversation_turn_processor"]
