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
    candidate_by_key={}
    for req in candidates:
        item=req.model_dump()
        key=str(item.get("key") or "").strip().lower()
        if key:
            candidate_by_key[key]=item

    for req in final:
        item=req.model_dump(); key=str(item.get("key") or "").strip().lower()
        if not key: continue
        source=candidate_by_key.get(key, {})
        item["key"]=key
        item["source_chunk_ids"]=sorted(set(source.get("source_chunk_ids") or []) | set(item.get("source_chunk_ids") or []))
        item["source_section"]=item.get("source_section") or source.get("source_section")
        item["source_excerpt"]=item.get("source_excerpt") or source.get("source_excerpt")
        item["condition"]=item.get("condition") or source.get("condition")
        item["evidence_type"]=item.get("evidence_type") or source.get("evidence_type")
        item["provenance"]={"document_id":document_id,"type":"policy_requirement_manifest"}
        if key not in merged: merged[key]=item
        else:
            old=merged[key]
            old["source_chunk_ids"]=sorted(set(old.get("source_chunk_ids") or []) | set(item.get("source_chunk_ids") or []))
            for k in ("source_section","source_excerpt","condition","evidence_type"):
                if not old.get(k) and item.get(k): old[k]=item[k]

    # Synthesis is allowed to merge wording, but never to drop a requirement that
    # was extracted from the complete policy. Add any candidate it omitted.
    for key, source in candidate_by_key.items():
        if key in merged:
            continue
        source["key"]=key
        source["provenance"]={"document_id":document_id,"type":"policy_requirement_manifest"}
        merged[key]=source

    return list(merged.values())

def _condition_is_clearly_false(condition: str | None, claim_facts: dict[str, Any]) -> bool:
    """Conservatively exclude only conditions disproved by explicit claim facts."""
    if not condition:
        return False
    text = condition.lower()
    facts = json.dumps(claim_facts, ensure_ascii=False, default=str).lower()
    negative_pairs = (
        ("theft", ("collision", "accident", "crash", "medical", "illness", "trip delay", "baggage")),
        ("burglary", ("collision", "medical", "illness", "trip delay")),
        ("fire brigade", ("medical", "motor accident", "travel")),
        ("post-mortem", ("no death", "survived", "alive")),
        ("loss of rent", ("motor", "health", "travel", "cyber")),
        ("online shopping", ("motor", "home", "health", "travel")),
        ("social media", ("motor", "home", "health", "travel")),
        ("surgery", ("no surgery", "medication only", "outpatient only")),
        ("implant", ("no implant", "medication only")),
        ("baggage", ("motor", "home", "health", "cyber")),
        ("flight delay", ("motor", "home", "health", "cyber")),
        ("cashless", ("reimbursement",)),
    )
    for trigger, negatives in negative_pairs:
        if trigger in text and any(n in facts for n in negatives):
            return True
    return False


def resolve_requirement_manifest(*, manifest: list[dict[str, Any]], insurance_type: str,
                                 claim_facts: dict[str, Any], llm=None) -> list[dict[str, Any]]:
    """Resolve applicability conservatively; never let an LLM shrink the authoritative checklist."""
    if not manifest:
        return []
    by_key = {
        str(item.get("key") or "").strip().lower(): dict(item)
        for item in manifest if item.get("key")
    }
    if not by_key:
        return []

    llm = llm or get_configured_llm()
    prompt = f"""Resolve applicability for this authoritative {insurance_type} claim requirement manifest.
For EVERY manifest key, return the same requirement object when it applies or when its condition is still unknown.
Only omit a key when the claim facts clearly prove its condition does not apply.
Never invent claimant facts and never remove a source-backed requirement merely because the claim fact is missing.
KNOWN CLAIM FACTS:
{json.dumps(claim_facts, ensure_ascii=False, default=str)}
REQUIREMENT MANIFEST:
{json.dumps(manifest, ensure_ascii=False, default=str)}"""

    llm_items: dict[str, dict[str, Any]] = {}
    llm_failed = False
    try:
        result = invoke_with_retry(
            lambda: structured_output(llm, RequirementPlan).invoke(prompt),
            operation_name="claim-specific policy requirement resolution", attempts=2,
        )
        final = result.requirements if isinstance(result, RequirementPlan) else RequirementPlan.model_validate(result).requirements
        llm_items = {
            str(req.key).strip().lower(): req.model_dump()
            for req in final
            if req.key
        }
    except Exception:
        # On resolver failure, preserve the complete authoritative manifest.
        # Applicability pruning depends on successful claim-specific resolution;
        # fallback mode must never silently drop source-backed requirements.
        llm_failed = True
        llm_items = {}

    output = []
    for key, source in by_key.items():
        if not llm_failed and _condition_is_clearly_false(source.get("condition"), claim_facts):
            continue
        enriched = dict(source)
        model_item = llm_items.get(key)
        if model_item:
            for field in ("label", "question_hint", "required", "evidence_type", "condition", "category", "source_section", "source_excerpt"):
                if model_item.get(field) not in (None, ""):
                    enriched[field] = model_item[field]
            enriched["source_chunk_ids"] = list(dict.fromkeys(
                (source.get("source_chunk_ids") or []) + (model_item.get("source_chunk_ids") or [])
            ))
        enriched["key"] = key
        enriched["provenance"] = source.get("provenance", {"type": "policy_requirement_manifest"})
        output.append(enriched)
    return output
