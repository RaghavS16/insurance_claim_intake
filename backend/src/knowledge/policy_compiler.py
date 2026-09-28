"""Policy-level requirement compiler and claim-specific requirement resolver."""
from __future__ import annotations
import json
from typing import Any
from pydantic import BaseModel, Field
from src.agents.llm_factory import get_configured_llm, invoke_with_retry, structured_output
from src.knowledge.requirements import Requirement, RequirementPlan

class RequirementCandidate(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)

def _source_text(chunks: list[dict[str, Any]], limit: int = 16000) -> str:
    parts=[]; used=0
    for row in chunks:
        text=str(row.get("text") or "").strip()
        if not text: continue
        part=f"[chunk_id={row.get('chunk_id')}]\n{text}"
        if used+len(part)>limit: break
        parts.append(part); used += len(part)
    return "\n\n".join(parts)

def _compile_batch(llm, insurance_type: str, chunks: list[dict[str, Any]]) -> list[Requirement]:
    prompt=f"""Compile authoritative insurance claim requirements from these policy wording chunks for {insurance_type}.
Use ONLY the policy text. Do not use general insurance practice and do not invent a checklist.
Extract claimant/policy information, incident information, third-party information, notifications/deadlines,
evidence/documents, repair/settlement information, add-ons/endorsements, and conditional obligations.
Coverage descriptions that do not create claimant action are not requirements.
For each requirement return key, label, question_hint, required, evidence_type (photo/document/null),
condition (or null), category, source_section, source_chunk_ids, and source_excerpt (<=280 chars).
Conditional requirements remain required=true with their condition.
POLICY CHUNKS:
{_source_text(chunks)}"""
    result=invoke_with_retry(lambda: structured_output(llm, RequirementCandidate).invoke(prompt),
                             operation_name="policy requirement batch compilation", attempts=2)
    if isinstance(result, RequirementCandidate): return result.requirements
    if isinstance(result, dict): return RequirementCandidate.model_validate(result).requirements
    return []

def compile_policy_requirements(*, document_id: str, insurance_type: str,
                                 chunks: list[dict[str, Any]], llm=None) -> list[dict[str, Any]]:
    if not chunks or not insurance_type: return []
    llm=llm or get_configured_llm()
    candidates = []
    batch_size = 4
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        try:
            batch_requirements = _compile_batch(llm, insurance_type, batch)
        except Exception as exc:
            raise RuntimeError(
                f"Policy requirement compilation failed for batch {start // batch_size + 1}"
            ) from exc
        expected_chunk_ids = {str(row.get("chunk_id")) for row in batch if row.get("chunk_id")}
        for req in batch_requirements:
            if {str(x) for x in (req.source_chunk_ids or [])} & expected_chunk_ids:
                candidates.append(req)
    if not candidates: return []
    prompt=f"""Synthesize the final authoritative claim requirement manifest for {insurance_type}.
Use ONLY the policy-derived candidates below. Merge duplicates, preserve conditions and provenance,
do not invent fields/documents, and preserve the distinction between information, evidence,
notification, repair and add-on requirements.
CANDIDATES:
{json.dumps([r.model_dump() for r in candidates], ensure_ascii=False)}"""
    try:
        result=invoke_with_retry(lambda: structured_output(llm,RequirementPlan).invoke(prompt),
                                 operation_name="policy requirement manifest synthesis", attempts=2)
        final=result.requirements if isinstance(result,RequirementPlan) else RequirementPlan.model_validate(result).requirements
        if not final:
            final = candidates
    except Exception:
        final=candidates
    merged={}
    for req in final:
        item=req.model_dump(); key=str(item.get("key") or "").strip().lower()
        if not key: continue
        item["key"]=key
        item["provenance"]={"document_id":document_id,"type":"policy_requirement_manifest"}
        if key not in merged: merged[key]=item
        else:
            old=merged[key]
            old["source_chunk_ids"]=sorted(set(old.get("source_chunk_ids") or []) | set(item.get("source_chunk_ids") or []))
            for k in ("source_section","source_excerpt","condition","evidence_type"):
                if not old.get(k) and item.get(k): old[k]=item[k]
    return list(merged.values())

def resolve_requirement_manifest(*, manifest: list[dict[str, Any]], insurance_type: str,
                                 claim_facts: dict[str, Any], llm=None) -> list[dict[str, Any]]:
    """Select applicable requirements for this claim without losing unresolved conditions."""
    if not manifest: return []
    llm=llm or get_configured_llm()
    prompt=f"""Resolve this authoritative {insurance_type} policy requirement manifest against the known claim facts.
Include requirements that clearly apply. Exclude requirements whose conditions clearly do not apply.
If a condition cannot yet be determined from the facts, KEEP the requirement and preserve its condition so
the conversation can collect the fact needed to resolve it. Never invent a claimant fact.
Return the same RequirementPlan structure and preserve source provenance.
KNOWN CLAIM FACTS:
{json.dumps(claim_facts,ensure_ascii=False,default=str)}
REQUIREMENT MANIFEST:
{json.dumps(manifest,ensure_ascii=False,default=str)}"""
    try:
        result=invoke_with_retry(lambda: structured_output(llm,RequirementPlan).invoke(prompt),
                                 operation_name="claim-specific policy requirement resolution", attempts=2)
        final=result.requirements if isinstance(result,RequirementPlan) else RequirementPlan.model_validate(result).requirements
        by_key = {str(item.get("key") or "").strip().lower(): item for item in manifest if item.get("key")}
        output = []
        for req in final:
            item = req.model_dump()
            key = str(item.get("key") or "").strip().lower()
            if not key or key not in by_key:
                continue
            source = by_key[key]
            item["key"] = key
            item["source_chunk_ids"] = list(dict.fromkeys((source.get("source_chunk_ids") or []) + (item.get("source_chunk_ids") or [])))
            item["source_section"] = item.get("source_section") or source.get("source_section")
            item["source_excerpt"] = item.get("source_excerpt") or source.get("source_excerpt")
            item["condition"] = item.get("condition") or source.get("condition")
            item["provenance"] = source.get("provenance", {"type": "policy_requirement_manifest"})
            output.append(item)
        return output
    except Exception:
        # Safe fallback: keep unconditional requirements and conditionals rather than silently dropping them.
        return list(manifest)
