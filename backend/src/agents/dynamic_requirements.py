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
    insurance_type = data.get("insurance_type") or state.get("insurance_type_hint")
    policy_id = data.get("policy_id") or data.get("policy_number")
    incident_date = None
    try:
        from datetime import date
        date_val = data.get("event_date") or data.get("incident_date") or data.get("admission_date")
        incident_date = date.fromisoformat(str(date_val)) if date_val else None
    except ValueError:
        incident_date = None
    query = str(state.get("last_user_utterance") or data.get("event_description") or state.get("claim_text") or "").strip()
    return KnowledgeRetriever().retrieve(
        insurance_type=str(insurance_type) if insurance_type else None,
        policy_number=str(policy_id) if policy_id else None,
        incident_date=incident_date,
        query=query,
        intake_channel="insurer_web_portal",
        intake_started_at=str(state.get("claim_created_at") or state.get("created_at") or "") or None,
        claim_facts=data,
        tenant_id=state.get("tenant_id"),
        jurisdiction=state.get("jurisdiction"),
        claimant_id=state.get("claimant_id"),
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


def clean_extracted_value(key: str, val: Any, raw_utterance: str | None = None) -> Any:
    if val is None or isinstance(val, (int, float, bool)):
        return val
    text = str(val).strip()

    is_narrative = any(n in key.lower() for n in ("description", "narrative", "details", "circumstances", "summary", "notes"))
    if not is_narrative:
        if raw_utterance and text.lower() == raw_utterance.strip().lower() and len(text) > 40:
            return None
        if len(text) > 80:
            return None

    # Amount / Currency extraction: "around 45,000 rupees as per garage" -> 45000.0
    if any(p in key.lower() for p in ("amount", "cost", "bill", "estimate", "expense", "fee", "price", "payout", "charge")):
        amt_match = re.search(r"(?:rs\.?|inr|\$|rupees)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*(?:rs\.?|inr|rupees)?", text, re.I)
        if amt_match:
            try:
                raw_num = amt_match.group(1).replace(",", "")
                return float(raw_num)
            except ValueError:
                pass

    if any(p in key.lower() for p in ("policy", "policy_id", "policy_number", "policy_no")):
        match = re.search(r"\b([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+)\b", text)
        if not match:
            after_kw = re.sub(r"^(?:.*?\bpolicy\s*(?:number|no\.?|id|identifier)?\s*(?:is|was|:)?\s*)", "", text, flags=re.I).strip()
            match = re.search(r"\b([A-Za-z0-9_-]{3,})\b", after_kw)
        if match:
            cand = match.group(1).upper().strip()
            if any(c.isdigit() for c in cand):
                return cand
        clean = re.sub(r"^(?:.*?\bpolicy\s*(?:number|no\.?|id|identifier)?\s*(?:is|was|:)?\s*)", "", text, flags=re.I).strip()
        tokens = [t for t in re.split(r"\s+", clean) if t.lower() not in {"please", "thanks", "thank", "you", "here", "is", "my"}]
        return tokens[0].upper() if tokens else text

    if any(p in key.lower() for p in ("vehicle", "bike", "car", "registration", "plate")):
        match_veh = re.search(r"\b([A-Z]{2}[ -]?[0-9]{1,2}[ -]?[A-Z]{1,3}[ -]?[0-9]{4})\b", text, re.I)
        if match_veh:
            return match_veh.group(1).upper().replace(" ", "").replace("-", "")

    if any(p in key.lower() for p in ("date", "time")) and not is_narrative:
        d_match = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", text)
        if d_match:
            return d_match.group(1)
        month_match = re.search(r"\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})\b", text, re.I)
        if month_match:
            try:
                from datetime import datetime
                d_str = f"{month_match.group(1)} {month_match.group(2)[:3]} {month_match.group(3)}"
                dt = datetime.strptime(d_str, "%d %b %Y")
                return dt.date().isoformat()
            except Exception:
                pass

    if any(p in key.lower() for p in ("location", "place", "city", "address")) and not is_narrative:
        loc_clean = re.sub(r"^(?:it\s+(?:happened|occurred)\s+(?:at|near|in)\s+|at\s+|near\s+|in\s+)", "", text, flags=re.I)
        loc_clean = re.sub(r"\s+(?:on|at|around)\s+\d{1,2}.*$", "", loc_clean, flags=re.I).strip(" .,;:")
        if loc_clean and len(loc_clean) <= 60:
            return loc_clean

    # Strip common conversational noise: "my policy number is ...", "it is ...", "i am ..."
    text = re.sub(
        r"^(?:my\s+[a-z0-9_ -]+\s*(?:is|was|:)?|it\s+(?:is|was|'s)\s*(?:\b(?:a|an)\b\s*)?|i\s+(?:have|am|was)\s*|the\s+[a-z0-9_ -]+\s*(?:is|was|:)?)\s*",
        "",
        text,
        flags=re.I,
    ).strip(" .,:;!?\"'")
    return text


def sync_extracted_fields(state: ClaimState | dict[str, Any]) -> None:
    data = state.get("extracted_data") or {}
    req_map = {str(r.get("key")): r for r in (state.get("dynamic_requirements") or []) if r.get("key")}
    existing_entries = {e.get("field_key"): e for e in (state.get("extracted_fields") or []) if e.get("field_key")}

    fields = []
    for k, v in data.items():
        if v in (None, "", "UNKNOWN"):
            continue
        req = req_map.get(k) or {}
        label = req.get("label") or (existing_entries.get(k) or {}).get("field_label") or k.replace("_", " ").title()
        req_id = req.get("requirement_id") or req.get("key") or (existing_entries.get(k) or {}).get("source_requirement_id") or ""
        clean_v = clean_extracted_value(k, v)
        fields.append({
            "field_key": k,
            "field_label": str(label),
            "value": clean_v,
            "source_requirement_id": str(req_id),
        })
    state["extracted_fields"] = fields


def _deterministic_dynamic_extract(text: str, requirements: list[dict[str, Any]] | None = None, last_asked_field: str | None = None) -> dict[str, Any]:
    """Extract high-confidence domain values and map them only to matching dynamic requirements."""
    extracted: dict[str, Any] = {}
    match_veh = re.search(r"\b([A-Z]{2}[ -]?[0-9]{1,2}[ -]?[A-Z]{1,3}[ -]?[0-9]{4})\b", text, re.I)
    vehicle_reg = match_veh.group(1).upper().strip() if match_veh else None

    # Policy identifier
    match_pol = re.search(
        r"\bpolicy\s*(?:number|no\.?|id|identifier)?\s*(?:is|:)?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,})",
        text,
        re.I,
    )
    if not match_pol:
        match_pol = re.search(r"\b((?:POL|MOT|HLT|TRV|CYB|HOM|AUTO|VEH)[-_ ]?\d{2,8}(?:[-_ ][A-Za-z0-9]{1,6})?)\b", text, re.I)
    policy_code = clean_extracted_value("policy_id", match_pol.group(1).upper().strip()) if match_pol else None

    # Incident date
    match_date = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2})\b", text)
    clean_date = match_date.group(1) if match_date else None
    if not clean_date:
        try:
            from datetime import date, timedelta
            low_text = text.lower()
            if "yesterday" in low_text:
                clean_date = (date.today() - timedelta(days=1)).isoformat()
            elif "today" in low_text:
                clean_date = date.today().isoformat()
        except Exception:
            clean_date = None

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

    driver_name = None
    name_match = re.search(
        r"(?:driver(?:'s|’s)?\s+(?:name\s+)?(?:was|is|:)|driven\s+by)\s*"
        r"([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,3}?)(?=\s+(?:during|and|with|who|at|on)\b|[,.;]|$)",
        text,
        re.I,
    )
    if name_match:
        driver_name = name_match.group(1).strip()

    vehicle_make_model = None
    make_model = re.search(
        r"(?:it\s+was\s+(?:a|an)\s+|(?:other|oncoming)\s+(?:vehicle|car)\s+(?:was|is)\s+(?:a|an)\s+)"
        r"([A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}?)(?=\s+registration\s+(?:number|no)|\s+with\s+registration|[,.;]|$)",
        text,
        re.I,
    )
    if make_model:
        vehicle_make_model = make_model.group(1).strip()

    normalized_answer = text.strip().lower().strip(" .!?")
    short_yes = normalized_answer in {"yes", "yeah", "yep", "correct", "right", "i do", "i have"}
    short_no = normalized_answer in {"no", "nope", "i don't", "i do not", "not filed"}

    target_key = (last_asked_field or (requirements[0].get("key") if requirements and len(requirements) == 1 else "") or "").lower()

    for req in requirements or []:
        key = str(req.get("key") or "")
        key_low = key.lower()
        semantic = " ".join(str(req.get(k) or "") for k in ("key", "label", "question_hint")).lower()
        if policy_code and any(term in semantic for term in ("policy", "policy number", "policy id", "policy_number", "policy_id")):
            extracted[key] = policy_code
        if clean_date and any(term in semantic for term in ("date", "incident date", "accident date", "admission date", "event_date")):
            extracted[key] = clean_date
        if vehicle_reg and any(term in semantic for term in ("registration", "license plate", "plate number", "vehicle number", "bike number", "car number")):
            extracted[key] = vehicle_reg
        if driver_license and any(term in semantic for term in ("driving licence", "driving license", "licence number", "license number", "driver license")):
            extracted[key] = driver_license
        if phone and any(term in semantic for term in ("contact number", "contact information", "phone number", "mobile number", "telephone")):
            extracted[key] = phone
        if driver_name and any(term in semantic for term in ("driver name", "driver's name", "driver’s name", "name of the driver")):
            extracted[key] = driver_name
        if vehicle_make_model and any(term in semantic for term in ("make and model", "make/model", "vehicle make", "car make", "vehicle model")):
            extracted[key] = vehicle_make_model

        # Semantic alcohol / sober requirement extraction
        if any(term in semantic for term in ("alcohol", "influence", "drug", "intoxicat")):
            if re.search(r"\b(?:sober|not\s+under\s+the\s+influence|no\b.*?\b(?:alcohol|drug|substance|intoxicat))\b", text, re.I):
                extracted[key] = False
            elif re.search(r"\b(?:under\s+the\s+influence|consumed\s+alcohol|intoxicated|was\s+drunk)\b", text, re.I):
                extracted[key] = True

        # Semantic police report extraction
        if any(term in semantic for term in ("police", "fir", "report_or_fir")):
            if re.search(r"\b(?:no\s+police\s+report|not\s+filed|no\s+fir|settled\s+at\s+the\s+scene)\b", text, re.I):
                extracted[key] = False
            elif re.search(r"\b(?:filed\s+(?:a\s+)?(?:police|fir)|police\s+report\s+was\s+filed|yes\s+i\s+have\s+(?:a\s+)?(?:police|fir))\b", text, re.I):
                extracted[key] = True

        # Dashcam / serial / footage extraction
        if any(term in semantic for term in ("dashcam", "serial", "footage", "camera")):
            cam_match = re.search(r"(?:dashcam|serial|footage|camera)[^A-Za-z0-9]*(?:is|number|no|#|:|-)?\s*([A-Za-z0-9-_]{4,25})", text, re.I)
            if cam_match:
                extracted[key] = cam_match.group(1).strip()

    # Rule 5: Only allow direct yes/no token to satisfy the single requirement that was just asked (or single active requirement)
    if target_key and (short_yes or short_no):
        for req in requirements or []:
            key = str(req.get("key") or "")
            if key.lower() == target_key or key.lower() in target_key or target_key in key.lower():
                extracted[key] = True if short_yes else False

    # Preserve canonical keys
    if policy_code:
        extracted.setdefault("policy_id", policy_code)
    if clean_date:
        extracted.setdefault("event_date", clean_date)
    if vehicle_reg:
        extracted.setdefault("vehicle_registration_number", vehicle_reg)
    if driver_license:
        extracted.setdefault("driver_license_number", driver_license)
    return extracted


def _mirror_canonical_roles(state: ClaimState | dict[str, Any]) -> None:
    req_map = {str(r.get("key")): r for r in (state.get("dynamic_requirements") or []) if r.get("key")}
    extracted = state.setdefault("extracted_data", {})
    for k, v in list(extracted.items()):
        req = req_map.get(k)
        if req and req.get("canonical_role"):
            crole = req.get("canonical_role")
            if crole in ("policy_id", "insurance_type", "event_date", "event_location", "event_description", "estimated_claim_amount"):
                extracted.setdefault(crole, v)
                if not extracted.get(crole):
                    extracted[crole] = v


def extract_answers(state: ClaimState | dict[str, Any]) -> None:
    utterance = str(state.get("last_user_utterance") or "").strip()
    last_asked = str(state.get("last_asked_field") or state.get("next_question_field") or "")
    if utterance:
        # 1. Always run deterministic pattern extraction into extracted_data
        quick_vals = _deterministic_dynamic_extract(utterance, state.get("dynamic_requirements") or [], last_asked_field=last_asked)
        for k, v in quick_vals.items():
            clean_v = clean_extracted_value(k, v, raw_utterance=utterance)
            if clean_v is not None:
                state.setdefault("extracted_data", {})[k] = clean_v

    remaining = unresolved(state)
    if not remaining or not utterance:
        state["dynamic_missing"] = remaining
        state["missing_evidence"] = missing_evidence(state)
        sync_extracted_fields(state)
        _mirror_canonical_roles(state)
        return

    allowed = {str(r.get("key")) for r in remaining if r.get("key")}

    # 2. LLM-based structured extraction for remaining domain fields
    prompt = (
        "Extract only clean, exact claim-specific values that are explicitly present in the latest claimant utterance. "
        "Return ONLY the concise entity value (e.g., if user says 'my policy is POL-123', return 'POL-123'; "
        "if user says 'my bike number is TN31A4567', return 'TN31A4567'; "
        "if user says 'around 45,000 rupees as per garage', return 45000.0; "
        "if user says 'it happened near Anna Nagar Arch on 12 Oct 2026', return location: 'Anna Nagar Arch', date: '2026-10-12'). "
        "Never return the user's conversational sentence or full sentence when an entity or short identifier is expected. "
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
                    clean_val = clean_extracted_value(key, value, raw_utterance=utterance)
                    if clean_val is not None:
                        state.setdefault("extracted_data", {})[key] = clean_val
    except Exception as exc:
        state["dynamic_extraction_error"] = type(exc).__name__
        state["dynamic_extraction_error_message"] = str(exc)[:500]

    state["dynamic_missing"] = unresolved(state)
    state["missing_evidence"] = missing_evidence(state)
    sync_extracted_fields(state)
    _mirror_canonical_roles(state)

