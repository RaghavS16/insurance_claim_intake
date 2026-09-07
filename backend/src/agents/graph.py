"""LangGraph orchestration for conversational claim intake."""
import logging
from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor

logger = logging.getLogger(__name__)


def _build_intake_graph():
    """Single-turn compatibility graph."""
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", nodes.next_question_generator)
    graph.add_node("natural_response_generator", nodes.natural_response_generator)
    graph.set_entry_point("claim_extractor")
    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "next_question_generator")
    graph.add_edge("next_question_generator", "natural_response_generator")
    graph.add_edge("natural_response_generator", END)
    return graph.compile()


_intake_graph = _build_intake_graph()


def build_intake_graph():
    return _intake_graph


def _build_conversation_graph():
    """One semantic interpretation per user turn, followed by validation and response planning."""
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("conversation_turn_processor", conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", nodes.next_question_generator)
    graph.add_node("natural_response_generator", nodes.natural_response_generator)
    graph.set_entry_point("conversation_turn_processor")
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda state: "skip" if state.get("_skip_extraction") else "extract",
        {"extract": "claim_extractor", "skip": "mandatory_field_checker"},
    )
    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "next_question_generator")
    graph.add_edge("next_question_generator", "natural_response_generator")
    graph.add_edge("natural_response_generator", END)
    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    return _conversation_graph


__all__ = ["build_intake_graph", "build_conversation_graph"]
