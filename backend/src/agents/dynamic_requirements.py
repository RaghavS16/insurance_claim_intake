"""Dynamic claim-type requirement planning and conversational extraction."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from src.agents.llm_factory import get_configured_llm
from src.knowledge.retriever import KnowledgeRetriever

class DynamicExtraction(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

def build_dynamic_context(state: dict[str, Any]) -> dict[str, Any]:
    data = state.get("extracted_data") or {}
    insurance_type = str(data.get("insurance_type") or "")
    if not insurance_type:
        return {"requirements": [], "policy": [], "regulations": []}
    return KnowledgeRetriever().retrieve(
        insurance_type=insurance_type,
        policy_number=data.get("policy_id"),
        query=str(data.get("event_description") or ""),
    )

def unresolved(state: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = state.get("dynamic_requirements") or []
    data = state.get("extracted_data") or {}
    return [r for r in requirements if r.get("required", True) and data.get(r.get("key")) in (None, "", "UNKNOWN")]

def extract_answers(state: dict[str, Any]) -> None:
    remaining = unresolved(state)
    utterance = str(state.get("last_user_utterance") or "").strip()
    if not remaining or not utterance:
        state["dynamic_missing"] = remaining
        return
    prompt = (
        "Extract only claim-specific values that are explicitly present in the latest claimant utterance. "
        "Use only the supplied requirement keys. Do not infer, invent or copy values from prior turns. "
        f"Requirements: {remaining}\nCurrent claim facts: {state.get('extracted_data', {})}\n"
        f"Latest claimant utterance: {utterance}"
    )
    try:
        result = get_configured_llm().with_structured_output(DynamicExtraction).invoke(prompt)
        values = result.model_dump().get("values", {}) if hasattr(result, "model_dump") else {}
        allowed = {r.get("key") for r in remaining}
        for key, value in values.items():
            if key in allowed and value not in (None, "", "UNKNOWN"):
                state.setdefault("extracted_data", {})[key] = value
    except Exception:
        pass
    state["dynamic_missing"] = unresolved(state)
