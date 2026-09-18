"""LangGraph orchestration for the conversational claim intake agent."""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor
from src.agents.dynamic_requirements import build_dynamic_context, extract_answers


_RESPONSE_SYSTEM_PROMPT = """You are an intelligent, empathetic conversation planner for an insurance claim intake assistant.

Your goal is to guide the claimant through a smooth, natural conversation across 4 stages:
1. Baseline Details Gathering: Collect incident description, insurance type, incident date, incident location, approximate damage/loss amount, and policy number. Acknowledge facts provided, respond empathetically, and ask only for what is still needed.
2. Baseline Confirmation & Policy Verification: Once all baseline details are present, present a concise recap and ask the claimant if the details are accurate. Once verified, transition smoothly to specific details.
3. Dynamic Requirements & Evidence Files: Gather domain-specific details (from RAG) and remind them to upload supporting documents or photos if needed.
4. Final Review & Submission: Once all specific details and evidence are in place, ask if they would like to submit the claim directly to the claims adjuster.

Rules:
- Speak naturally and conversationally. Do not sound like a rigid questionnaire or form.
- If the claimant provided several facts at once, acknowledge them together.
- If the claimant made a correction (e.g. "my policy number is POL-1409-XI"), warmly acknowledge the correction and use the updated value.
- If the claimant asks a question, answer it helpfully based on available information or insurance context.
- Never invent policy numbers, coverage decisions, or legal facts.
- Do not mention internal variables, schemas, JSON, LangGraph, agents, or "missing fields".
- Keep voice-friendly: 1 to 2 clear, natural sentences suitable for text and speech.
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
    """Safe, non-form-like fallback when the response model is unavailable."""
    if not missing:
        return "I have the claim details I need. Is everything correct?"
    labels = [_FIELD_LABELS[field] for field in missing[:3] if field in _FIELD_LABELS]
    if len(missing) >= 5 and not data:
        return (
            "Tell me whatever you know about what happened, when and where it happened, your insurance type, "
            "policy number, and approximate loss or repair cost."
        )
    if len(labels) == 1:
        return f"Whenever you're ready, tell me {labels[0]}."
    if len(labels) == 2:
        return f"Whenever you're ready, tell me {labels[0]} and {labels[1]}."
    return f"Whenever you're ready, tell me {', '.join(labels)}."


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
    if not response or len(response) > 600:
        return False
    low = response.lower()
    if "<" in response or ">" in response:
        return False
    if any(token in low for token in ("json", "schema", "langgraph", "extracted_data", "missing_fields")):
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
        f"Still-needed claim-specific information: {state.get('dynamic_missing', [])}\n"
        f"Still-needed evidence uploads: {state.get('missing_evidence', [])}\n"
        f"Grounding context: {state.get('knowledge_context', {})}\n"
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


def _dynamic_fallback(state: ClaimState) -> str:
    remaining = state.get("dynamic_missing") or []
    missing_ev = state.get("missing_evidence") or []
    data = state.get("extracted_data") or {}
    if remaining:
        first = remaining[0]
        hint = first.get("question_hint") or f"could you provide your {first.get('label', 'details').lower()}?"
        return f"To proceed with your {data.get('insurance_type', '')} claim, {hint}".strip()
    if missing_ev:
        first_ev = missing_ev[0]
        return f"Please upload {first_ev.get('label', 'the supporting document').lower()} when you have it so we can continue."
    return _natural_fallback(list(state.get("missing_fields", [])), data)


def _dynamic_requirement_enrichment(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state
    data = state.get("extracted_data") or {}
    insurance_type = data.get("insurance_type")
    if not insurance_type:
        state["dynamic_requirements"] = []
        state["dynamic_missing"] = []
        return state
    context = build_dynamic_context(state)
    state["rag_status"] = context.get("status", "UNKNOWN")
    state["dynamic_requirements"] = context.get("requirements", [])
    state["knowledge_context"] = context
    if not context.get("available", False):
        state["dynamic_missing"] = [{"key": "__rag_unavailable__", "label": "claim-specific knowledge retrieval", "required": True}]
        state["missing_evidence"] = []
        state["conversation_status"] = "waiting_for_knowledge"
        return state
    extract_answers(state)
    if state.get("confirmed") and (state.get("dynamic_missing") or state.get("missing_evidence")):
        state["conversation_status"] = "collecting_dynamic"
    return state


def _response_planner(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state
    missing = list(state.get("missing_fields", []))
    data = state.get("extracted_data", {})
    dynamic_missing = list(state.get("dynamic_missing", []))
    missing_evidence = list(state.get("missing_evidence") or [])
    
    # Stage 1 complete -> Baseline Confirmation Prompt
    if state.get("awaiting_confirmation") and not state.get("confirmed") and not missing:
        state["next_question_field"] = "confirmation"
        state["next_question"] = nodes._confirmation_summary(data) + " Is everything correct?"
        state["message"] = state["next_question"]
        return state

    if state.get("rag_status") not in {None, "OK", "NO_INSURANCE_TYPE"} and not missing and not state.get("dynamic_requirements"):
        state["next_question_field"] = "knowledge"
    elif missing:
        state["next_question_field"] = missing[0]
    elif dynamic_missing:
        state["next_question_field"] = dynamic_missing[0].get("key")
    elif missing_evidence:
        state["next_question_field"] = "evidence:" + str(missing_evidence[0].get("key"))
    else:
        state["next_question_field"] = "final_confirmation"

    if state.get("rag_status") not in {None, "OK", "NO_INSURANCE_TYPE"} and not missing and not state.get("dynamic_requirements"):
        state["next_question"] = "I have the baseline claim details. I’m checking the claim-specific policy requirements before we continue."
    else:
        state["next_question"] = _model_response(state)

    # Safety Guard: Never ask for final adjuster submission if dynamic fields or evidence are still pending
    if (dynamic_missing or missing_evidence) and not missing:
        resp_low = state["next_question"].lower()
        if (
            state["next_question"] == _natural_fallback(missing, data)
            or any(term in resp_low for term in ("submit this claim", "submit your claim", "claims adjuster", "ready to submit"))
        ):
            state["next_question"] = _dynamic_fallback(state)
    elif missing_evidence and not dynamic_missing and not missing:
        item = missing_evidence[0]
        if not state["next_question"] or state["next_question"] == _natural_fallback(missing, data):
            state["next_question"] = f"Please upload the {str(item.get('label', 'supporting document')).lower()} when you have it, and then we can continue."

    state["message"] = state["next_question"]
    return state


def _build_conversation_graph():
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("conversation_turn_processor", conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("dynamic_requirement_enrichment", _dynamic_requirement_enrichment)
    graph.add_node("next_question_generator", _response_planner)
    graph.set_entry_point("conversation_turn_processor")
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda state: "done" if state.get("_skip_all") else "continue",
        {"continue": "claim_extractor", "done": END},
    )
    graph.add_edge("claim_extractor", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "dynamic_requirement_enrichment")
    graph.add_edge("dynamic_requirement_enrichment", "next_question_generator")
    graph.add_edge("next_question_generator", END)
    return graph.compile()


_conversation_graph = _build_conversation_graph()


def build_conversation_graph():
    """Return the compiled LangGraph conversation graph singleton."""
    return _conversation_graph


def build_intake_graph():
    """Backward-compatibility alias for build_conversation_graph. Prefer that name."""
    return _conversation_graph


__all__ = ["build_intake_graph", "build_conversation_graph"]
