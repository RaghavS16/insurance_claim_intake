"""LLM-based document metadata extraction. No claim requirements are hard-coded here."""
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, Field
from src.agents.llm_factory import get_configured_llm

class DocumentMetadata(BaseModel):
    title: str = ""
    document_type: str = "unknown"
    insurance_type: str | None = None
    policy_number: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    document_scope: str = Field(default="general", description="Short description of what this document governs.")

def infer_metadata(text: str, filename: str, document_type_hint: str | None = None) -> DocumentMetadata:
    prompt = f"""Analyze this insurance document and extract metadata for retrieval.
Do not invent values. If a value is not explicit, return null/empty.
Filename: {filename}
Document type hint: {document_type_hint or "none"}
Document text:
{text[:30000]}
Return structured metadata only."""
    try:
        result = get_configured_llm().with_structured_output(DocumentMetadata).invoke(prompt)
        if isinstance(result, DocumentMetadata):
            return result
    except Exception:
        pass
    return DocumentMetadata(title=filename)
