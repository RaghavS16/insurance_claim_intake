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
    intake_channel: str = "insurer_web_portal",
    intake_started_at: str | None = None,
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

WORKFLOW CONTEXT:
This claim is being reported directly to the insurer through its own claim-intake application.
The current conversation is the active first-notice/intake interaction, so the application itself records the current insurer notification.
Do not ask for a notification date/time for this same intake channel. Only require a separate prior notification if the source explicitly says it had to happen before this claim through a separate channel.

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
    # Structured output is the only normal path. The unstructured fallback is a single
    # bounded attempt and exists only for providers that ignore structured output.
    try:
        result = invoke_with_retry(
            lambda: structured_output(llm, RequirementPlan).invoke(prompt),
            operation_name="dynamic requirement planning",
            attempts=1,
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
                attempts=1,
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
            searchable = " ".join(
                str(item.get(k) or "").lower()
                for k in ("key", "label", "question_hint", "condition")
            )
            same_intake_notification = any(
                phrase in searchable
                for phrase in (
                    "reported to the insurer",
                    "report to the insurer",
                    "insurer call",
                    "call centre",
                    "call center",
                    "notify the insurer",
                    "notification to the insurer",
                )
            )
            prior_notification = any(
                phrase in searchable
                for phrase in (
                    "previously reported",
                    "previously notified",
                    "prior notification",
                    "prior notice",
                    "before this claim",
                    "before filing",
                )
            )
            if same_intake_notification and not prior_notification:
                continue
            item["provenance"] = {"sources": source_refs}
            output.append(item)
        return output

    return []




def get_provisional_requirements(
    llm,
    *,
    insurance_type: str,
    claim_facts: dict[str, Any],
    conversation: str = "",
) -> list[dict]:
    """Create non-policy-specific follow-up candidates so intake never stalls.

    These are provisional conversation candidates, not coverage requirements. They
    are collected when authoritative RAG knowledge is temporarily unavailable and
    must be revalidated against policy/regulatory sources before submission.
    """
    prompt = f"""You are an insurance claim intake conversation planner.
The claimant has already completed baseline verification. Continue the conversation
naturally by identifying claim-specific details and supporting evidence that are
reasonable to collect from the claimant based ONLY on the claimant's own incident
facts and the insurance type.

This is NOT a policy decision. Do not state that anything is mandatory or covered.
Do not repeat baseline fields: policy number, incident date, insurance type,
incident description, incident location, estimated loss amount.
Do not ask when the claimant reported this claim to the insurer through the
current intake application.
Only identify details or documents that are directly suggested by the incident
facts. Prefer a small number of high-value next steps.

Insurance type: {insurance_type}
Claim facts: {claim_facts}
Recent claimant conversation: {conversation}

For each candidate:
- key: concise snake_case identifier
- label: claimant-friendly title
- question_hint: natural conversational question
- required: true only if needed to continue collecting this candidate
- evidence_type: 'photo' or 'document' only when the claimant's facts directly
  indicate that such evidence is relevant; otherwise null
- condition: brief reason grounded in the claimant's facts
Return RequirementPlan.
"""
    try:
        result = invoke_with_retry(
            lambda: structured_output(llm, RequirementPlan).invoke(prompt),
            operation_name="provisional claim-specific planning",
            attempts=1,
        )
        if isinstance(result, RequirementPlan):
            plan = result
        elif isinstance(result, dict):
            plan = RequirementPlan.model_validate(result)
        else:
            return []
    except Exception:
        return []

    output = []
    for req in plan.requirements[:8]:
        item = req.model_dump()
        searchable = " ".join(str(item.get(k) or "").lower() for k in ("key", "label", "question_hint"))
        if any(
            phrase in searchable
            for phrase in (
                "reported to the insurer",
                "report to the insurer",
                "insurer call",
                "call centre",
                "call center",
                "notify the insurer",
                "notification to the insurer",
            )
        ):
            continue
        item["provenance"] = {"type": "provisional_claim_context"}
        output.append(item)
    return output
