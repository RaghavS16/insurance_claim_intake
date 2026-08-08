"""
LangGraph orchestration graphs.

R4-3: Both graphs are compiled ONCE at module import time and cached as
module-level singletons.  Calling build_evaluation_graph(db) per-request
was adding ~50–200ms of avoidable compilation overhead on top of LLM inference.

For the evaluation graph, the db Session is now threaded through LangGraph's
`config` parameter at invocation time rather than closed over at compile time.
"""

import logging
from functools import partial
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from src.agents.state import ClaimState
from src.agents import nodes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graph 1: Intake (extraction + mandatory-field check)
# Compiled once; no DB dependency.
# ---------------------------------------------------------------------------

def _build_intake_graph():
    """
    Phase 1: claim_text (voice/text) -> extracted fields -> missing-field check.
    Stops here regardless of outcome; the API layer decides whether to prompt
    the user again or move to confirmation based on `missing_fields`.
    """
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)

    graph.set_entry_point("claim_extractor")
    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", END)

    return graph.compile()


# Module-level singleton — compiled once at import time.
_intake_graph = _build_intake_graph()


def build_intake_graph():
    """Return the pre-compiled intake graph singleton."""
    return _intake_graph


# ---------------------------------------------------------------------------
# Graph 2: Evaluation (policy → documents → coverage → fraud → route → format)
# DB-aware; db is injected per-invocation via functools.partial so the graph
# itself is still compiled once and reused.
# ---------------------------------------------------------------------------

def build_evaluation_graph(db: Session):
    """
    Return a compiled evaluation graph with db injected into all DB-aware nodes.

    Nodes that need DB access (policy_validator, fraud_detector, route_decision)
    receive the current Session via functools.partial() so LangGraph sees a
    single-argument callable (state -> state) as required.

    Graph structure:
      policy_validator
        ├─ (valid)               → document_requirement_checker
        │    ├─ (ready)          → coverage_checker
        │    │    ├─ (covered)   → fraud_detector → route_decision → response_formatter
        │    │    └─ (not_covered)               → response_formatter
        │    └─ (missing)        → route_decision → response_formatter
        └─ (rejected/mismatch)                   → response_formatter  [manual_review]

    R2-3: 'type_mismatch' (declared claim_type ≠ policy type) is routed the same
          as 'rejected' — both go straight to response_formatter → manual_review.
    """
    graph = StateGraph(ClaimState)  # type: ignore

    # DB-aware nodes: wrap with partial() so the db Session is pre-bound and
    # LangGraph receives the expected single-argument (state -> state) signature.
    graph.add_node("policy_validator",            partial(nodes.policy_validator, db=db))
    graph.add_node("document_requirement_checker", nodes.document_requirement_checker)
    graph.add_node("coverage_checker",             nodes.coverage_checker)
    graph.add_node("fraud_detector",              partial(nodes.fraud_detector, db=db))
    graph.add_node("route_decision",              partial(nodes.route_decision, db=db))
    graph.add_node("response_formatter",           nodes.response_formatter)

    graph.set_entry_point("policy_validator")

    graph.add_conditional_edges(
        "policy_validator",
        lambda s: "valid" if s.get("validation_status") == "valid" else "rejected_or_mismatch",
        {"valid": "document_requirement_checker", "rejected_or_mismatch": "response_formatter"},
    )

    graph.add_conditional_edges(
        "document_requirement_checker",
        lambda s: "missing" if s.get("missing_documents") else "ready",
        {"ready": "coverage_checker", "missing": "route_decision"},
    )

    graph.add_conditional_edges(
        "coverage_checker",
        lambda s: "covered" if s.get("coverage_eligible") else "not_covered",
        {"covered": "fraud_detector", "not_covered": "response_formatter"},
    )

    graph.add_edge("fraud_detector", "route_decision")
    graph.add_edge("route_decision", "response_formatter")
    graph.add_edge("response_formatter", END)

    return graph.compile()