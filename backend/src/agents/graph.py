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


def _compact_knowledge_context(context: dict[str, Any]) -> dict[str, Any]:
    """Keep conversational prompts small while preserving RAG provenance."""
    compact: dict[str, Any] = {
        "available": context.get("available", False),
        "status": context.get("status"),
        "requirements": [
            {
                k: req.get(k)
                for k in ("key", "label", "question_hint", "required", "evidence_type", "condition")
                if req.get(k) is not None
            }
            for req in (context.get("requirements") or [])
        ],
    }
    for key in ("policy", "regulations"):
        rows = []
        for row in (context.get(key) or [])[:3]:
            item = dict(row)
            item["text"] = str(item.get("text") or "")[:3500]
            rows.append(item)
        compact[key] = rows
    return compact


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

    dynamic_missing = [
        {k: item.get(k) for k in ("key", "label", "question_hint", "required", "evidence_type")}
        for item in (state.get("dynamic_missing") or [])
    ]
    missing_evidence_items = [
        {k: item.get(k) for k in ("key", "label", "question_hint", "required", "evidence_type")}
        for item in (state.get("missing_evidence") or [])
    ]
    prompt = (
        f"{_RESPONSE_SYSTEM_PROMPT}\n\n"
        f"Authoritative claim facts: {data}\n"
        f"Still-needed baseline information: {missing}\n"
        f"Still-needed claim-specific information: {dynamic_missing}\n"
        f"Still-needed evidence uploads: {missing_evidence_items}\n"
        f"Grounding context: {_compact_knowledge_context(state.get('knowledge_context', {}))}\n"
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
        return str(hint).strip()
    if missing_ev:
        first_ev = missing_ev[0]
        return f"Please upload {first_ev.get('label', 'the supporting document').lower()} when you have it so we can continue."
    return _natural_fallback(list(state.get("missing_fields", [])), data)


def _dynamic_requirement_enrichment(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    # Claim-specific RAG starts only after baseline confirmation AND successful
    # policy verification. This avoids expensive RAG/LLM work during baseline intake.
    if not state.get("confirmed"):
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["rag_status"] = "WAITING_FOR_BASELINE_CONFIRMATION"
        state["conversation_status"] = "reviewing" if state.get("awaiting_confirmation") else "collecting"
        return state

    policy_verification = state.get("policy_verification") or {}
    if policy_verification and not policy_verification.get("valid"):
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["rag_status"] = "POLICY_VERIFICATION_FAILED"
        state["conversation_status"] = "verification_failed"
        return state
    if not policy_verification.get("valid"):
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["rag_status"] = "WAITING_FOR_POLICY_VERIFICATION"
        state["conversation_status"] = "pending_verification"
        return state

    data = state.get("extracted_data") or {}
    insurance_type = data.get("insurance_type")
    if not insurance_type:
        state["dynamic_requirements"] = []
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["rag_status"] = "NO_INSURANCE_TYPE"
        return state

    context_key = "|".join(
        str(data.get(k) or "")
        for k in ("insurance_type", "policy_id", "event_date", "event_description")
    )
    if (
        state.get("rag_context_key") == context_key
        and state.get("rag_status") == "OK"
        and state.get("dynamic_requirements")
    ):
        extract_answers(state)
        if state.get("confirmed") and (
            state.get("dynamic_missing") or state.get("missing_evidence")
        ):
            state["conversation_status"] = "collecting_dynamic"
        return state

    context = build_dynamic_context(state)
    state["rag_status"] = context.get("status", "UNKNOWN")
    state["dynamic_requirements"] = context.get("requirements", [])
    state["knowledge_context"] = context
    state["rag_context_key"] = context_key

    if not context.get("available", False):
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["conversation_status"] = "waiting_for_knowledge"
        return state

    extract_answers(state)
    if state.get("confirmed") and (
        state.get("dynamic_missing") or state.get("missing_evidence")
    ):
        state["conversation_status"] = "collecting_dynamic"
    elif state.get("confirmed"):
        state["conversation_status"] = "final_review"
    return state


def _response_planner(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    missing = list(state.get("missing_fields", []))
    data = state.get("extracted_data", {})
    dynamic_missing = list(state.get("dynamic_missing", []))
    missing_evidence = list(state.get("missing_evidence") or [])
    plan_ready = bool(state.get("dynamic_requirements")) and state.get("rag_status") == "OK"

    if state.get("awaiting_confirmation") and not state.get("confirmed") and not missing:
        state["next_question_field"] = "confirmation"
        state["next_question"] = nodes._confirmation_summary(data) + " Is everything correct?"
        state["conversation_status"] = "reviewing"
        state["message"] = state["next_question"]
        return state

    if state.get("confirmed") and not missing and not plan_ready:
        state["conversation_status"] = "waiting_for_knowledge"
        state["next_question_field"] = "knowledge"
        status = state.get("rag_status")
        if status == "REQUIREMENT_PLAN_UNAVAILABLE":
            state["next_question"] = (
                "I've verified the basic claim details, but I couldn't determine the claim-specific "
                "requirements from the available policy guidance yet. The claim cannot be submitted "
                "until those requirements are available."
            )
        elif status == "NO_RELEVANT_KNOWLEDGE":
            state["next_question"] = (
                "I've verified the basic claim details, but I couldn't find applicable policy guidance "
                "for this claim yet. The claim cannot be submitted until the applicable requirements "
                "are available."
            )
        else:
            state["next_question"] = (
                "I've verified the basic claim details. I need the applicable claim requirements before "
                "we continue."
            )
        state["message"] = state["next_question"]
        return state

    if missing:
        state["next_question_field"] = missing[0]
        state["next_question"] = _natural_fallback(missing, data)
    elif dynamic_missing:
        state["next_question_field"] = dynamic_missing[0].get("key")
        state["next_question"] = _dynamic_fallback(state)
        state["conversation_status"] = "collecting_dynamic"
    elif missing_evidence:
        state["next_question_field"] = "evidence:" + str(missing_evidence[0].get("key"))
        state["next_question"] = _dynamic_fallback(state)
        state["conversation_status"] = "collecting_dynamic"
    else:
        state["next_question_field"] = "final_confirmation"

    if (
        state.get("confirmed")
        and not missing
        and plan_ready
        and not dynamic_missing
        and not missing_evidence
    ):
        if state.get("awaiting_submission_confirmation"):
            if state.get("last_intent") == "confirmation":
                state["final_submission_confirmed"] = True
                state["awaiting_submission_confirmation"] = False
                state["conversation_status"] = "submitting"
                state["next_question"] = "Thanks. I'll submit the completed claim now."
            elif state.get("last_intent") == "rejection":
                state["final_submission_confirmed"] = False
                state["awaiting_submission_confirmation"] = False
                state["conversation_status"] = "final_review"
                state["next_question"] = "No problem. Tell me what you'd like to change before I submit it."
            else:
                state["final_submission_confirmed"] = False
                state["next_question"] = (
                    "I've collected and checked everything required for this claim. "
                    "Would you like me to submit it to the adjuster?"
                )
        else:
            state["final_submission_confirmed"] = False
            state["awaiting_submission_confirmation"] = True
            state["conversation_status"] = "final_review"
            state["next_question"] = (
                "I've collected the required claim-specific information. "
                "Would you like me to submit the claim to the adjuster?"
            )
        state["message"] = state["next_question"]
        return state

    state["message"] = state.get("next_question", "")
    return state

def _workflow_event_router(state: ClaimState) -> str:
    return "workflow_event" if state.get("_workflow_event") else "user_turn"


def _build_conversation_graph():
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("workflow_event_router", lambda state: state)
    graph.add_node("conversation_turn_processor", conversation_turn_processor)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("dynamic_requirement_enrichment", _dynamic_requirement_enrichment)
    graph.add_node("next_question_generator", _response_planner)
    graph.set_entry_point("workflow_event_router")
    graph.add_conditional_edges(
        "workflow_event_router",
        _workflow_event_router,
        {"user_turn": "conversation_turn_processor", "workflow_event": "mandatory_field_checker"},
    )
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
