"""Knowledge-domain schemas used by dynamic claim requirements and RAG."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

DocumentType = Literal["claim_requirement", "policy_wording", "regulation", "guideline", "evidence"]

class KnowledgeChunk(BaseModel):
    id: str
    text: str
    document_type: DocumentType
    insurance_type: str | None = None
    policy_number: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_name: str = ""
    source_uri: str = ""
    metadata: dict = Field(default_factory=dict)

class ClaimRequirement(BaseModel):
    key: str
    label: str
    description: str
    required: bool = True
    evidence_type: str | None = None
    applies_when: str | None = None
    source_id: str | None = None

class RequirementSet(BaseModel):
    insurance_type: str
    requirements: list[ClaimRequirement] = Field(default_factory=list)
    sources: list[KnowledgeChunk] = Field(default_factory=list)
