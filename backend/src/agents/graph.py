from functools import partial
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from src.agents.state import ClaimState
from src.agents import nodes


def build_intake_graph():
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


def build_evaluation_graph(db: Session):
    """
    Phase 2: runs only after the user has confirmed the extracted fields.
    policy_validator -> document_requirement_checker -> coverage_checker
    -> fraud_detector -> route_decision -> response_formatter
    """
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("policy_validator", partial(nodes.policy_validator, db=db))
    graph.add_node("document_requirement_checker", nodes.document_requirement_checker)
    graph.add_node("coverage_checker", nodes.coverage_checker)
    graph.add_node("fraud_detector", partial(nodes.fraud_detector, db=db))
    graph.add_node("route_decision", partial(nodes.route_decision, db=db))
    graph.add_node("response_formatter", nodes.response_formatter)

    graph.set_entry_point("policy_validator")

    graph.add_conditional_edges(
        "policy_validator",
        lambda s: "valid" if s.get("validation_status") == "valid" else "rejected",
        {"valid": "document_requirement_checker", "rejected": "response_formatter"},
    )

    graph.add_conditional_edges(
        "document_requirement_checker",
        lambda s: "missing" if s.get("missing_documents") else "ready",
        {"ready": "coverage_checker", "missing": "response_formatter"},
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