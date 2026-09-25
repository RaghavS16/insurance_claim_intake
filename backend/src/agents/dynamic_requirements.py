"""Dynamic claim-type requirement planning and conversational extraction."""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, Field
from src.agents.llm_factory import get_configured_llm, invoke_with_retry, structured_output
from src.knowledge.retriever import KnowledgeRetriever
from src.agents.state import ClaimState

class DynamicExtraction(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

def build_dynamic_context(state: ClaimState | dict[str, Any]) -> dict[str, Any]:
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
        intake_channel="insurer_web_portal",
        intake_started_at=str(state.get("claim_created_at") or state.get("created_at") or "") or None,
        claim_facts=data,
    )

def is_evidence_req(r: dict[str, Any]) -> bool:
    ev_type = r.get("evidence_type")
    if ev_type:
        return True
    
    key = str(r.get("key", "")).lower()
    label = str(r.get("label", "")).lower()
    hint = str(r.get("question_hint", "")).lower()
    
    if any(phrase in hint for phrase in ("upload", "attach", "photo", "image", "scan", "copy of")):
        return True
    # Do not classify generic "document details/number" questions as uploads.
    evidence_terms = ["photo", "image", "bill", "invoice", "receipt", "police_report", "medical_report", "certificate"]
    if any(word in key or word in label for word in evidence_terms):
        return True
    return False

def unresolved(state: ClaimState | dict[str, Any]) -> list[dict[str, Any]]:
    """Return required conversational data fields that are still missing from extracted_data."""
    requirements = state.get("dynamic_requirements") or []
    data = state.get("extracted_data") or {}
    return [
        r for r in requirements
        if r.get("required", True)
        and not is_evidence_req(r)
        and r.get("key")
        and data.get(str(r.get("key"))) in (None, "", "UNKNOWN")
    ]


def missing_evidence(state: ClaimState | dict[str, Any]) -> list[dict[str, Any]]:
    """Return required evidence that has not been VERIFIED.

    An upload, filename match, or pending review never satisfies a requirement.
    """
    requirements = state.get("dynamic_requirements") or []
    evidence = state.get("evidence") or []
    verified_keys = {
        str(e.get("evidence_key"))
        for e in evidence
        if e.get("evidence_key") and str(e.get("verification_status") or "").upper() == "VERIFIED"
    }
    return [
        r for r in requirements
        if r.get("required", True) and is_evidence_req(r) and str(r.get("key")) not in verified_keys
    ]


def _deterministic_dynamic_extract(text: str) -> dict[str, str]:
    """Extract standard domain patterns (vehicle registration, driver license) deterministically."""
    extracted = {}
    # Match Indian/US/standard vehicle registration plates e.g. TN-09-CB-1234, MH02AB1234, DL-01-A-1234
    match_veh = re.search(r"\b([A-Z]{2}[ -]?[0-9]{1,2}[ -]?[A-Z]{1,3}[ -]?[0-9]{4})\b", text, re.I)
    if match_veh:
        extracted["vehicle_registration_number"] = match_veh.group(1).upper().strip()
    # Match driver license mentions e.g. DL-12345, DL-5678, license: DL12345678
    match_dl = re.search(r"\b(?:dl|license|licence|driving\s+license)\s*(?:no\.?|number|id|is|:)?\s*([A-Za-z0-9/-]{4,20})\b", text, re.I)
    if match_dl:
        extracted["driver_license_number"] = match_dl.group(1).upper().strip()
        extracted["driving_license_status"] = match_dl.group(1).upper().strip()
    return extracted


def extract_answers(state: ClaimState | dict[str, Any]) -> None:
    utterance = str(state.get("last_user_utterance") or "").strip()
    if utterance:
        # 1. Always run deterministic pattern extraction into extracted_data
        quick_vals = _deterministic_dynamic_extract(utterance)
        for k, v in quick_vals.items():
            state.setdefault("extracted_data", {})[k] = v

    remaining = unresolved(state)
    if not remaining or not utterance:
        state["dynamic_missing"] = remaining
        state["missing_evidence"] = missing_evidence(state)
        return

    allowed = {str(r.get("key")) for r in remaining if r.get("key")}

    # 2. LLM-based structured extraction for remaining domain fields
    prompt = (
        "Extract only claim-specific values that are explicitly present in the latest claimant utterance. "
        "Use only the supplied requirement keys. Do not infer, invent or copy values from prior turns. "
        f"Requirements: {remaining}\nCurrent claim facts: {state.get('extracted_data', {})}\n"
        f"Latest claimant utterance: {utterance}"
    )
    try:
        result: Any = invoke_with_retry(
            lambda: structured_output(get_configured_llm(), DynamicExtraction).invoke(prompt),
            operation_name="claim-specific structured extraction",
            attempts=3,
        )
        if isinstance(result, BaseModel):
            values = result.model_dump().get("values", {})
        elif isinstance(result, dict):
            values = result.get("values", {})
        else:
            values = {}
        for key, value in values.items():
            if str(key) in allowed and value not in (None, "", "UNKNOWN"):
                state.setdefault("extracted_data", {})[str(key)] = value
    except Exception as exc:
        state["dynamic_extraction_error"] = type(exc).__name__
        state["dynamic_extraction_error_message"] = str(exc)[:500]

    state["dynamic_missing"] = unresolved(state)
    state["missing_evidence"] = missing_evidence(state)

