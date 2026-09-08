"""LangGraph orchestration for the Phase 1 claim conversation."""
from __future__ import annotations

import re

from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.response_guard import safe_spoken_reply
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor


def _ensure_incident_narrative(state: ClaimState) -> ClaimState:
    """Create a clean narrative only when the claimant already described the incident."""
    if state.get("_skip_all") or state.get("extracted_data", {}).get("event_description"):
        return state
    raw = str(state.get("last_user_utterance") or "").strip()
    if len(raw.split()) < 4:
        return state
    candidate = raw
    candidate = re.sub(r"\b(?:my\s+)?policy\s+(?:number|no\.?|id|identifier|idea)\b.*$", "", candidate, flags=re.I)
    candidate = re.sub(r"\b(?:repair\s+cost|repair|damage|loss|estimated\s+(?:cost|loss)|claim)\s*(?:is|was|of|around|about|approximately|:)?\s*(?:₹|rs\.?|inr|rupees?)?\s*\d[\d,]*(?:\.\d+)?\s*(?:crores?|cr|lakhs?|lacs?|lac|k|thousand)?\b", "", candidate, flags=re.I)
    candidate = re.sub(r"\b(?:yesterday|today|tomorrow|the day before|day before yesterday)\b", "", candidate, flags=re.I)
    candidate = re.sub(r"\b(?:in|at|near|around|on)\s+[A-Za-z][A-Za-z .'-]{1,60}?\b(?=\s+(?:and|but|with|my|the|where)\b|[,.!?]|$)", "", candidate, flags=re.I)
    candidate = re.sub(r"\s+([,.!?])", r"\1", candidate)
    candidate = re.sub(r"\s{2,}", " ", candidate).strip(" ,.-")
    if len(candidate.split()) >= 4:
        state.setdefault("extracted_data", {})["event_description"] = candidate
        state.setdefault("field_status", {})["event_description"] = "provided"
        state.setdefault("field_metadata", {})["event_description"] = {
            "status": "provided", "source_turn": state.get("turn_number", 0), "confidence": 0.88,
            "evidence": raw,
        }
        state.setdefault("recently_extracted_fields", []).append("event_description")
    return state


def _response_planner(state: ClaimState) -> ClaimState:
    state = nodes.next_question_generator(state)
    natural = safe_spoken_reply(state)
    if natural and not state.get("awaiting_confirmation") and not state.get("_skip_all"):
        state["next_question"] = natural
        state["message"] = natural
        state["response_message"] = natural
    return state


def _build_conversation_graph():
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("conversation_turn_processor", conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("ensure_incident_narrative", _ensure_incident_narrative)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", _response_planner)
    graph.set_entry_point("conversation_turn_processor")
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda state: "done" if state.get("_skip_all") else "continue",
        {"continue": "claim_extractor", "done": END},
    )
    graph.add_edge("claim_extractor", "ensure_incident_narrative")
    graph.add_edge("ensure_incident_narrative", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "next_question_generator")
    graph.add_edge("next_question_generator", END)
    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    return _conversation_graph


def build_intake_graph():
    return _conversation_graph


__all__ = ["build_intake_graph", "build_conversation_graph"]
