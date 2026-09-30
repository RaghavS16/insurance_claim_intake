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

_RESPONSE_SYSTEM_PROMPT = """You are the claimant-facing conversational AI for an insurance agency.
You are a general-purpose insurance assistant with RAG-backed claim intake.

Answer the claimant's actual question or request first. Claim intake is parallel background work, not a prerequisite for conversation.
Use retrieved policy, procedure, regulatory, and claim-guidance evidence when available. Never invent policy terms, exclusions, limits, deadlines, eligibility rules, or required documents.
When retrieved evidence is insufficient for a policy-specific answer, say so clearly instead of guessing.

When a claimant shares facts, extract and preserve them without making them repeat information already provided. When a claimant is filing a claim, use the applicable retrieved requirements to identify the next useful detail or document dynamically.
A claimant can ask questions at any point—before, during, or after intake, while documents are being reviewed, and while a claim is being prepared for submission.
Policy verification remains a workflow gate before submission; it is not a gate for answering questions.
Final submission remains a strict workflow action after required information/evidence and authoritative policy checks are satisfied.

Conversation rules:
- Be natural, concise, empathetic, and direct.
- Answer the question before asking an intake follow-up.
- Never restart the conversation or dump the full missing-field list.
- If the claimant already supplied a fact, acknowledge it and move on.
- Never expose raw JSON, schemas, Python code, internal state names, or orchestration details.
- Keep voice-friendly responses normally to 2–6 sentences.
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
    labels = {
        "policy_id": "your policy number",
        "event_date": "the incident date",
        "insurance_type": "the type of insurance",
        "event_description": "what happened",
        "event_location": "where the incident happened",
        "estimated_claim_amount": "the approximate loss or repair amount",
    }
    missing = list(state.get("missing_fields") or [])
    if missing:
        field = missing[0]
        return f"To start the claim, could you share {labels.get(field, field.replace('_', ' '))}?"
    dynamic = list(state.get("dynamic_missing") or [])
    if dynamic:
        hint = dynamic[0].get("question_hint")
        if hint:
            return str(hint).strip()
        return f"Could you provide {str(dynamic[0].get('label') or dynamic[0].get('key') or 'the next required detail').lower()}?"
    evidence = list(state.get("missing_evidence") or [])
    if evidence:
        hint = evidence[0].get("question_hint")
        if hint:
            return str(hint).strip()
        return f"Please upload {str(evidence[0].get('label') or 'the required supporting document').lower()} when ready."
    return ""


def _rag_question_responder(state: ClaimState) -> ClaimState:
    state["rag_answer"] = ""
    state["rag_answer_sources"] = []
    state["rag_answer_grounded"] = False
    state["rag_answer_query"] = ""
    state["rag_answer_status"] = None

    if state.get("_skip_all") or not _looks_like_question(state):
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
    if state.get("_skip_all") or state.get("_rag_question_only"):
        return state

    # Requirement planning is available as soon as an insurance type is known.
    # Policy verification remains a submission gate, not a conversation gate.
    if not state.get("confirmed"):
        state["conversation_phase"] = "1_baseline"

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
    # Requirement planning should be stable across ordinary claim-specific
    # answers. Re-running the reasoning model after every dynamic answer caused a
    # transient RAG failure to erase an already-valid requirement plan (for example
    # after the claimant answered an alcohol question). Re-plan only when baseline
    # claim context or evidence state changes.
    planning_fact_keys = (
        "policy_id",
        "event_date",
        "insurance_type",
        "event_description",
        "event_location",
        "estimated_claim_amount",
    )
    # Only baseline context determines the requirement plan. Answers to
    # requirements and evidence verification state must not invalidate the plan.
    context_payload = {
        "baseline_facts": {
            key: data.get(key)
            for key in planning_fact_keys
            if data.get(key) not in (None, "", "UNKNOWN")
        },
    }
    context_digest = hashlib.sha256(
        json.dumps(context_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:24]
    context_key = f"intake-channel-v4|{context_digest}"
    if (
        state.get("rag_context_key") == context_key
        and state.get("rag_status") in {"OK", "PROVISIONAL"}
        and state.get("dynamic_requirements")
    ):
        extract_answers(state)
        state["pending_evidence_review"] = pending_evidence_review(state)
        if state.get("confirmed") and (
            state.get("dynamic_missing") or state.get("missing_evidence") or state.get("pending_evidence_review")
        ):
            state["conversation_phase"] = "3_rag_intake"
            state["conversation_status"] = "collecting_dynamic"
        return state

    previous_requirements = list(state.get("dynamic_requirements") or [])
    previous_knowledge = state.get("knowledge_context") or {}
    previous_rag_status = str(state.get("rag_status") or "")
    context = build_dynamic_context(state)
    state["rag_status"] = context.get("status", "UNKNOWN")
    state["dynamic_requirements"] = context.get("requirements", [])
    state["knowledge_context"] = context
    state["rag_context_key"] = context_key

    if not context.get("available", False):
        # Never discard an already-generated requirement plan just because a later
        # RAG refresh is temporarily unavailable. This is especially important after
        # an evidence upload, where the plan itself has not changed but its
        # satisfaction state has.
        if previous_requirements and previous_rag_status in {"OK", "PROVISIONAL"}:
            state["dynamic_requirements"] = previous_requirements
            state["knowledge_context"] = previous_knowledge
            state["rag_status"] = previous_rag_status
            extract_answers(state)
            state["pending_evidence_review"] = pending_evidence_review(state)
            state["conversation_status"] = "collecting_dynamic"
            state["conversation_phase"] = "3_rag_intake"
            return state
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

    rag_answer = str(state.get("rag_answer") or "").strip()
    if rag_answer:
        reply = rag_answer
        if _claim_intake_context_requested(state):
            follow_up = _single_intake_follow_up(state)
            if follow_up and follow_up.lower() not in reply.lower():
                reply = f"{reply}\n\n{follow_up}"
        state["next_question_field"] = "question"
        state["next_question"] = reply
        state["message"] = reply
        if state.get("confirmed"):
            state["conversation_phase"] = "3_rag_intake" if (dynamic_missing or missing_evidence) else "4_gap_analysis"
        else:
            state["conversation_phase"] = "1_baseline"
        return state

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
        and not pending_review
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
        state["next_question"] = "Your uploaded evidence is queued for review. There are no other claim details needed from you right now; we’ll keep the claim open until that review is resolved."
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
    graph.add_node("rag_question_responder", _rag_question_responder)
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
    graph.add_edge("claim_extractor", "rag_question_responder")
    graph.add_edge("rag_question_responder", "mandatory_field_checker")
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
