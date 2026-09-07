"""Conversation guard helpers."""
from src.agents import nodes


def conversation_turn_processor(state):
    state = nodes.conversation_turn_processor(state)
    if state.get("last_intent") == "confirmation" and state.get("awaiting_confirmation"):
        state["confirmed"] = True
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "pending_verification"
        state["_skip_extraction"] = True
    elif state.get("last_intent") == "rejection" and state.get("awaiting_confirmation"):
        state["confirmed"] = False
        state["awaiting_confirmation"] = False
        state["conversation_status"] = "collecting"
    return state
