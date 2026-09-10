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


def conversation_turn_processor(state):
    was_awaiting = bool(state.get("awaiting_confirmation"))
    raw = str(state.get("claim_text") or "")
    state = nodes.conversation_turn_processor(state)
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
