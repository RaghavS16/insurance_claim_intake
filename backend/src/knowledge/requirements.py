"""LLM-generated claim-specific requirement schema directly from RAG documents.

No static question catalogue is hardcoded. Follow-up details collection and evidence requirements
are dynamically extracted from authoritative policy documents, regulatory circulars, and claim
guidelines retrieved via RAG.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from src.agents.llm_factory import LLMTransientError, get_configured_llm, invoke_with_retry, structured_output

class Requirement(BaseModel):
    key: str = Field(min_length=2)
    label: str
    question_hint: str
    required: bool = True
    evidence_type: str | None = None
    condition: str | None = None
    category: str = "other"
    source_section: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_excerpt: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    canonical_role: str | None = None
    citation_label: str | None = None

class RequirementPlan(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    rationale: str = ""


def tag_canonical_role(item: dict[str, Any]) -> str | None:
    role = item.get("canonical_role")
    if role:
        return role
    key = str(item.get("key") or "").lower()
    label = str(item.get("label") or "").lower()
    if any(k in key or k in label for k in ("policy_id", "policy_number", "policy_no", "certificate_number")):
        return "policy_id"
    if any(k in key or k in label for k in ("insurance_type", "coverage_type", "claim_type", "policy_type")):
        return "insurance_type"
    if any(k in key or k in label for k in ("admission_date", "date_of_accident", "date_of_loss", "event_date", "incident_date", "loss_date")):
        return "event_date"
    if any(k in key or k in label for k in ("event_location", "accident_location", "place_of_incident", "loss_location", "hospital_location", "location")):
        return "event_location"
    if any(k in key or k in label for k in ("event_description", "incident_description", "loss_description", "description_of_accident", "nature_of_illness")):
        return "event_description"
    if any(k in key or k in label for k in ("estimated_claim_amount", "claimed_amount", "estimate_amount", "loss_amount", "repair_estimate", "claimed_hospital_bill", "hospital_bill")):
        return "estimated_claim_amount"
    return None


def get_requirements_from_context(
    llm=None,
    *,
    insurance_type: str = "general",
    policy_context: list[dict] | None = None,
    regulatory_context: list[dict] | None = None,
    chunks: list[dict] | None = None,
    incident_description: str = "",
    intake_channel: str = "insurer_web_portal",
    intake_started_at: str | None = None,
    claim_facts: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    jurisdiction: str | None = None,
    **kwargs: Any,
) -> list[dict]:
    """Dynamically determine follow-up information and evidence requirements from RAG documents."""
    if policy_context is None and chunks is not None:
        policy_context = chunks
    if regulatory_context is None:
        regulatory_context = []
    if not policy_context and not regulatory_context:
        return []
    if llm is None:
        llm = get_configured_llm()

    def _prompt_context(rows: list[dict]) -> list[dict]:
        return [
            {
                "source_name": row.get("source_name"),
                "document_id": row.get("document_id"),
                "chunk_id": row.get("chunk_id") or row.get("id"),
                "document_type": row.get("document_type"),
                "score": row.get("rerank_score", row.get("score")),
                "text": str(row.get("text") or "")[:1500],
            }
            for row in rows[:5]
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
2. Identify ALL required supporting evidence or document uploads explicitly mandated by the retrieved policy wording, regulatory guidance, or claim conditions. Do not infer a document requirement from general insurance practice; only return evidence requirements that are supported by the retrieved sources.
3. Do not summarize the checklist into a small number of "representative" items. Preserve every distinct source-backed claimant detail, document, notification, add-on obligation, and conditional requirement that appears in the supplied evidence.
4. When a requirement is conditional and the condition is not resolved by the known claim facts, keep it in the plan with its condition so the conversation can collect the fact needed to resolve it.

Include ALL required claimant details and supporting evidence mandated by the retrieved sources to process, identify, or assess the claim (such as policy number/identifier, incident dates, loss amounts, event descriptions, or specific documentation if required by the source text). Do not assume any pre-collected baseline fields.

Insurance Type: {insurance_type}
Claimant Incident Summary: {incident_description}
Known Claim Facts (use only to evaluate source-supported conditions; never invent missing facts):
{claim_facts or {}}

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

