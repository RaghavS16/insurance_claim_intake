"""Compile a whole policy document into an auditable claim-requirement manifest.

The claimant-time RAG flow should not rediscover a policy checklist from a handful of
chunks that happen to resemble an accident narrative. This module performs hierarchical
document-level extraction and persists the resulting manifest in KnowledgeDocument.metadata_json.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.agents.llm_factory import get_configured_llm, invoke_with_retry, structured_output
from src.database.models import KnowledgeChunk, KnowledgeDocument
from src.database.session import SessionLocal


class RequirementCandidate(BaseModel):
    key: str
    label: str
    category: str = "claim_information"
    required: bool = True
    condition: str | None = None
    evidence_type: str | None = None
    question_hint: str = ""
    basis: str = "explicit"
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_excerpt: str = ""


class RequirementCandidateBatch(BaseModel):
    requirements: list[RequirementCandidate] = Field(default_factory=list)


class RequirementManifest(BaseModel):
    insurance_type: str
    source_document_id: str
    requirements: list[RequirementCandidate] = Field(default_factory=list)
    compilation_version: str = "policy-manifest-v1"
    rationale: str = ""


def _compact_chunk(chunk: dict[str, Any]) -> str:
    return (
        f"CHUNK_ID={chunk['chunk_id']}\n"
        f"TEXT:\n{chunk['text'][:5000]}"
    )


def _extract_batch(llm: Any, insurance_type: str, chunks: list[dict[str, Any]]) -> list[RequirementCandidate]:
    prompt = f"""You are compiling an authoritative insurance claim-intake requirement manifest from
a policy wording document for {insurance_type} insurance.

Read ONLY the supplied policy excerpts. Identify every claimant-facing detail, condition,
notification obligation, or supporting evidence that the wording explicitly requires OR
directly supports as necessary to assess/process the claim.

Important:
- Do not invent requirements from generic insurance practice.
- Do not turn every mention of a document into a mandatory upload.
- Preserve conditional requirements with an explicit condition.
- Distinguish ordinary claim information from evidence/documents.
- A requirement can be derived from a clause when the clause clearly makes that information
  necessary for a claim, but set basis='necessary_for_assessment' rather than pretending the
  policy uses a checklist.
- Use stable snake_case keys.
- Capture source_chunk_ids and a short source_excerpt for auditability.
- Return an empty list when the excerpts contain no supported claim-intake requirement.

Insurance type: {insurance_type}

POLICY EXCERPTS:
{chr(10).join(_compact_chunk(c) for c in chunks)}
"""
    result = invoke_with_retry(
        lambda: structured_output(llm, RequirementCandidateBatch).invoke(prompt),
        operation_name="policy requirement batch compilation",
        attempts=2,
    )
    return list(result.requirements)


def _synthesise_manifest(
    llm: Any,
    *,
    insurance_type: str,
    document_id: str,
    candidates: list[RequirementCandidate],
) -> RequirementManifest:
    payload = [c.model_dump() for c in candidates[:160]]
    prompt = f"""Create the final claim-intake requirement manifest for this {insurance_type} policy.

You are given candidate requirements extracted from the COMPLETE policy document in batches.
Deduplicate semantically equivalent items, retain distinct conditional requirements, and
do not add anything that is not supported by the candidates.

Rules:
- Keep the broadest useful set of claim-information requirements supported by the policy.
- Keep evidence requirements only when the policy supports them.
- Never convert a conditional obligation into an unconditional requirement.
- Keep condition text precise enough for later applicability evaluation.
- Preserve source_chunk_ids and source_excerpt for every retained requirement.
- question_hint should be a natural claimant-facing prompt, not a rigid questionnaire item.
- The manifest is policy knowledge, not a coverage decision.

Insurance type: {insurance_type}
Source document id: {document_id}

CANDIDATES:
{payload}
"""
    result = invoke_with_retry(
        lambda: structured_output(llm, RequirementManifest).invoke(prompt),
        operation_name="policy requirement manifest synthesis",
        attempts=2,
    )
    result.insurance_type = insurance_type
    result.source_document_id = document_id
    return result


def compile_policy_document(
    *,
    document_id: str,
    insurance_type: str,
    chunks: list[dict[str, Any]],
    llm: Any | None = None,
) -> dict[str, Any]:
    """Compile the complete ordered policy into a reusable requirement manifest."""
    if not chunks:
        return {
            "insurance_type": insurance_type,
            "source_document_id": document_id,
            "requirements": [],
            "compilation_version": "policy-manifest-v1",
            "rationale": "No readable policy chunks were available.",
        }

    llm = llm or get_configured_llm()
    candidates: list[RequirementCandidate] = []
    # 8 x ~450-word chunks keeps each extraction prompt comfortably bounded while
    # still providing enough surrounding policy context for cross-clause requirements.
    for start in range(0, len(chunks), 8):
        candidates.extend(
            _extract_batch(llm, insurance_type, chunks[start : start + 8])
        )

    if not candidates:
        return {
            "insurance_type": insurance_type,
            "source_document_id": document_id,
            "requirements": [],
            "compilation_version": "policy-manifest-v1",
            "rationale": "The policy contained no directly supported claim-intake requirements in the extracted text.",
        }

    manifest = _synthesise_manifest(
        llm,
        insurance_type=insurance_type,
        document_id=document_id,
        candidates=candidates,
    )
    return manifest.model_dump()


def get_or_compile_policy_manifest(
    *,
    insurance_type: str,
    policy_number: str | None = None,
    incident_date: Any | None = None,
    llm: Any | None = None,
) -> dict[str, Any] | None:
    """Return the cached manifest for the applicable policy, compiling it once if needed."""
    db = SessionLocal()
    try:
        conditions = [
            KnowledgeDocument.document_type == "policy_wording",
            (KnowledgeDocument.insurance_type == insurance_type)
            | (KnowledgeDocument.insurance_type.is_(None)),
        ]
        metadata = KnowledgeDocument.metadata_json
        if policy_number:
            conditions.append(
                (metadata["policy_number"].as_string() == policy_number)
                | (metadata["policy_number"].as_string().is_(None))
            )
        if incident_date:
            event_date = incident_date.isoformat()
            effective_from = metadata["effective_from"].as_string()
            effective_to = metadata["effective_to"].as_string()
            conditions.extend([
                (effective_from.is_(None)) | (effective_from <= event_date),
                (effective_to.is_(None)) | (effective_to >= event_date),
            ])

        docs = (
            db.execute(
                select(KnowledgeDocument)
                .where(*conditions)
                .order_by(KnowledgeDocument.created_at.desc())
            )
            .scalars()
            .all()
        )
        if not docs:
            return None

        # Prefer an exact policy-number match when metadata is available.
        if policy_number:
            exact = [
                d for d in docs
                if str((d.metadata_json or {}).get("policy_number") or "").strip().upper()
                == str(policy_number).strip().upper()
            ]
            if exact:
                docs = exact

        doc = docs[0]
        cached = (doc.metadata_json or {}).get("requirement_manifest")
        if isinstance(cached, dict) and cached.get("requirements") is not None:
            return cached

        chunks = (
            db.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == doc.id)
                .order_by(KnowledgeChunk.chunk_index.asc())
            )
            .scalars()
            .all()
        )
        chunk_rows = [
            {"chunk_id": str(c.id), "text": str(c.text or "")}
            for c in chunks
        ]
    finally:
        db.close()

    try:
        manifest = compile_policy_document(
            document_id=str(doc.id),
            insurance_type=insurance_type,
            chunks=chunk_rows,
            llm=llm,
        )
    except Exception:
        return None

    db = SessionLocal()
    try:
        persisted = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == str(doc.id)).first()
        if persisted:
            metadata_json = dict(persisted.metadata_json or {})
            metadata_json["requirement_manifest"] = manifest
            persisted.metadata_json = metadata_json
            db.commit()
    finally:
        db.close()
    return manifest
