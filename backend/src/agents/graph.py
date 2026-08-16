"""
LangGraph orchestration graphs for Claim Intake and Conversation Turns.

Review 1 Architecture:
- Intake Graph: Compiled as singleton `_intake_graph` (claim_extractor -> mandatory_field_checker).
- Conversation Graph: Compiled as singleton `_conversation_graph` (intent processor -> extractor -> validator -> next question / completion).
- Evaluation Graph (Review 2/3): Re-exported from `src.agents.evaluation`.
"""
import logging
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from src.agents.state import ClaimState
from src.agents import nodes
from src.agents.evaluation import build_evaluation_graph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph 1: Static Intake (Extraction + Mandatory-field check)
# ---------------------------------------------------------------------------
def _build_intake_graph():
    """
    Intake pipeline: raw claim text -> field extraction -> mandatory field validation.
    """
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)

    graph.set_entry_point("claim_extractor")
    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", END)

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
    User utterance -> Turn intent processor -> [Extractor] -> Field checker -> Next question / Intake completion.
    """
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("conversation_turn_processor", nodes.conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("next_question_generator", nodes.next_question_generator)
    graph.add_node("intake_completion_marker", nodes.intake_completion_marker)

    graph.set_entry_point("conversation_turn_processor")

    # Intent routing: 'repeat' / 'dont_know' / 'defer' skip re-extraction
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda s: "skip" if s.get("_skip_extraction") else "extract",
        {"extract": "claim_extractor", "skip": "mandatory_field_checker"},
    )

    graph.add_edge("claim_extractor", "mandatory_field_checker")

    graph.add_conditional_edges(
        "mandatory_field_checker",
        lambda s: "missing" if s.get("missing_fields") else "complete",
        {"missing": "next_question_generator", "complete": "intake_completion_marker"},
    )

    graph.add_edge("next_question_generator", END)
    graph.add_edge("intake_completion_marker", END)

    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    """Return the pre-compiled conversation-turn graph singleton."""
    return _conversation_graph


__all__ = [
    "build_intake_graph",
    "build_conversation_graph",
    "build_evaluation_graph",
]