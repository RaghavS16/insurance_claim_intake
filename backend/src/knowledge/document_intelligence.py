"""LLM-based document metadata extraction. No claim requirements are hard-coded here."""
from __future__ import annotations
import re
from datetime import date
from pydantic import BaseModel, Field
from src.agents.llm_factory import get_configured_llm

INSURANCE_TYPES: dict[str, list[str]] = {
    "senior_citizen_health": ["senior citizen", "senior_citizen", "age 60", "60 years and above", "geriatric", "moratorium period (60 months)"],
    "motor": ["motor", "vehicle", "auto", "car", "collision", "own damage", "third-party liability", "garage", "idv", "motor vehicles act"],
    "health": ["health", "medical", "hospital", "inpatient", "cashless", "tpa", "discharge summary", "icd", "rohini"],
    "home": ["home", "property", "dwelling", "building", "contents", "bharat griha raksha", "fire", "flood", "burglary"],
    "travel": ["travel", "trip", "flight", "baggage", "passport", "overseas", "schengen", "pir"],
    "cyber": ["cyber", "ransomware", "data breach", "phishing", "extortion", "unauthorized transaction", "cert-in", "1930", "ncrp"],
}

class DocumentMetadata(BaseModel):
    title: str = ""
    document_type: str = "unknown"
    insurance_type: str | None = None
    document_scope: str = Field(default="general", description="Short description of what this document governs.")

def _heuristic_classify(filename: str, sample_text: str = "") -> tuple[str, str | None]:
    low_f = filename.lower()
    low_t = sample_text[:10000].lower()
    
    # Document type inference
    doc_type = "unknown"
    if "regulatory" in low_f or "regulation" in low_f or "master circular" in low_f:
        doc_type = "regulation"
    elif "wording" in low_f or "policy wording" in low_f or "policy_wording" in low_f or "prospectus" in low_f:
        doc_type = "policy_wording"
    elif "endorsement" in low_f:
        doc_type = "endorsement"
    elif "guideline" in low_f or "circular" in low_f:
        doc_type = "regulation"
    
    # Insurance line inference: senior citizen health MUST precede generic health!
    ins_type = None
    for line, keywords in INSURANCE_TYPES.items():
        if any(kw in low_f for kw in keywords):
            ins_type = line
            break
            
    if not ins_type:
        for line, keywords in INSURANCE_TYPES.items():
            if any(kw in low_t for kw in keywords):
                ins_type = line
                break

    return doc_type, ins_type

def infer_metadata(text: str, filename: str, document_type_hint: str | None = None) -> DocumentMetadata:
    meta = None
    doc_type_heur, ins_type_heur = _heuristic_classify(filename, text)

    prompt = f"""Analyze this insurance document and extract metadata for retrieval.
Do not invent values. If a value is not explicit, return null/empty.
Filename: {filename}
Document type hint: {document_type_hint or doc_type_heur or "none"}
Document text:
{text[:30000]}
Return structured metadata only."""
    try:
        result = get_configured_llm().with_structured_output(DocumentMetadata).invoke(prompt)
        if isinstance(result, DocumentMetadata):
            meta = result
    except Exception:
        pass
    if meta is None:
        meta = DocumentMetadata(title=filename)
    if not meta.document_type or meta.document_type == "unknown":
        meta.document_type = document_type_hint or doc_type_heur or "policy_wording"
    if not meta.insurance_type:
        meta.insurance_type = ins_type_heur
    return meta
