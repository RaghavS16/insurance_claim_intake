"""LLM-generated claim-specific requirement schema.

No insurance-specific requirement catalogue is hard-coded. Requirements are derived
from retrieved policy, regulatory and claim-guidance documents.
"""
from pydantic import BaseModel, Field

class Requirement(BaseModel):
    key: str = Field(min_length=2)
    label: str
    question_hint: str
    required: bool = True
    evidence_type: str | None = None

class RequirementPlan(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    rationale: str = ""

def get_requirements_from_context(llm, *, insurance_type: str, policy_context: list[dict], regulatory_context: list[dict], incident_description: str = "") -> list[dict]:
    if not policy_context and not regulatory_context:
        return []
    prompt=f"""Create the claim-specific intake and evidence requirements for this insurance claim.
Only use requirements explicitly supported by the supplied authoritative documents. Do not use generic insurance knowledge.
Do not repeat baseline fields: policy number, incident date, insurance type, incident description, incident location, estimated loss.
Insurance type: {insurance_type}
Incident: {incident_description}
Policy evidence: {policy_context}
Regulatory/guidance evidence: {regulatory_context}
Return stable snake_case keys, claimant-friendly labels, natural question hints, required=true only when the documents make it necessary, and evidence_type only when supporting evidence is required."""
    try:
        result=llm.with_structured_output(RequirementPlan).invoke(prompt)
        if isinstance(result,RequirementPlan):
            return [r.model_dump() for r in result.requirements]
    except Exception:
        return []
    return []
