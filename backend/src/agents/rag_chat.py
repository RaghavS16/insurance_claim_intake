"""Retrieval-first CLAIMANT chatbot conversation layer.

This module is intentionally NOT the adjuster AI Copilot. The adjuster Copilot lives in
`src.api.adjuster_routes` and operates only in the authenticated adjuster workbench.

The claimant experience is RAG-first:
- Answer the human's question from indexed policy/guidance when available.
- Treat a turn as potentially both a question and claim input.
- Claim intake continues in parallel; it never suppresses a direct answer.
- No unsupported policy procedure is invented when retrieval has no grounding.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field

from src.agents.llm_factory import get_fast_llm, get_reasoning_llm, invoke_with_retry, structured_output
from src.knowledge.retriever import KnowledgeRetriever


class ChatIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    is_question: bool = False
    is_claim_input: bool = False
    wants_to_file: bool = False
    wants_status: bool = False
    wants_policy_explanation: bool = False
    wants_human: bool = False


class ChatAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: str = Field(default="")
    should_continue_intake: bool = True
    suggested_follow_up: str = Field(default="")


QUESTION_RE = re.compile(
    r"(^|\s)(what|why|how|when|where|who|which|can|could|would|will|do|does|did|is|are|am|was|were|"
    r"tell me|explain|procedure|process|steps|requirements|documents|needed)(\b|\s)",
    re.I,
)


def _clean(text: str, limit: int = 1800) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _heuristic_intent(text: str) -> ChatIntent:
    low = _clean(text).lower()
    return ChatIntent(
        is_question=_clean(text).endswith("?") or bool(QUESTION_RE.search(_clean(text))),
        is_claim_input=bool(re.search(
            r"\b(accident|claim|damage|hospital|medical|illness|stolen|fire|flood|injur|policy|loss|"
            r"repair|bill|invoice|incident|happened|occurred|treatment|surgery)\b", low
        )),
        wants_to_file=bool(re.search(r"\b(file|submit|make|report|open|register)\b.*\b(claim|insurance)\b", low)),
        wants_status=bool(re.search(r"\b(track|status|where is|update on)\b.*\b(claim|case)\b", low)),
        wants_policy_explanation=bool(re.search(
            r"\b(policy|coverage|covered|excluded|deductible|waiting period|procedure|documents|required)\b", low
        )),
        wants_human=bool(re.search(r"\b(human|agent|adjuster|representative|person)\b", low)),
    )


def classify_turn(text: str, known_facts: Dict[str, Any] | None = None) -> ChatIntent:
    fallback = _heuristic_intent(text)
    try:
        prompt = (
            "Classify this claimant message. It can contain both a question and claim facts. "
            "A question must never be treated as an answer to a missing field. "
            "Return only the structured flags.\n"
            f"Known facts: {json.dumps(known_facts or {}, ensure_ascii=False, default=str)}\n"
            f"Latest message: {_clean(text)}"
        )
        result = invoke_with_retry(
            lambda: structured_output(get_fast_llm(), ChatIntent).invoke(prompt),
            operation_name="claimant turn intent classification",
            attempts=1,
        )
        return result if isinstance(result, ChatIntent) else ChatIntent.model_validate(result)
    except Exception:
        return fallback


def retrieve_for_chat(text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    facts = dict(state.get("extracted_data") or {})
    insurance_type = facts.get("insurance_type") or state.get("insurance_type_hint")
    incident_date = None
    if facts.get("event_date"):
        try:
            from datetime import date
            incident_date = date.fromisoformat(str(facts["event_date"]))
        except ValueError:
            pass

    if insurance_type:
        try:
            return KnowledgeRetriever().retrieve(
                insurance_type=str(insurance_type),
                policy_number=facts.get("policy_id"),
                incident_date=incident_date,
                query=text,
                intake_channel="claimant_chat",
                claim_facts=facts,
                tenant_id=state.get("tenant_id"),
                jurisdiction=state.get("jurisdiction"),
            )
        except Exception:
            return {
                "available": False,
                "status": "RAG_UNAVAILABLE",
                "requirements": [],
                "policy": [],
                "regulations": [],
            }

    # Before type is known, do pure semantic retrieval from the user's question.
    try:
        from src.knowledge.store import search
        tenant_id = state.get("tenant_id")
        jurisdiction = state.get("jurisdiction")
        if not tenant_id:
            return {
                "available": False,
                "status": "TENANT_CONTEXT_REQUIRED",
                "requirements": [],
                "policy": [],
                "regulations": [],
            }
        policy = search(
            text,
            document_types=["policy_wording"],
            limit=8,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
        )
        guidance = search(
            text,
            document_types=["regulation", "guideline", "claim_requirement"],
            limit=8,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
        )
        return {
            "available": bool(policy or guidance),
            "status": "OK" if (policy or guidance) else "NO_RELEVANT_KNOWLEDGE",
            "requirements": [],
            "policy": policy,
            "regulations": guidance,
            "authoritative": False,
            "planning_model": "semantic_chat_retrieval",
        }
    except Exception:
        return {
            "available": False,
            "status": "RAG_UNAVAILABLE",
            "requirements": [],
            "policy": [],
            "regulations": [],
        }


def answer_claimant_question(
    text: str,
    state: Dict[str, Any],
    retrieval: Dict[str, Any],
    intent: ChatIntent,
) -> str:
    rows = [(retrieval.get("policy") or [])[:6], (retrieval.get("regulations") or [])[:6]]
    sources = []
    for group in rows:
        for row in group:
            sources.append({
                "source_name": row.get("source_name"),
                "document_type": row.get("document_type"),
                "score": row.get("score"),
                "page_number": row.get("page_number"),
                "section_number": row.get("section_number"),
                "clause_number": row.get("clause_number"),
                "citation_label": row.get("citation_label"),
                "document_version": row.get("document_version"),
                "jurisdiction": row.get("jurisdiction"),
                "text": _clean(row.get("text"), 2600),
            })

    requirements = (retrieval.get("requirements") or [])[:20]
    prompt = (
        "You are the claimant-facing insurance assistant. Answer the claimant's actual question first. "
        "Use ONLY retrieved knowledge for policy, procedure, coverage, exclusions, deadlines, and required documents. "
        "Never invent insurer rules or benefits. If knowledge is missing, say that the applicable guidance is not "
        "currently available in the indexed knowledge base and ask for the relevant policy/guidance document. "
        "A response may also invite the claimant to continue sharing claim facts, but must not replace the answer "
        "with a generic intake question. Keep it natural, clear, and concise.\n\n"
        f"Latest claimant message: {text}\n"
        f"Known claim facts: {json.dumps(state.get('extracted_data') or {}, ensure_ascii=False, default=str)}\n"
        f"Intent: {intent.model_dump()}\n"
        f"Retrieved sources: {json.dumps(sources, ensure_ascii=False, default=str)}\n"
        f"Retrieved claim requirements: {json.dumps(requirements, ensure_ascii=False, default=str)}"
    )

    try:
        result = invoke_with_retry(
            lambda: get_reasoning_llm().invoke(prompt),
            operation_name="RAG grounded claimant response",
            attempts=1,
        )
        content = getattr(result, "content", result)
        if isinstance(content, list):
            content = " ".join(
                str(x.get("text")) if isinstance(x, dict) and x.get("text") else str(x)
                for x in content
            )
        answer = _clean(str(content))
        if answer:
            return answer
    except Exception:
        pass

    if sources:
        return _clean(
            "Based on the indexed policy/guidance, " + str(sources[0].get("text") or ""),
            1200,
        )
    if requirements:
        labels = [
            str(r.get("label") or r.get("key") or "").strip()
            for r in requirements[:5]
            if r.get("label") or r.get("key")
        ]
        if labels:
            return "For this claim, the indexed guidance indicates that we need " + ", ".join(labels) + "."
    return (
        "I can help with the claim and explain the filing process, but I don't have a relevant policy or procedure "
        "document indexed for that question yet. Please link the applicable policy or provide the insurer guidance, "
        "and I'll use it to answer."
    )


def build_claimant_response(
    text: str,
    state: Dict[str, Any],
    intent: ChatIntent | None = None,
) -> Dict[str, Any]:
    # Reuse the fast-path classifier result when the caller already has it.
    intent = intent or classify_turn(text, state.get("extracted_data") or {})
    retrieval = retrieve_for_chat(text, state)
    needs_answer = bool(
        intent.is_question
        or intent.wants_to_file
        or intent.wants_policy_explanation
        or intent.wants_status
        or intent.wants_human
    )
    answer = answer_claimant_question(text, state, retrieval, intent) if needs_answer else ""
    return {
        "intent": intent.model_dump(),
        "answer": answer,
        "retrieval": retrieval,
    }
