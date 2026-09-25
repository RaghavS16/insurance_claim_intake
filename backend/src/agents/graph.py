"""LangGraph orchestration for the conversational claim intake agent."""
from __future__ import annotations

from typing import Any
import hashlib
import json

from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor
from src.agents.dynamic_requirements import build_dynamic_context, extract_answers, missing_evidence, pending_evidence_review


from src.agents.gap_analysis import analyze_claim_gaps

_RESPONSE_SYSTEM_PROMPT = """You are an intelligent, empathetic conversational AI dialogue agent for insurance claims intake.
You operate as a dynamic dialogue partner rather than a static or rigid Q&A chatbot.
You engage claimants in natural, flowing conversation to progressively gather, validate, and verify all required information.

The conversational flow follows this structured 5-phase progression:
1. Baseline Information Collection: Open with warm, contextual dialogue to establish rapport while collecting foundational details (policyholder identity/name, policy number, contact phone/email, incident date and time, claim category motor/property/health/travel/cyber, description narrative, location, estimated repair/loss amount). Acknowledge facts provided, respond empathetically to distress or frustration, and ask only for what is still needed.
2. Identity and Eligibility Verification: Confirm baseline facts and reassure the claimant as their policy status, coverage period, and claim eligibility are verified against underwriting records.
3. Intelligent RAG-Powered Question Generation & Real-Time Evidence Guidance: Using retrieved policy documents, claim procedures, and regulatory requirements, generate precise, context-adaptive follow-up questions tailored to their claim type (motor: accident dynamics, third-party involvement, police report/FIR, vehicle damage, drivability; property: damage cause, extent, mitigation, affected items; health: hospital admission, diagnosis, attending physician, cashless vs reimbursement). Guide users through uploading, describing, and validating required materials (photos, receipts, police reports, medical bills) in real-time, explaining why each is needed.
4. Information Validation & Gap Analysis: Continuously cross-check collected data against policy requirements and regulatory mandates, flagging inconsistencies or missing elements conversationally, and circling back smoothly to resolve gaps without restarting.
5. Adjuster-Ready Submission Package Compilation: Synthesize all verified information and guide the claimant through final confirmation for immediate adjuster review.

Conversation Design Rules:
- Speak naturally, warmly, and empathetically. Never sound like a rigid questionnaire.
- If the claimant provided multiple details at once, warmly acknowledge all of them together before asking the next question.
- If the claimant made a correction (e.g. "my policy number is POL-1409-XI"), warmly acknowledge the correction and use the updated value.
- If the claimant is frustrated or distressed, empathize first, provide reassuring clarity, and explain why the remaining detail helps their payout.
- If the claimant asks a question, answer it helpfully based on available insurance context.
- Keep voice-friendly: 1 to 3 clear, natural, reassuring sentences suitable for speech and text.
- Never output raw JSON, schemas, Python code, internal variables, or LangGraph state terms.
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
    """Safe, conversational fallback when the response model is unavailable."""
    if not missing:
        return "I have all the foundational claim details noted. Does everything look accurate so far?"
    labels = [_FIELD_LABELS[field] for field in missing if field in _FIELD_LABELS]
    if len(missing) >= 5 and not data:
        return (
            "I'm here to help you file your claim quickly and smoothly. Tell me what happened, "
            "when and where it occurred, your policy number, and any initial loss or repair estimate."
        )
    if len(labels) == 1:
        return f"To help us verify your coverage, could you share {labels[0]} whenever you're ready?"
    if len(labels) == 2:
        return f"I've noted what you've shared. Could you also share {labels[0]} and {labels[1]}?"
    return f"I've recorded those details. When you have a moment, could you also tell me {', '.join(labels[:2])}?"


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
    gap_data = state.get("gap_analysis") or analyze_claim_gaps(state)
    sentiment = gap_data.get("user_sentiment", "normal")
    phase = state.get("conversation_phase", "1_baseline")

    prompt = (
        f"{_RESPONSE_SYSTEM_PROMPT}\n\n"
        f"Active Intake Phase: {phase}\n"
        f"Authoritative claim facts: {data}\n"
        f"Still-needed baseline information: {missing}\n"
        f"Still-needed claim-specific information: {dynamic_missing}\n"
        f"Still-needed evidence uploads: {missing_evidence_items}\n"
        f"Detected claimant sentiment: {sentiment}\n"
        f"Identified gaps / consistency notes: {gap_data.get('flagged_gaps', [])}\n"
        f"Grounding context: {_compact_knowledge_context(state.get('knowledge_context', {}))}\n"
        f"Current conversation status: {state.get('conversation_status', 'collecting')}\n"
        f"Latest detected intent: {state.get('last_intent', 'unclear')}\n"
        f"Latest claimant utterance: {state.get('last_user_utterance', '')}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        "Write 1 to 3 clear, warm, and natural conversational sentences suitable for speech and text."
    )
    try:
        response = _message_text(
            nodes.invoke_with_retry(
                lambda: nodes._get_llm().invoke(prompt),
                operation_name="conversational response planning",
                attempts=1,
            )
        )
        if _response_is_usable(response, missing, data):
            return response
    except Exception as exc:
        nodes.logger.warning("Conversational response planning failed: %s", exc)
    if dynamic_missing or missing_evidence_items:
        return _dynamic_fallback(state)
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
        hint = first_ev.get("question_hint")
        if hint:
            return str(hint).strip()
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
        state["pending_evidence_review"] = []
        state["rag_status"] = "WAITING_FOR_BASELINE_CONFIRMATION"
        state["conversation_phase"] = "2_verification" if state.get("awaiting_confirmation") else "1_baseline"
        state["conversation_status"] = "reviewing" if state.get("awaiting_confirmation") else "collecting"
        return state

    policy_verification = state.get("policy_verification")
    if isinstance(policy_verification, dict) and not policy_verification.get("valid"):
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["pending_evidence_review"] = []
        state["rag_status"] = "POLICY_VERIFICATION_FAILED"
        state["conversation_phase"] = "2_verification"
        state["conversation_status"] = "verification_failed"
        return state
    if not isinstance(policy_verification, dict) or not policy_verification.get("valid"):
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["pending_evidence_review"] = []
        state["rag_status"] = "WAITING_FOR_POLICY_VERIFICATION"
        state["conversation_phase"] = "2_verification"
        state["conversation_status"] = "pending_verification"
        return state

    data = state.get("extracted_data") or {}
    insurance_type = data.get("insurance_type")
    if not insurance_type:
        state["dynamic_requirements"] = []
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["pending_evidence_review"] = []
        state["rag_status"] = "NO_INSURANCE_TYPE"
        return state

    # Bump when requirement-planning workflow semantics change so claims do not
    # reuse a stale RAG plan generated under an older intake context.
    context_payload = {
        "facts": data,
        "evidence": [
            {
                "evidence_key": item.get("evidence_key"),
                "verification_status": item.get("verification_status"),
                "detected_document_type": item.get("detected_document_type"),
            }
            for item in (state.get("evidence") or [])
        ],
    }
    context_digest = hashlib.sha256(
        json.dumps(context_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:24]
    context_key = f"intake-channel-v3|{context_digest}"
    if (
        state.get("rag_context_key") == context_key
        and state.get("rag_status") in {"OK", "PROVISIONAL"}
        and state.get("dynamic_requirements")
    ):
        extract_answers(state)
        if state.get("confirmed") and (
            state.get("dynamic_missing") or state.get("missing_evidence")
        ):
            state["conversation_phase"] = "3_rag_intake"
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
        state["pending_evidence_review"] = []
        state["conversation_status"] = "waiting_for_knowledge"
        return state

    extract_answers(state)
    state["pending_evidence_review"] = pending_evidence_review(state)
    if state.get("confirmed") and (
        state.get("dynamic_missing") or state.get("missing_evidence")
    ):
        state["conversation_phase"] = "3_rag_intake"
        state["conversation_status"] = "collecting_dynamic"
    elif state.get("confirmed"):
        state["conversation_phase"] = "4_gap_analysis"
        state["conversation_status"] = "final_review"
    return state


def _response_planner(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    missing = list(state.get("missing_fields", []))
    data = state.get("extracted_data", {})
    dynamic_missing = list(state.get("dynamic_missing", []))
    missing_evidence = list(state.get("missing_evidence") or [])
    pending_review = list(state.get("pending_evidence_review") or [])
    plan_ready = bool(state.get("dynamic_requirements")) and state.get("rag_status") in {"OK", "PROVISIONAL"}

    # Continuous Gap & Validation Analysis
    gaps_result = analyze_claim_gaps(state)
    state["gap_analysis"] = gaps_result

    if state.get("awaiting_confirmation") and not state.get("confirmed") and not missing:
        state["conversation_phase"] = "2_verification"
        state["next_question_field"] = "confirmation"
        state["next_question"] = nodes._confirmation_summary(data) + " Is everything correct?"
        state["conversation_status"] = "reviewing"
        state["message"] = state["next_question"]
        return state

    if state.get("confirmed") and not missing and not plan_ready:
        state["conversation_phase"] = "3_rag_intake"
        state["conversation_status"] = "waiting_for_knowledge"
        state["next_question_field"] = "knowledge"
        status = state.get("rag_status")
        if status == "LLM_CONFIGURATION_UNAVAILABLE":
            state["next_question"] = (
                "Thanks, the basic details are verified. The claim-specific guidance service is not configured yet. "
                "I’ll keep your verified details safely saved so we can continue once that service is available."
            )
        elif status == "LLM_TEMPORARILY_UNAVAILABLE":
            state["next_question"] = (
                "Thanks, the basic details are verified. I’m continuing with the claim-specific details now."
            )
        elif status == "REQUIREMENT_PLAN_UNAVAILABLE":
            state["next_question"] = (
                "Thanks, the basic details are verified. I’ll continue with the claim-specific review as soon as the "
                "applicable requirements are available."
            )
        elif status == "NO_RELEVANT_KNOWLEDGE":
            state["next_question"] = (
                "Thanks, the basic details are verified. I’ll continue with the claim-specific review using the "
                "available claim guidance."
            )
        else:
            state["next_question"] = (
                "Thanks, the basic details are verified. Let’s continue with the claim-specific details."
            )
        state["message"] = state["next_question"]
        return state

    if missing:
        state["conversation_phase"] = "1_baseline"
        state["next_question_field"] = missing[0]
        state["next_question"] = _natural_fallback(missing, data)
    elif dynamic_missing:
        state["conversation_phase"] = "3_rag_intake"
        state["next_question_field"] = dynamic_missing[0].get("key")
        state["conversation_status"] = "collecting_dynamic"
        state["next_question"] = _dynamic_fallback(state)
    elif missing_evidence:
        state["conversation_phase"] = "3_rag_intake"
        state["next_question_field"] = "evidence:" + str(missing_evidence[0].get("key"))
        state["conversation_status"] = "collecting_dynamic"
        state["next_question"] = _dynamic_fallback(state)
    else:
        state["conversation_phase"] = "4_gap_analysis"
        state["next_question_field"] = "final_confirmation"

    if (
        state.get("confirmed")
        and not missing
        and plan_ready
        and state.get("rag_status") == "OK"
        and not dynamic_missing
        and not missing_evidence
    ):
        if state.get("awaiting_submission_confirmation"):
            if state.get("last_intent") == "confirmation":
                state["final_submission_confirmed"] = True
                state["awaiting_submission_confirmation"] = False
                state["conversation_phase"] = "5_completed"
                state["conversation_status"] = "submitting"
                state["next_question"] = "Thanks. I'll compile your adjuster-ready submission package and submit the completed claim now."
            elif state.get("last_intent") == "rejection":
                state["final_submission_confirmed"] = False
                state["awaiting_submission_confirmation"] = False
                state["conversation_phase"] = "4_gap_analysis"
                state["conversation_status"] = "final_review"
                state["next_question"] = "No problem at all. Tell me what you'd like to adjust or add before I submit it."
            else:
                state["final_submission_confirmed"] = False
                state["conversation_phase"] = "4_gap_analysis"
                state["next_question"] = (
                    "I've collected and verified all the required information and evidence for your claim. "
                    "Would you like me to submit your complete dossier directly to the adjuster?"
                )
        else:
            state["final_submission_confirmed"] = False
            state["awaiting_submission_confirmation"] = True
            state["conversation_phase"] = "4_gap_analysis"
            state["conversation_status"] = "final_review"
            state["next_question"] = (
                "I've assembled all the required claim-specific details and evidence. "
                "Would you like me to submit the claim package to the claims adjuster?"
            )
        state["message"] = state["next_question"]
        return state

    if pending_review and not missing_evidence and not dynamic_missing:
        state["conversation_phase"] = "3_rag_intake"
        state["conversation_status"] = "collecting_dynamic"
        state["next_question_field"] = "evidence_review"
        state["next_question"] = _dynamic_fallback({**state, "missing_evidence": []}) if state.get("dynamic_requirements") else "Your uploaded evidence is queued for review. We can continue with the remaining claim details while that review is completed."
        state["message"] = state["next_question"]
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
