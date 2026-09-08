"""Deterministic conversation-state guard for confirmation/rejection."""
from src.agents import nodes


def _is_affirmative(text: str) -> bool:
    low = text.strip().lower()
    return low.startswith(("yes", "yeah", "yep", "correct", "that's correct", "that is correct", "looks good", "everything looks good", "all good"))


def _is_negative(text: str) -> bool:
    low = text.strip().lower()
    return low.startswith(("no", "nope", "not correct", "that's wrong", "that is wrong"))


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
    return state

__all__ = ["conversation_turn_processor"]
