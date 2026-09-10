"""LangGraph orchestration for the claim conversation."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor


def _natural_confirmation(data: dict) -> str:
    label = nodes.SUPPORTED_INSURANCE_TYPES.get(data.get("insurance_type"), data.get("insurance_type", ""))
    description = str(data.get("event_description") or "").strip().rstrip(".")
    date_text = data.get("event_date")
    location = data.get("event_location")
    amount = data.get("estimated_claim_amount")
    policy = data.get("policy_id")

    parts = []
    if description:
        parts.append(description)
    if date_text:
        parts.append(f"on {date_text}")
    if location:
        parts.append(f"in {location}")
    if amount is not None:
        parts.append(f"with an estimated loss of ₹{int(float(amount)):,}")
    if policy:
        parts.append(f"under policy {policy}")

    if label:
        lead = f"Got it. I’ve captured your {str(label).lower()} claim"
    else:
        lead = "Got it. I’ve captured your claim"
    return lead + (": " + ", ".join(parts) if parts else ".") + ". Does that look right?"


def _grouped_missing_prompt(missing: list[str], data: dict) -> str:
    """Ask for several still-missing baseline facts together, without sounding like a form."""
    if not missing:
        return "Tell me anything else you want to add to the claim."

    labels = {
        "policy_id": "policy number",
        "event_date": "when the incident happened",
        "insurance_type": "type of insurance",
        "event_description": "what happened",
        "event_location": "where it happened",
        "estimated_claim_amount": "the approximate loss or repair cost",
    }

    # Prefer a single natural invitation when most/all baseline information is absent.
    if len(missing) >= 5 and not data:
        return "Tell me what happened, when and where it happened, what type of insurance you have, your policy number, and the approximate loss or repair cost."

    phrases = [labels[f] for f in missing[:3]]
    if len(phrases) == 1:
        return f"And what about {phrases[0]}?"
    if len(phrases) == 2:
        return f"And what about {phrases[0]} and {phrases[1]}?"
    return f"And what about {phrases[0]}, {phrases[1]}, and {phrases[2]}?"


def _response_planner(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    if state.get("awaiting_confirmation"):
        state["next_question_field"] = "confirmation"
        state["next_question"] = _natural_confirmation(state.get("extracted_data", {}))
        state["message"] = state["next_question"]
        return state

    missing = list(state.get("missing_fields", []))
    state["next_question_field"] = missing[0] if missing else "confirmation"
    state["next_question"] = _grouped_missing_prompt(missing, state.get("extracted_data", {}))
    state["message"] = state["next_question"]
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
