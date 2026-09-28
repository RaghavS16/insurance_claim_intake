"""Claim-specific requirement planning backed by a document-level policy manifest."""
from __future__ import annotations
from typing import Any
import json
from pydantic import BaseModel, Field
from src.agents.llm_factory import LLMTransientError, get_configured_llm, invoke_with_retry, structured_output

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

def _notification_is_current_intake(item: dict[str, Any]) -> bool:
    searchable = " ".join(str(item.get(k) or "").lower() for k in ("key", "label", "question_hint", "condition"))
    same_intake = any(phrase in searchable for phrase in ("reported to the insurer", "report to the insurer", "insurer call", "call centre", "call center", "notify the insurer", "notification to the insurer"))
    prior_notification = any(phrase in searchable for phrase in ("previously reported", "previously notified", "prior notification", "prior notice", "before this claim", "before filing"))
    return same_intake and not prior_notification

def _manifest_requirements(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    output: list[dict[str, Any]] = []
    for raw in manifest.get("requirements") or []:
        if not isinstance(raw, dict) or not raw.get("key"):
            continue
        item = {
            "key": str(raw.get("key")),
            "label": str(raw.get("label") or raw.get("key")),
            "question_hint": str(raw.get("question_hint") or ""),
            "required": bool(raw.get("required", True)),
            "evidence_type": raw.get("evidence_type"),
            "condition": raw.get("condition"),
            "category": raw.get("category"),
            "basis": raw.get("basis"),
            "source_chunk_ids": list(raw.get("source_chunk_ids") or []),
            "source_excerpt": str(raw.get("source_excerpt") or ""),
        }
        if not _notification_is_current_intake(item):
            output.append(item)
    return output

def get_requirements_from_context(
    llm, *, insurance_type: str, policy_context: list[dict], regulatory_context: list[dict],
    incident_description: str = "", intake_channel: str = "insurer_web_portal",
    intake_started_at: str | None = None, claim_facts: dict[str, Any] | None = None,
    policy_manifest: dict[str, Any] | None = None,
) -> list[dict]:
    """Resolve whole-policy requirements against this claim's facts."""
    manifest_requirements = _manifest_requirements(policy_manifest)
    if not manifest_requirements and not policy_context and not regulatory_context:
        return []

    def _prompt_context(rows: list[dict]) -> list[dict]:
        return [{
            "source_name": row.get("source_name"),
            "document_type": row.get("document_type"),
            "score": row.get("rerank_score", row.get("score")),
            "text": str(row.get("text") or "")[:3500],
        } for row in rows[:8]]

    policy_prompt_context = _prompt_context(policy_context)
    regulatory_prompt_context = _prompt_context(regulatory_context)
    if manifest_requirements:
        inventory = manifest_requirements
        inventory_instruction = """The policy requirement manifest was compiled from the complete policy document. Treat it as the authoritative inventory. Select requirements that apply to this claim and preserve all applicable information and evidence requirements. Do not invent new requirements. A conditional requirement is applicable only when its condition is supported by known claim facts. If a condition cannot yet be evaluated, retain it as conditionally outstanding rather than silently dropping it."""
    else:
        inventory = []
        inventory_instruction = "No document-level manifest is available. Use only the retrieved authoritative excerpts and do not infer a generic industry checklist."

    prompt = f"""You are an expert insurance claim-intake planner for {insurance_type} insurance.

{inventory_instruction}

This is the insurer's current first-notice/intake conversation. The current intake itself records the notification being made now, so do not ask for a duplicate notification date/time unless the source explicitly requires prior notification through a separate channel.

Do NOT repeat these baseline fields: policy number, incident date, insurance type, incident description, incident location, estimated loss amount.

Resolve policy-supported requirements against the claimant's known facts. Preserve information that is already known as satisfied; return only requirements that still need claimant input or evidence, plus conditional requirements whose applicability still needs to be established.

For every returned requirement: key must remain stable and grounded in the source; label must be claimant-friendly; question_hint must be natural conversation; required=true only when source support makes it necessary or the applicable condition is met; evidence_type is photo or document only when source support exists; condition must be preserved when conditional; never create a requirement merely because it is common insurance practice.

Insurance Type: {insurance_type}
Claimant Incident Summary: {incident_description}
Known Claim Facts:
{claim_facts or {}}

POLICY REQUIREMENT MANIFEST:
{json.dumps(inventory, ensure_ascii=False, default=str)[:30000]}

RETRIEVED POLICY SUPPORTING EXCERPTS:
{policy_prompt_context}

RETRIEVED REGULATORY/GUIDANCE EXCERPTS:
{regulatory_prompt_context}

Return RequirementPlan.
"""
    plan: RequirementPlan | None = None
    try:
        result = invoke_with_retry(
            lambda: structured_output(llm, RequirementPlan).invoke(prompt),
            operation_name="claim-specific requirement resolution",
            attempts=2,
        )
        if isinstance(result, RequirementPlan) and result.requirements:
            plan = result
    except LLMTransientError:
        raise
    except Exception:
        plan = None

    if plan and plan.requirements:
        source_refs = [{
            "source_name": doc.get("source_name"),
            "source_uri": doc.get("source_uri"),
            "document_id": doc.get("document_id") or doc.get("id"),
            "chunk_id": doc.get("chunk_id") or doc.get("id"),
            "score": doc.get("rerank_score", doc.get("score")),
        } for doc in [*policy_context, *regulatory_context]]
        manifest_by_key = {str(x["key"]): x for x in manifest_requirements}
        output = []
        for req in plan.requirements:
            item = req.model_dump()
            manifest_item = manifest_by_key.get(str(req.key))
            item["provenance"] = {
                "type": "policy_requirement_manifest" if manifest_item else "retrieved_policy_context",
                "sources": source_refs,
            }
            if manifest_item:
                item["provenance"]["manifest_source_chunk_ids"] = manifest_item.get("source_chunk_ids", [])
                item["provenance"]["source_excerpt"] = manifest_item.get("source_excerpt", "")
                item["category"] = manifest_item.get("category")
                item["basis"] = manifest_item.get("basis")
            output.append(item)
        return output

    if manifest_requirements:
        return [
            {
                **{k: item.get(k) for k in ("key", "label", "question_hint", "required", "evidence_type", "condition", "category", "basis") if item.get(k) is not None},
                "provenance": {
                    "type": "policy_requirement_manifest_fallback",
                    "manifest_source_chunk_ids": item.get("source_chunk_ids", []),
                    "source_excerpt": item.get("source_excerpt", ""),
                },
            }
            for item in manifest_requirements
        ]
    return []

def get_provisional_requirements(llm=None, *, insurance_type: str, claim_facts: dict[str, Any], conversation: str = "") -> list[dict]:
    """Create provisional candidates only when authoritative knowledge is unavailable."""
    if llm is None:
        try:
            llm = get_configured_llm()
        except Exception:
            return []
    prompt = f"""You are an insurance claim intake conversation planner.
The claimant has completed baseline verification. Identify a small number of claim-specific details reasonable to collect based ONLY on the claimant's incident facts and insurance type.
This is NOT a policy decision. Do not state anything is mandatory or covered. Do not repeat baseline fields: policy number, incident date, insurance type, incident description, incident location, estimated loss amount. Do not ask when the claimant reported this claim through the current intake application.
Insurance type: {insurance_type}
Claim facts: {claim_facts}
Recent claimant conversation: {conversation}
Return RequirementPlan. Use evidence_type only when claimant facts directly indicate evidence is relevant. Mark these as provisional, not policy-mandated.
"""
    try:
        result = invoke_with_retry(
            lambda: structured_output(llm, RequirementPlan).invoke(prompt),
            operation_name="provisional claim-specific planning",
            attempts=1,
        )
        plan = result if isinstance(result, RequirementPlan) else RequirementPlan.model_validate(result)
    except Exception:
        return []
    output = []
    for req in plan.requirements[:8]:
        item = req.model_dump()
        if not _notification_is_current_intake(item):
            item["provenance"] = {"type": "provisional_claim_context"}
            output.append(item)
    return output
