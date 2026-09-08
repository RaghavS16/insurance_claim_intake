"""Deterministic conversation-state guard.

The guard only promotes a turn to confirmed when the claimant explicitly
confirms while the previous state was awaiting confirmation. It never treats
"all fields are present" as submission.
"""
from src.agents import nodes


def conversation_turn_processor(state):
    was_awaiting = bool(state.get("awaiting_confirmation"))
    state = nodes.conversation_turn_processor(state)
    if was_awaiting and state.get("last_intent") == "confirmation" and not state.get("recently_extracted_fields"):
        state["confirmed"] = True
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "pending_verification"
    elif was_awaiting and state.get("last_intent") == "rejection" and not state.get("recently_extracted_fields"):
        state["confirmed"] = False
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "collecting"
    return state

__all__ = ["conversation_turn_processor"]
