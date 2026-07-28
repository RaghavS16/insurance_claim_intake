from functools import partial
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from src.agents.state import ClaimState
from src.agents import nodes


def build_claim_graph(db: Session):
    graph = StateGraph(ClaimState)  # type: ignore

    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("policy_validator", partial(nodes.policy_validator, db=db))
    graph.add_node("coverage_checker", nodes.coverage_checker)
    graph.add_node("fraud_detector", partial(nodes.fraud_detector, db=db))
    graph.add_node("route_decision", partial(nodes.route_decision, db=db))
    graph.add_node("response_formatter", nodes.response_formatter)

    graph.set_entry_point("claim_extractor")
    graph.add_edge("claim_extractor", "policy_validator")

    graph.add_conditional_edges(
        "policy_validator",
        lambda s: "valid" if s.get("validation_status") == "valid" else "rejected",
        {"valid": "coverage_checker", "rejected": "response_formatter"},
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