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
