"""LangGraph orchestration for the Phase 1 claim conversation."""
from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor


def _response_planner(state: ClaimState) -> ClaimState:
    state = nodes.next_question_generator(state)
    # The single extraction LLM call can also provide the natural spoken reply.
    # Reuse it instead of issuing a second response-generation LLM call.
    spoken = str(state.get("spoken_response") or "").strip()
    if spoken and not state.get("awaiting_confirmation") and not state.get("_skip_all"):
        state["next_question"] = spoken
        state["message"] = spoken
    return state


def _build_conversation_graph():
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("conversation_turn_processor", conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", _response_planner)
    graph.set_entry_point("conversation_turn_processor")
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda state: "done" if state.get("_skip_all") else "continue",
        {"continue": "claim_extractor", "done": END},
    )
    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "next_question_generator")
    graph.add_edge("next_question_generator", END)
    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    return _conversation_graph


def build_intake_graph():
    return _conversation_graph


__all__ = ["build_intake_graph", "build_conversation_graph"]
