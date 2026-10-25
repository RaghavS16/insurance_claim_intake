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
    is_info_query = bool(re.search(
        r"\b(details?\s+require|explain\s+filing|how\s+to\s+apply|how\s+to\s+file|what\s+documents|waiting\s+period|settlement\s+timeline)\b",
        low,
    ))
    return ChatIntent(
        is_question=_clean(text).endswith("?") or bool(QUESTION_RE.search(_clean(text))) or is_info_query,
        is_claim_input=bool(re.search(
            r"\b(accident|claim|damage|hospital|medical|illness|stolen|fire|flood|injur|policy|loss|"
            r"repair|bill|invoice|incident|happened|occurred|treatment|surgery)\b", low
        )),
        wants_to_file=bool(re.search(r"\b(file|submit|make|report|open|register)\b.*\b(claim|insurance)\b", low)),
        wants_status=bool(re.search(r"\b(track|status|where is|update on)\b.*\b(claim|case)\b", low)),
        wants_policy_explanation=bool(re.search(
            r"\b(policy|coverage|covered|excluded|deductible|waiting period|procedure|documents|required)\b", low
        )) or is_info_query,
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


def infer_insurance_type_from_text(text: str) -> Optional[str]:
    low = (text or "").lower()
    if any(k in low for k in ("senior citizen", "senior_citizen", "senior health", "elderly", "geriatric", "60-75", "60–75")):
        return "senior_health"
    if any(k in low for k in ("motor", "vehicle", "car", "bike", "two-wheeler", "accident", "bumper", "collision", "windshield", "driver")):
        return "motor"
    if any(k in low for k in ("health", "hospital", "medical", "doctor", "cashless", "tpa", "illness", "surgery", "patient", "admission")):
        return "health"
    if any(k in low for k in ("home", "property", "house", "dwelling", "griha", "leak", "flood", "burglary")):
        return "home"
    if any(k in low for k in ("travel", "flight", "baggage", "trip", "passport")):
        return "travel"
    if any(k in low for k in ("cyber", "ransomware", "phishing", "data breach", "hack", "fraudulent transaction")):
        return "cyber"
    return None


def retrieve_for_chat(text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    facts = dict(state.get("extracted_data") or {})
    insurance_type = facts.get("insurance_type") or state.get("insurance_type_hint") or state.get("insurance_type")
    if not insurance_type and text:
        from src.knowledge.retriever import infer_insurance_type_from_query
        insurance_type = infer_insurance_type_from_text(text) or infer_insurance_type_from_query(text)
    if insurance_type:
        state["insurance_type"] = insurance_type

    incident_date = None
    if facts.get("event_date"):
        try:
            from datetime import date
            incident_date = date.fromisoformat(str(facts["event_date"]))
        except ValueError:
            pass

    search_query = text or ""
    low_text = search_query.lower()
    if any(w in low_text for w in ("apply", "new policy", "application", "buy", "proposal", "kyc")):
        search_query += " Section 5 How to Apply Application Process Section 5.4 Documents Required for New Policy Application KYC"
    elif any(w in low_text for w in ("file", "filing", "claim process", "how to claim", "documents required", "checklist")):
        search_query += " Section 6 How to File a Claim Step-by-Step Section 6.3 IRDAI Timelines Section 6.5 Information Required Section 6.6 Mandatory Documents"

    tenant_id = state.get("tenant_id") or "00000000-0000-0000-0000-000000000001"
    jurisdiction = state.get("jurisdiction") or "India"

    if insurance_type:
        try:
            return KnowledgeRetriever().retrieve(
                insurance_type=str(insurance_type),
                policy_number=facts.get("policy_id"),
                incident_date=incident_date,
                query=search_query,
                intake_channel="claimant_chat",
                claim_facts=facts,
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
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
        policy = search(
            search_query,
            document_types=["policy_wording"],
            limit=8,
            tenant_id=tenant_id,
            jurisdiction=jurisdiction,
        )
        guidance = search(
            search_query,
            document_types=["regulation", "guideline", "claim_requirement", "policy_regulatory"],
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

    for model_getter in (get_reasoning_llm, get_fast_llm):
        try:
            result = invoke_with_retry(
                lambda: model_getter().invoke(prompt),
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
            if answer and sources:
                labels = []
                for source in sources[:4]:
                    label = str(source.get("citation_label") or "").strip()
                    if not label:
                        name = str(source.get("source_name") or "Source").strip()
                        page = source.get("page_number")
                        label = f"{name}, p.{page}" if page else name
                    if label and label not in labels:
                        labels.append(label)
                if labels and not any(label.lower() in answer.lower() for label in labels):
                    answer = f"{answer.rstrip()}\n\nSources: " + "; ".join(labels)
                return answer
        except Exception:
            continue

    return _synthesize_structured_answer_from_chunks(text, sources, requirements)


def _synthesize_structured_answer_from_chunks(
    question: str,
    sources: list[dict[str, Any]],
    requirements: list[dict[str, Any]] | None = None,
) -> str:
    """Deterministic section-grounded synthesizer used when LLM is offline or timed out."""
    if not sources:
        if requirements:
            labels = [
                str(r.get("label") or r.get("key") or "").strip()
                for r in requirements[:5]
                if r.get("label") or r.get("key")
            ]
            if labels:
                return "Based on policy guidelines, the following claim details are required: " + ", ".join(labels) + "."
        return (
            "I can help with the claim and explain the filing process, but I don't have a relevant policy or procedure "
            "document indexed for that question yet. Please link the applicable policy or provide the insurer guidance, "
            "and I'll use it to answer."
        )

    low_q = question.lower()
    top_source = sources[0]
    txt = str(top_source.get("text") or "")
    source_name = str(top_source.get("source_name") or "Policy Guidance")
    citation = str(top_source.get("citation_label") or source_name)

    # 1. New Policy Application
    if any(w in low_q for w in ("apply", "application", "buy", "proposal", "kyc", "documents required to apply", "details require")):
        bullets = []
        for line in txt.splitlines():
            line_str = line.strip()
            if line_str.startswith("•") or line_str.startswith("-") or "[table" in line_str.lower():
                clean_bullet = line_str.lstrip("•- ").strip()
                if clean_bullet and clean_bullet not in bullets:
                    bullets.append(clean_bullet)
        if bullets:
            body = "To apply for this policy, the following documents and details are required per official guidelines:\n" + "\n".join(f"• {b}" for b in bullets[:6])
        else:
            clean_snippet = re.sub(r"\s+", " ", txt)[:380]
            body = f"Based on {source_name}, here is the application guidance: {clean_snippet}"
        return f"{body}\n\nSources: {citation}"

    # 2. Claim Filing Process & Checklists
    if any(w in low_q for w in ("file", "filing", "claim process", "how to claim", "documents required", "checklist", "timeline", "intimation")):
        bullets = []
        for line in txt.splitlines():
            line_str = line.strip()
            if line_str.startswith("•") or line_str.startswith("-") or re.match(r"^\d+\.", line_str):
                clean_bullet = line_str.lstrip("•- ").strip()
                if clean_bullet and clean_bullet not in bullets:
                    bullets.append(clean_bullet)
        if bullets:
            body = "Based on policy guidance, here is the procedure and required documents for filing a claim:\n" + "\n".join(f"• {b}" for b in bullets[:6])
        else:
            clean_snippet = re.sub(r"\s+", " ", txt)[:380]
            body = f"Based on {source_name}, here is the claims filing guidance: {clean_snippet}"
        return f"{body}\n\nSources: {citation}"

    # 3. Exclusions, waiting periods, deductibles, general
    clean_lines = [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("###") and not ln.strip().startswith("[Table")]
    summary = " ".join(clean_lines[:4])[:450]
    return f"Based on {source_name}: {summary}\n\nSources: {citation}"


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
