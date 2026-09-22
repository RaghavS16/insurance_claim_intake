"""LLM-generated claim-specific requirement schema directly from RAG documents.

No static question catalogue is hardcoded. Follow-up details collection and evidence requirements
are dynamically extracted from authoritative policy documents, regulatory circulars, and claim
guidelines retrieved via RAG.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from src.agents.llm_factory import LLMTransientError, invoke_with_retry, structured_output

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
2. Identify all required supporting evidence or document uploads explicitly mandated by the retrieved policy wording, regulatory guidance, or claim conditions. Do not infer a document requirement from general insurance practice; only return evidence requirements that are supported by the retrieved sources.

Do NOT repeat the 6 baseline fields already collected: policy number, incident date, insurance type, incident description, incident location, estimated loss amount.

Insurance Type: {insurance_type}
Claimant Incident Summary: {incident_description}

Authoritative Policy Documents (RAG):
{policy_prompt_context}

Authoritative Regulatory & Guidance Documents (RAG):
{regulatory_prompt_context}

Return a structured RequirementPlan with requirements where:
- key: concise snake_case identifier derived from the terminology used in the retrieved sources
- label: clear claimant-friendly title grounded in the retrieved sources
- question_hint: natural, conversational question the assistant should ask the user to collect this detail
- required: true only when the retrieved sources make the requirement necessary to process or assess the claim
- evidence_type: use 'photo' or 'document' only when the retrieved sources explicitly require that kind of evidence; otherwise use null
- condition: include any source-supported condition under which the requirement applies, otherwise null
"""
    plan: RequirementPlan | None = None
    try:
        result = invoke_with_retry(
            lambda: structured_output(llm, RequirementPlan).invoke(prompt),
            operation_name="dynamic requirement planning",
            attempts=3,
        )
        if isinstance(result, RequirementPlan) and result.requirements:
            plan = result
    except LLMTransientError:
        raise
    except Exception:
        plan = None

    if plan is None:
        try:
            import json
            import re
            raw = invoke_with_retry(
                lambda: llm.invoke(prompt),
                operation_name="dynamic requirement JSON fallback",
                attempts=3,
            )
            content = getattr(raw, "content", str(raw))
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                data_str = json_match.group(1)
            else:
                data_str = content[content.find("{"):content.rfind("}")+1]
            if data_str:
                data = json.loads(data_str)
                plan = RequirementPlan.model_validate(data)
        except LLMTransientError:
            raise
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


