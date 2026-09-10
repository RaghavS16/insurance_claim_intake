"""LangGraph orchestration for the conversational claim intake agent."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor


_RESPONSE_SYSTEM_PROMPT = """You are the conversation planner for a voice-first insurance claim assistant.

Your job is NOT to run through a questionnaire. You are an intelligent conversational agent that happens to collect
insurance claim information. Decide what the most helpful thing to say next from the latest claimant utterance, the
conversation, and the authoritative claim facts below.

Rules:
- Respond naturally to what the claimant just said. Do not mechanically continue a previous question.
- If the claimant asked a question, answer it when the available information supports an answer. Never invent policy,
  coverage, regulatory, legal, or claim facts. If the answer requires policy/regulatory documents that are not yet
  available, say that briefly and continue the intake naturally.
- If the claimant corrected a fact, acknowledge the correction and use the corrected value.
- If the claimant supplied several facts, acknowledge the useful information together; do not ask for facts already known.
- If information is missing, ask only for the smallest useful set of missing baseline details. Group related details when
  that sounds natural, rather than asking one field per turn. Do not enumerate fields like a form.
- If all baseline facts are present and confirmation is pending, give a short human-readable recap and ask for one
  confirmation. Do not introduce new questions.
- If the claimant is simply thinking, pausing, thanking you, greeting you, or making process/social conversation, respond
  to that intent instead of forcing an intake question. Keep the response short for voice.
- Do not mention internal state, fields, schemas, extraction, LangGraph, agents, prompts, or "missing fields".
- Do not use bullets or numbered lists. Keep the response to one or two natural sentences suitable for speech.

Authoritative baseline fields are: policy number, incident date, insurance type, incident description, incident location,
and approximate claim/loss amount.
"""

_FIELD_LABELS = {
    "policy_id": "policy number",
    "event_date": "when the incident happened",
    "insurance_type": "type of insurance",
    "event_description": "what happened",
    "event_location": "where it happened",
    "estimated_claim_amount": "the approximate loss or repair cost",
}


def _natural_fallback(missing: list[str], data: dict[str, Any]) -> str:
    """Safe fallback when the response model is unavailable or returns unusable text."""
    if not missing:
        return "I have the claim details I need. Is everything correct?"
    labels = [_FIELD_LABELS[field] for field in missing[:3]]
    if len(missing) >= 5 and not data:
        return (
            "Tell me what happened, when and where it happened, what type of insurance you have, "
            "your policy number, and the approximate loss or repair cost."
        )
    if len(labels) == 1:
        return f"And what about {labels[0]}?"
    if len(labels) == 2:
        return f"And what about {labels[0]} and {labels[1]}?"
    return f"And what about {labels[0]}, {labels[1]}, and {labels[2]}?"


def _message_text(result: Any) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return " ".join(parts).strip()
    return str(content or "").strip()


def _response_is_usable(response: str, missing: list[str], data: dict[str, Any]) -> bool:
    if not response or len(response) > 500:
        return False
    low = response.lower()
    if "<" in response or ">" in response:
        return False
    if any(token in low for token in ("json", "schema", "langgraph", "extracted_data", "missing_fields")):
        return False

    # Prevent a model response from accidentally asking for a fact that is already authoritative.
    supplied_markers = {
        "policy_id": ("policy number", "policy id", "policy no"),
        "event_date": ("when the incident", "incident date", "date of the incident"),
        "insurance_type": ("type of insurance", "insurance type"),
        "event_description": ("what happened", "describe the incident", "incident description"),
        "event_location": ("where it happened", "where the incident", "incident location"),
        "estimated_claim_amount": ("loss", "repair cost", "claim amount", "estimated cost"),
    }
    for field, markers in supplied_markers.items():
        if field not in missing and data.get(field) not in (None, "", nodes.UNKNOWN_SENTINEL):
            if any(marker in low for marker in markers):
                return False
    return True


def _model_response(state: ClaimState) -> str:
    data = state.get("extracted_data", {})
    missing = list(state.get("missing_fields", []))
    history = state.get("conversation_history", [])[-10:]
    history_text = "\n".join(
        f"{turn.get('speaker', 'unknown')}: {turn.get('text', '')}" for turn in history
    ) or "No previous conversation."

    prompt = (
        f"{_RESPONSE_SYSTEM_PROMPT}\n\n"
        f"Authoritative claim facts: {data}\n"
        f"Still-needed baseline information: {missing}\n"
        f"Current conversation status: {state.get('conversation_status', 'collecting')}\n"
        f"Latest detected intent: {state.get('last_intent', 'unclear')}\n"
        f"Latest claimant utterance: {state.get('last_user_utterance', '')}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        "Write only the exact sentence(s) the assistant should say to the claimant."
    )
    try:
        response = _message_text(nodes._get_llm().invoke(prompt))
        if _response_is_usable(response, missing, data):
            return response
    except Exception as exc:
        nodes.logger.warning("Conversational response planning failed: %s", exc)
    return _natural_fallback(missing, data)


def _response_planner(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    missing = list(state.get("missing_fields", []))
    data = state.get("extracted_data", {})

    # The model decides the wording and conversational move. The deterministic fallback is only
    # used when the model is unavailable or tries to violate the state constraints.
    state["next_question_field"] = (
        "confirmation" if state.get("awaiting_confirmation") else (missing[0] if missing else "confirmation")
    )
    state["next_question"] = _model_response(state)
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
