"""Dynamic claim-type requirement planning and conversational extraction."""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from src.agents.llm_factory import get_configured_llm, invoke_with_retry, structured_output
from src.knowledge.retriever import KnowledgeRetriever
from src.agents.state import ClaimState

class DynamicExtractedValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: Any


class DynamicExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: list[DynamicExtractedValue] = Field(default_factory=list)

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

def _baseline_equivalent_value(requirement: dict[str, Any], data: dict[str, Any]) -> Any:
    """Resolve dynamic requirement aliases already covered by baseline facts."""
    semantic = " ".join(
        str(requirement.get(k) or "").lower()
        for k in ("key", "label", "question_hint", "condition")
    )
    aliases = (
        ("policy_id", ("policy number", "policy no", "policy id", "policy_number")),
        ("event_date", ("incident date", "accident date", "date of incident", "date of accident")),
        ("insurance_type", ("insurance type", "type of insurance", "claim type", "insurance category")),
        ("event_location", ("incident location", "accident location", "location of incident", "location of accident")),
        ("event_description", ("incident description", "accident description", "what happened", "description of incident")),
        ("estimated_claim_amount", (
            "estimated claim amount", "claim amount", "estimated loss", "loss amount",
            "estimated repair cost", "repair cost", "repair estimate", "estimated cost of repair",
            "total repair cost", "total estimated cost for repairing", "cost to repair",
        )),
    )
    for field, phrases in aliases:
        if data.get(field) not in (None, "", "UNKNOWN") and any(phrase in semantic for phrase in phrases):
            return data.get(field)
    return None


def unresolved(state: ClaimState | dict[str, Any]) -> list[dict[str, Any]]:
    """Return required conversational data fields that are still missing from extracted_data."""
    requirements = state.get("dynamic_requirements") or []
    data = state.get("extracted_data") or {}
    unresolved_items = []
    for requirement in requirements:
        if not requirement.get("required", True) or is_evidence_req(requirement) or not requirement.get("key"):
            continue
        key = str(requirement.get("key"))
        if data.get(key) not in (None, "", "UNKNOWN"):
            continue
        # RAG may use domain wording such as "estimated repair cost" for the
        # baseline "estimated_claim_amount". Do not turn that wording difference
        # into a duplicate claimant question.
        if _baseline_equivalent_value(requirement, data) not in (None, "", "UNKNOWN"):
            continue
        unresolved_items.append(requirement)
    return unresolved_items


def pending_evidence_review(state: ClaimState | dict[str, Any]) -> list[dict[str, Any]]:
    """Return evidence requirements already uploaded but awaiting manual review.

    REVIEW_REQUIRED is a workflow state, not a reason to ask the claimant to upload
    the same file again. The requirement remains a submission blocker until an
    adjuster/reviewer resolves it, but intake can continue with other requirements.
    """
    requirements = state.get("dynamic_requirements") or []
    evidence = state.get("evidence") or []
    pending_keys = {
        str(e.get("evidence_key"))
        for e in evidence
        if e.get("evidence_key")
        and str(e.get("verification_status") or "").upper() == "REVIEW_REQUIRED"
    }
    return [
        r for r in requirements
        if r.get("required", True) and is_evidence_req(r) and str(r.get("key")) in pending_keys
    ]


def missing_evidence(state: ClaimState | dict[str, Any]) -> list[dict[str, Any]]:
    """Return required evidence that still needs claimant action.

    VERIFIED satisfies a requirement. REVIEW_REQUIRED means the claimant already
    supplied a file and must not be prompted to upload it again; the item is tracked
    separately by pending_evidence_review(). REJECTED/UNREADABLE remain actionable.
    """
    requirements = state.get("dynamic_requirements") or []
    evidence = state.get("evidence") or []
    satisfied_or_pending = {
        str(e.get("evidence_key"))
        for e in evidence
        if e.get("evidence_key")
        and str(e.get("verification_status") or "").upper() in {"VERIFIED", "REVIEW_REQUIRED"}
    }
    return [
        r for r in requirements
        if r.get("required", True)
        and is_evidence_req(r)
        and str(r.get("key")) not in satisfied_or_pending
    ]


def _deterministic_dynamic_extract(text: str, requirements: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Extract high-confidence domain values and map them only to matching dynamic requirements.

    This is a semantic safety net for common structured facts. It does not create a
    fixed question catalogue; the active RAG requirement still decides which values
    matter for this claim.
    """
    extracted: dict[str, Any] = {}
    match_veh = re.search(r"\b([A-Z]{2}[ -]?[0-9]{1,2}[ -]?[A-Z]{1,3}[ -]?[0-9]{4})\b", text, re.I)
    vehicle_reg = match_veh.group(1).upper().strip() if match_veh else None

    match_dl = re.search(
        r"\b(?:driving\s+licen[cs]e|licen[cs]e|dl)\s*(?:no\.?|number|id|is|:)?\s*([A-Za-z0-9/-]{4,24})\b",
        text,
        re.I,
    )
    driver_license = match_dl.group(1).upper().strip() if match_dl else None

    phone = None
    phone_match = re.search(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)", text)
    if phone_match:
        raw_phone = re.sub(r"[ -]", "", phone_match.group(0))
        phone = raw_phone

    # Explicit driver-name constructions avoid swallowing the surrounding sentence.
    driver_name = None
    name_match = re.search(
        r"(?:driver(?:'s|’s)?\s+(?:name\s+)?(?:was|is|:)|driven\s+by)\s*"
        r"([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3}?)(?=\s+(?:during|and|with|who|at|on)\b|[,.;]|$)",
        text,
        re.I,
    )
    if name_match:
        driver_name = name_match.group(1).strip()

    # Capture a third-party make/model from phrases such as "it was a silver Hyundai i20".
    vehicle_make_model = None
    make_model = re.search(
        r"(?:it\s+was\s+(?:a|an)\s+|(?:other|oncoming)\s+(?:vehicle|car)\s+(?:was|is)\s+(?:a|an)\s+)"
        r"([A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}?)(?=\s+registration\s+(?:number|no)|\s+with\s+registration|[,.;]|$)",
        text,
        re.I,
    )
    if make_model:
        vehicle_make_model = make_model.group(1).strip()

    police_negative = bool(re.search(r"\b(?:no|didn['’]?t\s+file|wasn['’]?t\s+filed)\b.{0,30}\b(?:police\s+report|fir)\b", text, re.I))
    police_positive = bool(re.search(r"\b(?:yes|filed|have|has)\b.{0,35}\b(?:police\s+report|fir)\b", text, re.I))
    normalized_answer = text.strip().lower().strip(" .!?")
    short_yes = normalized_answer in {"yes", "yeah", "yep", "correct", "right", "i do", "i have"}
    short_no = normalized_answer in {"no", "nope", "i don't", "i do not", "not filed"}
    negative_answer = bool(re.search(
        r"\b(?:no|nope|not|never|didn['’]?t|wasn['’]?t|weren['’]?t|haven['’]?t|don['’]?t|doesn['’]?t|without)\b",
        text, re.I,
    ))
    positive_answer = bool(re.search(
        r"\b(?:yes|yeah|yep|correct|right|i do|i have|filed|have)\b",
        text, re.I,
    ))

    for req in requirements or []:
        key = str(req.get("key") or "").lower()
        semantic = " ".join(str(req.get(k) or "") for k in ("key", "label", "question_hint")).lower()
        if vehicle_reg and any(term in semantic for term in ("registration", "license plate", "plate number", "vehicle number")):
            extracted[key] = vehicle_reg
        if driver_license and any(term in semantic for term in ("driving licence", "driving license", "licence number", "license number", "driver license")):
            extracted[key] = driver_license
        if phone and any(term in semantic for term in ("contact number", "contact information", "phone number", "mobile number", "telephone")):
            extracted[key] = phone
        if driver_name and any(term in semantic for term in ("driver name", "driver's name", "driver’s name", "name of the driver")):
            extracted[key] = driver_name
        if vehicle_make_model and any(term in semantic for term in ("make and model", "make/model", "vehicle make", "car make", "vehicle model")):
            extracted[key] = vehicle_make_model
        # Generic boolean reconciliation for active yes/no requirements.
        # This is deliberately driven by the current requirement's question/hint,
        # not a fixed question catalogue. It prevents answers such as
        # "No, I was completely sober" from being asked again.
        yes_no_hint = bool(re.search(
            r"^(?:do|does|did|is|are|was|were|have|has|can|could|will|would)\b",
            str(req.get("question_hint") or "").strip().lower(),
        ))
        if yes_no_hint:
            if "under the influence" in semantic or "intoxicat" in semantic or "alcohol" in semantic or "drug" in semantic:
                if negative_answer or short_no or re.search(r"\b(?:sober|not under the influence)\b", text, re.I):
                    extracted[key] = False
                elif positive_answer or short_yes:
                    extracted[key] = True
            elif "police" in semantic or "fir" in semantic:
                if police_negative or short_no:
                    extracted[key] = False
                elif police_positive or short_yes:
                    extracted[key] = True
            elif short_no:
                extracted[key] = False
            elif short_yes:
                extracted[key] = True

    # Preserve backwards-compatible canonical keys for the existing requirement aliases.
    if vehicle_reg:
        extracted.setdefault("vehicle_registration_number", vehicle_reg)
    if driver_license:
        extracted.setdefault("driver_license_number", driver_license)
    return extracted


def extract_answers(state: ClaimState | dict[str, Any]) -> None:
    utterance = str(state.get("last_user_utterance") or "").strip()
    if utterance:
        # 1. Always run deterministic pattern extraction into extracted_data
        quick_vals = _deterministic_dynamic_extract(utterance, state.get("dynamic_requirements") or [])
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
            raw_values = result.model_dump().get("values", [])
        elif isinstance(result, dict):
            raw_values = result.get("values", [])
        else:
            raw_values = []
        if isinstance(raw_values, dict):
            raw_values = [{"key": key, "value": value} for key, value in raw_values.items()]
        for item in raw_values or []:
            if isinstance(item, dict):
                key = str(item.get("key") or "")
                value = item.get("value")
                if key in allowed and value not in (None, "", "UNKNOWN"):
                    state.setdefault("extracted_data", {})[key] = value
    except Exception as exc:
        state["dynamic_extraction_error"] = type(exc).__name__
        state["dynamic_extraction_error_message"] = str(exc)[:500]

    state["dynamic_missing"] = unresolved(state)
    state["missing_evidence"] = missing_evidence(state)

