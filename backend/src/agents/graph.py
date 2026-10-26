"""LangGraph orchestration for the conversational claim intake agent."""
from __future__ import annotations

from typing import Any
import re
import hashlib
import json

from langgraph.graph import END, StateGraph

from src.agents import nodes
from src.agents.state import ClaimState
from src.agents.turn_guard import conversation_turn_processor
from src.knowledge.retriever import KnowledgeRetriever
from src.agents.dynamic_requirements import build_dynamic_context, extract_answers, missing_evidence, pending_evidence_review


from src.agents.gap_analysis import analyze_claim_gaps


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




def _looks_like_question(state: ClaimState) -> bool:
    text = str(state.get("last_user_utterance") or "").strip().lower()
    intent = str(state.get("last_intent") or "").lower()
    if intent in {"question", "repeat"}:
        return True
    return bool(
        re.match(
            r"^(what|why|how|when|where|who|whose|which|can|could|would|will|should|do|does|did|is|are|am|was|were|may|might|tell me|explain)\b",
            text,
        )
        or re.search(r"\?\s*$", text)
    )


def _claim_intake_context_requested(state: ClaimState) -> bool:
    text = str(state.get("last_user_utterance") or "").lower()
    return bool(
        re.search(
            r"\b(file|filing|claim|submit|submission|procedure|process|document|documents|upload|evidence|report|reimburse|reimbursement|cashless|coverage|eligible|eligibility|next step|what do i need)\b",
            text,
        )
        or state.get("recently_extracted_fields")
        or state.get("confirmed")
        or state.get("dynamic_requirements")
    )


def _single_intake_follow_up(state: ClaimState) -> str:
    dynamic = list(state.get("dynamic_missing") or [])
    if dynamic:
        hint = dynamic[0].get("question_hint")
        if hint:
            return str(hint).strip()
        label = str(dynamic[0].get('label') or dynamic[0].get('key') or 'the next required detail').lower()
        return f"Could you provide {label}?"
    evidence = list(state.get("missing_evidence") or [])
    if evidence:
        hint = evidence[0].get("question_hint")
        if hint:
            return str(hint).strip()
        return f"Please upload {str(evidence[0].get('label') or 'the required supporting document').lower()} when ready."
    missing = list(state.get("missing_fields") or [])
    if missing:
        f = missing[0]
        label = "policy number" if f in ("policy_id", "policy_number") else f.replace("_", " ")
        return f"Could you provide your {label}?"
    return ""


def _confirmation_summary(data: dict[str, Any]) -> str:
    """Produce a compact dynamic summary for explicit claimant confirmation."""
    parts = []
    for key, value in data.items():
        if value not in (None, "", "UNKNOWN") and not key.startswith("_"):
            label = key.replace("_", " ").title()
            parts.append(f"{label}: {value}")
    return "Here is the claim summary: " + "; ".join(parts[:8]) + "." if parts else "Here is the current claim summary."


def _rag_question_responder(state: ClaimState) -> ClaimState:
    state["rag_answer"] = ""
    state["rag_answer_sources"] = []
    state["rag_answer_grounded"] = False
    state["rag_answer_query"] = ""
    state["rag_answer_status"] = None
    state["_rag_question_only"] = False

    if state.get("_skip_all") or not _looks_like_question(state):
        return state

    prior_rag = state.get("rag_reply")
    if isinstance(prior_rag, dict) and prior_rag.get("answer"):
        state["rag_answer"] = str(prior_rag.get("answer") or "").strip()
        state["rag_answer_sources"] = list(prior_rag.get("sources") or [])
        state["rag_answer_grounded"] = bool(prior_rag.get("grounded", True))
        state["rag_answer_query"] = str(prior_rag.get("query") or state.get("last_user_utterance") or "").strip()
        state["rag_answer_status"] = prior_rag.get("status") or "OK"
        state["_rag_question_only"] = not _claim_intake_context_requested(state)
        return state

    from datetime import date

    data = state.get("extracted_data") or {}
    incident_date = None
    try:
        if data.get("event_date"):
            incident_date = date.fromisoformat(str(data.get("event_date")))
    except ValueError:
        incident_date = None

    query = str(state.get("last_user_utterance") or "").strip()
    if not query:
        return state

    try:
        result = KnowledgeRetriever().answer_query(
            query=query,
            insurance_type=data.get("insurance_type"),
            policy_number=data.get("policy_id"),
            incident_date=incident_date,
            claim_facts=data,
            tenant_id=state.get("tenant_id"),
            jurisdiction=state.get("jurisdiction"),
        )
        state["rag_answer"] = str(result.get("answer") or "").strip()
        state["rag_answer_sources"] = list(result.get("sources") or [])
        state["rag_answer_grounded"] = bool(result.get("grounded"))
        state["rag_answer_query"] = query
        state["rag_answer_status"] = result.get("status")
    except Exception as exc:
        nodes.logger.warning("Claimant RAG question answering failed: %s", exc)
        state["rag_answer"] = (
            "I can help with that, but the insurance knowledge service is temporarily unavailable. "
            "I won't guess at policy-specific details."
        )
        state["rag_answer_status"] = "LLM_TEMPORARILY_UNAVAILABLE"

    # Pure Q&A should not invoke the more expensive dynamic requirement planner.
    # Filing/process questions continue through intake in the same turn.
    state["_rag_question_only"] = not _claim_intake_context_requested(state)
    return state


def _dynamic_fallback(state: ClaimState) -> str:
    remaining = state.get("dynamic_missing") or []
    missing_ev = state.get("missing_evidence") or []
    data = state.get("extracted_data") or {}
    recent = state.get("recently_extracted_fields") or []
    last_intent = str(state.get("last_intent") or "").lower()
    prefix = "Got it, I've noted that. " if (recent and last_intent in {"claim_detail", "greeting", "confirmation", "filler", "unclear"}) else ""
    if remaining:
        first = remaining[0]
        hint = str(first.get("question_hint") or f"Could you provide your {first.get('label', 'details').lower()}?").strip()
        return f"{prefix}{hint}" if prefix and not hint.lower().startswith("got it") else hint
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

    data = state.get("extracted_data") or {}
    previous_requirements = list(state.get("dynamic_requirements") or [])
    previous_knowledge = state.get("knowledge_context") or {}
    previous_rag_status = str(state.get("rag_status") or "")

    # Re-plan when claim facts, query, or policy context change
    planning_fact_keys = tuple(sorted(data.keys()))
    context_payload = {
        "facts": {
            key: data.get(key)
            for key in planning_fact_keys
            if data.get(key) not in (None, "", "UNKNOWN") and not key.startswith("_")
        },
        "query": str(state.get("last_user_utterance") or "")[:200],
    }
    context_digest = hashlib.sha256(
        json.dumps(context_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:24]
    context_key = f"intake-channel-v5|{context_digest}"

    if (
        state.get("rag_context_key") == context_key
        and state.get("rag_status") in {"OK", "PROVISIONAL"}
        and state.get("dynamic_requirements")
    ):
        extract_answers(state)
        state["pending_evidence_review"] = pending_evidence_review(state)
        if state.get("dynamic_missing") or state.get("missing_evidence") or state.get("pending_evidence_review"):
            state["conversation_phase"] = "source_of_truth_intake"
            state["conversation_status"] = "collecting"
        return state
    if state.get("_rag_question_only") and not _claim_intake_context_requested(state):
        return state

    context = build_dynamic_context(state)
    state["rag_status"] = context.get("status", "UNKNOWN")
    state["dynamic_requirements"] = context.get("requirements", [])
    state["knowledge_context"] = context
    state["rag_context_key"] = context_key

    if not context.get("available", False):
        if previous_requirements and previous_rag_status in {"OK", "PROVISIONAL"}:
            state["dynamic_requirements"] = previous_requirements
            state["knowledge_context"] = previous_knowledge
            state["rag_status"] = previous_rag_status
            extract_answers(state)
            state["pending_evidence_review"] = pending_evidence_review(state)
            state["conversation_status"] = "collecting"
            state["conversation_phase"] = "source_of_truth_intake"
            return state
        state["dynamic_missing"] = []
        state["missing_evidence"] = []
        state["pending_evidence_review"] = []
        state["conversation_status"] = "waiting_for_knowledge"
        state["conversation_phase"] = "source_of_truth_intake"
        return state

    extract_answers(state)
    state["pending_evidence_review"] = pending_evidence_review(state)
    if state.get("dynamic_missing") or state.get("missing_evidence"):
        state["conversation_phase"] = "source_of_truth_intake"
        state["conversation_status"] = "collecting"
    elif not state.get("dynamic_missing") and not state.get("missing_evidence"):
        state["conversation_phase"] = "gap_analysis"
        state["conversation_status"] = "ready_for_submission"
    return state


def _response_planner(state: ClaimState) -> ClaimState:
    if state.get("_skip_all"):
        return state

    data = state.get("extracted_data", {})
    dynamic_missing = list(state.get("dynamic_missing", []))
    missing_evidence = list(state.get("missing_evidence") or [])
    pending_review = list(state.get("pending_evidence_review") or [])
    requirements = list(state.get("dynamic_requirements") or [])
    rag_status = str(state.get("rag_status") or "")
    policy_id = data.get("policy_id") or data.get("policy_number")
    policy_valid = state.get("policy_valid")

    # Continuous Gap & Validation Analysis
    gaps_result = analyze_claim_gaps(state)
    state["gap_analysis"] = gaps_result

    # 1. If policy verification failed, report it clearly and do not proceed
    if policy_id and policy_valid is False:
        state["conversation_phase"] = "policy_verification"
        state["conversation_status"] = "verification_failed"
        verif = state.get("policy_verification") or {}
        reason = verif.get("reason")
        if reason == "ownership_mismatch":
            msg = f"The policy number '{policy_id}' does not match your registered user account. Please provide your correct policy number."
        elif reason == "policy_not_found":
            msg = f"I could not find policy '{policy_id}' in our records. Please verify the policy number and try again."
        elif reason == "policy_expired":
            msg = f"Policy '{policy_id}' has expired. Please check your policy status or provide an active policy number."
        elif reason == "policy_inactive":
            msg = f"Policy '{policy_id}' is currently inactive. Please check your policy status or provide an active policy number."
        else:
            msg = f"The policy number '{policy_id}' could not be verified ({reason or 'verification failed'}). Please provide a valid policy number."
        state["next_question_field"] = "policy_id"
        state["next_question"] = msg
        state["message"] = msg
        return state

    # 2. Claimant Q&A answer takes precedence if present
    rag_answer = str(state.get("rag_answer") or "").strip()
    if rag_answer:
        reply = rag_answer
        has_loss_facts = bool(data.get("event_date") or data.get("event_location") or data.get("estimated_claim_amount"))
        if _claim_intake_context_requested(state) and (has_loss_facts or state.get("confirmed")):
            follow_up = _single_intake_follow_up(state)
            if follow_up and follow_up.lower() not in reply.lower():
                reply = f"{reply}\n\n{follow_up}"
        elif not has_loss_facts and not state.get("confirmed"):
            if "file a claim" not in reply.lower() and "claim intake" not in reply.lower():
                reply = f"{reply}\n\nIf you would like to start filing a claim, please share your policy number and tell me what happened."
        state["next_question_field"] = "question"
        state["next_question"] = reply
        state["message"] = reply
        state["conversation_phase"] = "source_of_truth_intake" if (dynamic_missing or missing_evidence) else "gap_analysis"
        return state

    # 2b. Context resolution required when neither policy_number nor insurance_type is known yet
    if not requirements and rag_status == "CONTEXT_RESOLUTION_REQUIRED":
        state["conversation_phase"] = "source_of_truth_intake"
        state["conversation_status"] = "collecting"
        ctx_q = (state.get("knowledge_context") or {}).get("question") or (
            "Could you provide your policy number or specify what type of policy "
            "(e.g., motor, health, home, travel) you are filing a claim for?"
        )
        state["next_question_field"] = "policy_id"
        state["next_question"] = ctx_q
        state["message"] = ctx_q
        return state

    # 3. Honest fallback if the knowledge base has no requirements or LLM is unavailable
    if not requirements and rag_status in {
        "NO_RELEVANT_KNOWLEDGE",
        "REQUIREMENT_PLAN_UNAVAILABLE",
        "POLICY_REQUIREMENT_MANIFEST_UNAVAILABLE",
        "NO_POLICY_WORDING",
        "LLM_TEMPORARILY_UNAVAILABLE",
    }:
        state["conversation_phase"] = "source_of_truth_intake"
        state["conversation_status"] = "waiting_for_knowledge"
        if rag_status == "LLM_TEMPORARILY_UNAVAILABLE":
            reply = (
                "Our AI analysis service is temporarily unavailable. No filing requirements have been invented. "
                "You can save your draft claim now and request adjuster follow-up, or try again shortly."
            )
        elif rag_status == "REQUIREMENT_PLAN_UNAVAILABLE":
            reply = (
                "I cannot determine the filing requirements for this claim because the applicable policy wording "
                "and regulatory guidelines have not been indexed in our knowledge base. I have flagged this for an "
                "administrator or claims specialist to review and index the necessary policy documentation."
            )
        else:
            reply = (
                "I cannot determine the filing requirements for this claim because the applicable policy wording "
                "and regulatory guidelines have not been indexed in our knowledge base. No filing requirements have been invented. "
                "You can save this draft and request adjuster follow-up to proceed."
            )
        state["next_question_field"] = "escalate"
        state["next_question"] = reply
        state["message"] = reply
        return state

    # 4. Dynamic requirements intake
    if dynamic_missing:
        state["conversation_phase"] = "source_of_truth_intake"
        state["next_question_field"] = dynamic_missing[0].get("key")
        state["conversation_status"] = "collecting_dynamic"
        state["next_question"] = _dynamic_fallback(state)
    elif missing_evidence:
        state["conversation_phase"] = "source_of_truth_intake"
        state["next_question_field"] = "evidence:" + str(missing_evidence[0].get("key"))
        state["conversation_status"] = "collecting_dynamic"
        state["next_question"] = _dynamic_fallback(state)
    elif pending_review:
        state["conversation_phase"] = "source_of_truth_intake"
        state["conversation_status"] = "collecting"
        state["next_question_field"] = "evidence_review"
        state["next_question"] = "Your uploaded evidence is queued for review. There are no other claim details needed from you right now; we’ll keep the claim open until that review is resolved."
    else:
        state["conversation_phase"] = "gap_analysis"
        state["next_question_field"] = "submission"
        if state.get("final_submission_confirmed"):
            state["conversation_status"] = "submission_requested"
            state["awaiting_submission_confirmation"] = False
            state["next_question"] = ""
        elif state.get("submit_requested"):
            state["conversation_status"] = "awaiting_submission_confirmation"
            state["awaiting_submission_confirmation"] = True
            state["final_submission_confirmed"] = False
            state["next_question"] = (
                _confirmation_summary(data)
                + " Please review this summary and say “confirm and submit” when everything is correct."
            )
        else:
            state["conversation_status"] = "ready_for_submission"
            state["awaiting_submission_confirmation"] = False
            state["next_question"] = (
                "I have the required claim details and evidence, and the policy check is complete. "
                "Your claim is ready whenever you want to submit it."
            )

    state["message"] = state.get("next_question", "")
    return state


def _workflow_event_router(state: ClaimState) -> str:
    return "workflow_event" if state.get("_workflow_event") else "user_turn"


def _build_conversation_graph():
    graph = StateGraph(ClaimState)  # type: ignore
    graph.add_node("workflow_event_router", lambda state: state)
    graph.add_node("conversation_turn_processor", conversation_turn_processor)
    graph.add_node("dynamic_requirement_enrichment", _dynamic_requirement_enrichment)
    graph.add_node("claim_extractor", nodes.claim_extractor)
    graph.add_node("mandatory_field_checker", nodes.mandatory_field_checker)
    graph.add_node("rag_question_responder", _rag_question_responder)
    graph.add_node("next_question_generator", _response_planner)
    graph.set_entry_point("workflow_event_router")
    graph.add_conditional_edges(
        "workflow_event_router",
        _workflow_event_router,
        {"user_turn": "conversation_turn_processor", "workflow_event": "dynamic_requirement_enrichment"},
    )
    graph.add_conditional_edges(
        "conversation_turn_processor",
        lambda state: "done" if state.get("_skip_all") else "continue",
        {"continue": "claim_extractor", "done": END},
    )
    graph.add_edge("claim_extractor", "dynamic_requirement_enrichment")
    graph.add_edge("dynamic_requirement_enrichment", "mandatory_field_checker")
    graph.add_edge("mandatory_field_checker", "rag_question_responder")
    graph.add_edge("rag_question_responder", "next_question_generator")
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
