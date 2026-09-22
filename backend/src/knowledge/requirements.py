"""LLM-generated claim-specific requirement schema directly from RAG documents.

No static question catalogue is hardcoded. Follow-up details collection and evidence requirements
are dynamically extracted from authoritative policy documents, regulatory circulars, and claim
guidelines retrieved via RAG.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

class Requirement(BaseModel):
    key: str = Field(min_length=2)
    label: str
    question_hint: str
    required: bool = True
    evidence_type: str | None = None
    condition: str | None = None

class RequirementPlan(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    rationale: str = ""


def get_requirements_from_context(
    llm,
    *,
    insurance_type: str,
    policy_context: list[dict],
    regulatory_context: list[dict],
    incident_description: str = "",
) -> list[dict]:
    """Dynamically determine follow-up information and evidence requirements from RAG documents."""
    if not policy_context and not regulatory_context:
        return []

    def _prompt_context(rows: list[dict]) -> list[dict]:
        # Keep RAG prompts bounded; retrieval provenance is persisted separately.
        return [
            {
                "source_name": row.get("source_name"),
                "document_type": row.get("document_type"),
                "score": row.get("rerank_score", row.get("score")),
                "text": str(row.get("text") or "")[:3500],
            }
            for row in rows[:3]
        ]

    policy_prompt_context = _prompt_context(policy_context)
    regulatory_prompt_context = _prompt_context(regulatory_context)

    prompt = f"""You are an expert insurance claims specialist.
Analyze the retrieved authoritative policy wording, regulatory circulars, and claim guidelines provided below for this {insurance_type} insurance claim.

Based SOLELY on these retrieved documents:
1. Identify specific follow-up information details required from the claimant to process and assess coverage for this claim.
2. Identify all required supporting evidence, photographs, or document uploads mandated by the policy wording or claim conditions (e.g., photos of damage, bills, discharge summary, FIR copy, driving license, travel tickets).

Do NOT repeat the 6 baseline fields already collected: policy number, incident date, insurance type, incident description, incident location, estimated loss amount.

Insurance Type: {insurance_type}
Claimant Incident Summary: {incident_description}

Authoritative Policy Documents (RAG):
{policy_prompt_context}

Authoritative Regulatory & Guidance Documents (RAG):
{regulatory_prompt_context}

Return a structured RequirementPlan with requirements where:
- key: concise snake_case identifier (e.g., vehicle_registration_number, driving_license_details, damage_photos, repair_estimate, medical_bills)
- label: clear claimant-friendly title
- question_hint: natural, conversational question the assistant should ask the user to collect this detail
- required: true if necessary under the policy terms to process the claim
- evidence_type: 'photo' for photographs/images, 'document' for paper documents/bills/invoices/reports, or null for text/data details
"""
    plan: RequirementPlan | None = None
    try:
        result = llm.with_structured_output(RequirementPlan).invoke(prompt)
        if isinstance(result, RequirementPlan) and result.requirements:
            plan = result
    except Exception:
        plan = None

    if plan is None:
        try:
            import json
            import re
            raw = llm.invoke(prompt)
            content = getattr(raw, "content", str(raw))
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                data_str = json_match.group(1)
            else:
                data_str = content[content.find("{"):content.rfind("}")+1]
            if data_str:
                data = json.loads(data_str)
                plan = RequirementPlan.model_validate(data)
        except Exception:
            plan = None

    if plan and plan.requirements:
        source_refs = []
        for doc in [*policy_context, *regulatory_context]:
            source_refs.append({
                "source_name": doc.get("source_name"),
                "source_uri": doc.get("source_uri"),
                "document_id": doc.get("document_id") or doc.get("id"),
                "chunk_id": doc.get("chunk_id") or doc.get("id"),
                "score": doc.get("rerank_score", doc.get("score")),
            })
        output = []
        for req in plan.requirements:
            item = req.model_dump()
            item["provenance"] = {"sources": source_refs}
            output.append(item)
        return output

    return []


