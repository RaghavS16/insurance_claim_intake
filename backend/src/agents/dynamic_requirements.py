"""Conversational dynamic-requirement planning."""
from __future__ import annotations
from typing import Any
from src.knowledge.retriever import KnowledgeRetriever

def build_dynamic_context(state: dict[str, Any]) -> dict[str, Any]:
    data = state.get("extracted_data") or {}
    insurance_type = str(data.get("insurance_type") or "").lower()
    if not insurance_type:
        return {"requirements": [], "sources": []}
    ctx = KnowledgeRetriever().retrieve(
        insurance_type=insurance_type,
        policy_number=data.get("policy_id"),
        query=str(data.get("event_description") or ""),
    )
    return {
        "requirements": [r.model_dump() for r in ctx.requirements.requirements],
        "sources": [s.model_dump() for s in (*ctx.policy_chunks, *ctx.regulation_chunks)],
    }

def unresolved_requirements(state: dict[str, Any]) -> list[dict[str, Any]]:
    context = state.get("dynamic_requirements") or []
    collected = state.get("extracted_data") or {}
    return [r for r in context if r.get("required") and not collected.get(r.get("key"))]


from pydantic import BaseModel, Field
from src.agents.llm_factory import get_configured_llm

class DynamicAnswerPatch(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

def extract_dynamic_answers(state: dict[str, Any]) -> dict[str, Any]:
    """Extract only values for currently unresolved claim-specific requirements."""
    unresolved = unresolved_requirements(state)
    if not unresolved:
        return state
    utterance = str(state.get("last_user_utterance") or "")
    if not utterance:
        return state
    keys = {str(r.get("key")) for r in unresolved}
    prompt = (
        "You are extracting claim-specific requirements from one claimant utterance. "
        "Use only the requirement keys supplied below. Never invent values. "
        "If the utterance does not provide a value, omit that key. "
        f"Requirement keys and descriptions: {unresolved}\n"
        f"Current claim facts: {state.get('extracted_data', {})}\n"
        f"Latest claimant utterance: {utterance}"
    )
    try:
        result = get_configured_llm().with_structured_output(DynamicAnswerPatch).invoke(prompt)
        values = getattr(result, "values", {}) or {}
        state.setdefault("extracted_data", {}).update({k: v for k, v in values.items() if k in keys and v not in (None, "")})
    except Exception:
        pass
    state["unresolved_requirements"] = unresolved_requirements(state)
    return state
