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
        return {"available": True, "status": "NO_INSURANCE_TYPE", "requirements": [], "policy": [], "regulations": []}
    incident_date = None
    try:
        from datetime import date
        incident_date = date.fromisoformat(str(data.get("event_date"))) if data.get("event_date") else None
    except ValueError:
        incident_date = None
    return KnowledgeRetriever().retrieve(
        insurance_type=insurance_type,
        policy_number=data.get("policy_id"),
        incident_date=incident_date,
        query=str(data.get("event_description") or ""),
    )

def unresolved(state: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = state.get("dynamic_requirements") or []
    data = state.get("extracted_data") or {}
    return [r for r in requirements if r.get("required", True) and data.get(r.get("key")) in (None, "", "UNKNOWN")]


def missing_evidence(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return required evidence items that have not been uploaded yet."""
    requirements = state.get("dynamic_requirements") or []
    evidence = state.get("evidence") or []
    uploaded_keys = {str(e.get("evidence_key")) for e in evidence if e.get("evidence_key")}
    return [
        r for r in requirements
        if r.get("required", True) and r.get("evidence_type") and r.get("key") not in uploaded_keys
    ]


def extract_answers(state: dict[str, Any]) -> None:
    remaining = unresolved(state)
    utterance = str(state.get("last_user_utterance") or "").strip()
    if not remaining or not utterance:
        state["dynamic_missing"] = remaining
        state["missing_evidence"] = missing_evidence(state)
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
    except Exception as exc:
        state["dynamic_extraction_error"] = type(exc).__name__
    state["dynamic_missing"] = unresolved(state)
    state["missing_evidence"] = missing_evidence(state)
