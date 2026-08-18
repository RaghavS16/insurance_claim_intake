"""
LangGraph orchestration graphs for Claim Intake and Conversation Turns.

Review 1 Architecture:
- Intake Graph: Compiled as singleton `_intake_graph` (claim_extractor -> mandatory_field_checker -> next_question_generator).
- Conversation Graph: Compiled as singleton `_conversation_graph` (turn processor -> extractor -> validator -> next question / confirmation / completion).
"""
import logging
from langgraph.graph import StateGraph, END

from src.agents.state import ClaimState
from src.agents import nodes


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph 1: Static Intake (Extraction + Mandatory-field check)
# ---------------------------------------------------------------------------
def _build_intake_graph():
    """
    Intake pipeline: raw claim text -> field extraction -> mandatory field validation -> natural prompt.
    """
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
    """Return the pre-compiled intake graph singleton."""
    return _intake_graph


# ---------------------------------------------------------------------------
# Graph 2: Conversation Turn Graph (Review 1 Primary Flow)
# ---------------------------------------------------------------------------
def _build_conversation_graph():
    """
    Conversation turn pipeline:
    User utterance -> Turn intent processor -> [Extractor] -> Field checker -> Natural Response / Confirmation / Completion.
    """
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("conversation_turn_processor", nodes.conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", nodes.next_question_generator)
    graph.add_node("natural_response_generator", nodes.natural_response_generator)

    graph.set_entry_point("conversation_turn_processor")

    # Intent routing: 'repeat' / 'affirmation on confirmation' / 'defer' skip re-extraction
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda s: "skip" if s.get("_skip_extraction") else "extract",
        {"extract": "claim_extractor", "skip": "mandatory_field_checker"},
    )

    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "next_question_generator")
    graph.add_edge("next_question_generator", "natural_response_generator")
    graph.add_edge("natural_response_generator", END)

    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    """Return the pre-compiled conversation-turn graph singleton."""
    return _conversation_graph


__all__ = [
    "build_intake_graph",
    "build_conversation_graph",
]