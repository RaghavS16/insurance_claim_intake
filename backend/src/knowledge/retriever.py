"""Production RAG orchestration extracting requirements directly from authoritative policy and regulatory documents."""
from datetime import date
from src.agents.llm_factory import LLMTransientError, get_configured_llm, get_fast_llm, is_transient_llm_error
from .requirements import get_requirements_from_context, get_provisional_requirements
from .store import search, list_policy_documents, get_document_chunks, get_cached_requirement_manifest, save_requirement_manifest
from .reranker import rerank
from .policy_compiler import compile_policy_requirements, resolve_requirement_manifest

class KnowledgeRetrievalError(RuntimeError):
    pass

class KnowledgeRetriever:
    def retrieve(self, *, insurance_type: str, policy_number: str | None = None, incident_date: date | None = None, query: str = "", intake_channel: str = "insurer_web_portal", intake_started_at: str | None = None, claim_facts: dict | None = None, tenant_id: str | None = None, jurisdiction: str | None = None) -> dict:
        facts = dict(claim_facts or {})
        incident_description = str(query or facts.get("event_description") or "").strip()
        searchable_facts = " ".join(
            f"{key}: {value}"
            for key, value in facts.items()
            if value not in (None, "", "UNKNOWN") and key not in {"event_description"}
        )
        q = " ".join(part for part in (insurance_type, incident_description, searchable_facts) if part).strip()[:4000]
        if not insurance_type:
            return {"available": False, "status": "INVALID_CONTEXT", "requirements": [], "policy": [], "regulations": []}
        
        policy = []
        guidance = []
        manifest = []
        policy_docs = []
        policy_docs_found = False
        # Document-level compilation is authoritative when available, but a DB/cache
        # outage must not disable the existing retrieval path.
        try:
            policy_docs = list_policy_documents(insurance_type=insurance_type, policy_number=policy_number, incident_date=incident_date, tenant_id=tenant_id, jurisdiction=jurisdiction)
            policy_docs_found = bool(policy_docs)
            for doc in policy_docs:
                cached = get_cached_requirement_manifest(doc["document_id"], tenant_id)
                if not cached:
                    chunks = get_document_chunks(doc["document_id"], tenant_id)
                    try:
                        cached = compile_policy_requirements(document_id=doc["document_id"], insurance_type=insurance_type, chunks=chunks)
                        if cached: save_requirement_manifest(doc["document_id"], cached, tenant_id)
                    except Exception:
                        cached = []
                manifest.extend(cached)
        except Exception:
            manifest = []

        selected_policy_version = None
        if policy_docs:
            selected_policy_version = (policy_docs[0].get("policy_version") or (policy_docs[0].get("metadata") or {}).get("policy_version"))

        if manifest:
            manifest = list({str(x.get("key")): x for x in manifest if x.get("key")}.values())
            try:
                resolved = resolve_requirement_manifest(
                    manifest=manifest,
                    insurance_type=insurance_type,
                    claim_facts={**facts, "incident": incident_description},
                )
            except Exception:
                resolved = []
            if resolved:
                return {
                    "available": True,
                    "status": "OK",
                    "requirements": resolved,
                    "policy": search(
                        q,
                        insurance_type=insurance_type,
                        policy_number=policy_number,
                        document_types=["policy_wording"],
                        incident_date=incident_date,
                        tenant_id=tenant_id,
                        jurisdiction=jurisdiction,
                    ),
                    "regulations": search(
                        q,
                        insurance_type=insurance_type,
                        document_types=["regulation", "guideline", "claim_requirement"],
                        incident_date=incident_date,
                        tenant_id=tenant_id,
                        jurisdiction=jurisdiction,
                    ),
                    "authoritative": True,
                    "planning_model": "policy_manifest",
                    "policy_version": selected_policy_version,
                }

        # If an applicable policy wording exists, never replace a failed or unresolved
        # policy manifest with top-k semantic chunks and call that authoritative.
        # That was the source of the old "Claude sees the whole policy, our AI sees
        # five accident-similar chunks" behavior.
        if policy_docs_found:
            try:
                policy = search(
                    q,
                    insurance_type=insurance_type,
                    policy_number=policy_number,
                    document_types=["policy_wording"],
                    incident_date=incident_date,
                )
            except Exception:
                policy = []
            return {
                "available": False,
                "status": "POLICY_REQUIREMENT_MANIFEST_UNAVAILABLE",
                "requirements": [],
                "policy": policy,
                "regulations": [],
                "authoritative": False,
                "planning_model": "policy_manifest_required",
                "policy_version": selected_policy_version,
            }

        try:
            policy = search(q, insurance_type=insurance_type, policy_number=policy_number, document_types=["policy_wording"], incident_date=incident_date, tenant_id=tenant_id, jurisdiction=jurisdiction)
            guidance = search(q, insurance_type=insurance_type, document_types=["regulation", "guideline", "claim_requirement"], incident_date=incident_date, tenant_id=tenant_id, jurisdiction=jurisdiction)
        except Exception:
            policy, guidance = [], []

        if policy:
            try:
                policy = rerank(q, policy, top_n=5)
            except Exception:
                pass
        if guidance:
            try:
                guidance = rerank(q, guidance, top_n=5)
            except Exception:
                pass

        if not policy and not guidance:
            try:
                provisional_llm = get_fast_llm()
            except Exception:
                provisional_llm = None
            provisional = get_provisional_requirements(
                provisional_llm,
                insurance_type=insurance_type,
                claim_facts={
                    **facts,
                    "policy_number": policy_number,
                    "incident_date": str(incident_date) if incident_date else None,
                    "incident": incident_description,
                },
                conversation=incident_description,
            )
            return {
                "available": bool(provisional),
                "status": "PROVISIONAL" if provisional else "NO_RELEVANT_KNOWLEDGE",
                "requirements": provisional,
                "policy": [],
                "regulations": [],
                "authoritative": False,
            }

        try:
            llm = get_configured_llm()
            requirements = get_requirements_from_context(
                llm,
                insurance_type=insurance_type,
                policy_context=policy,
                regulatory_context=guidance,
                incident_description=incident_description,
                intake_channel=intake_channel,
                intake_started_at=intake_started_at,
                claim_facts=facts,
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
            )
        except Exception as exc:
            # A transient reasoning-model failure must not stop the claimant flow.
            # Retry requirement planning once with the low-latency model before
            # surfacing a temporary/unavailable state.
            try:
                fast_llm = get_fast_llm()
                requirements = get_requirements_from_context(
                    fast_llm,
                    insurance_type=insurance_type,
                    policy_context=policy,
                    regulatory_context=guidance,
                    incident_description=incident_description,
                    intake_channel=intake_channel,
                    intake_started_at=intake_started_at,
                    claim_facts=facts,
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                )
            except Exception:
                requirements = []
            if requirements:
                source_kind = "reasoning_fallback"
                return {
                    "available": True,
                    "status": "OK",
                    "requirements": requirements,
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": True,
                    "planning_model": source_kind,
                }

            # If authoritative requirement planning is temporarily unavailable,
            # keep the claimant conversation moving with a clearly marked
            # provisional plan derived from the claimant's facts. Submission remains
            # blocked until an authoritative RAG plan is available.
            try:
                provisional = get_provisional_requirements(
                    fast_llm if "fast_llm" in locals() else None,
                    insurance_type=insurance_type,
                    claim_facts={
                        **facts,
                        "policy_number": policy_number,
                        "incident_date": str(incident_date) if incident_date else None,
                        "incident": incident_description,
                    },
                    conversation=incident_description,
                )
            except Exception:
                provisional = []
            if provisional:
                return {
                    "available": True,
                    "status": "PROVISIONAL",
                    "requirements": provisional,
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": False,
                    "planning_model": "provisional_fallback",
                }

            # Preserve the transient-provider state so the conversational layer can
            # retry RAG instead of incorrectly reporting a permanent missing plan.
            transient_text = str(exc).lower()
            if "HF_TOKEN is required" in str(exc) or "API key" in str(exc):
                return {
                    "available": False,
                    "status": "LLM_CONFIGURATION_UNAVAILABLE",
                    "requirements": [],
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": False,
                }
            if (
                isinstance(exc, LLMTransientError)
                or is_transient_llm_error(exc)
                or any(token in transient_text for token in ("503", "429", "timeout", "temporarily unavailable", "rate limit", "overloaded"))
            ):
                return {
                    "available": False,
                    "status": "LLM_TEMPORARILY_UNAVAILABLE",
                    "requirements": [],
                    "policy": policy,
                    "regulations": guidance,
                }
            requirements = []

        if not requirements:
            provisional = get_provisional_requirements(
                None,
                insurance_type=insurance_type,
                claim_facts={
                    **facts,
                    "policy_number": policy_number,
                    "incident_date": str(incident_date) if incident_date else None,
                    "incident": incident_description,
                },
                conversation=incident_description,
            )
            if provisional:
                return {
                    "available": True,
                    "status": "PROVISIONAL",
                    "requirements": provisional,
                    "policy": policy,
                    "regulations": guidance,
                    "authoritative": False,
                }
            return {
                "available": False,
                "status": "REQUIREMENT_PLAN_UNAVAILABLE",
                "requirements": [],
                "policy": policy,
                "regulations": guidance,
                "authoritative": False,
            }

        return {
            "available": True,
            "status": "OK",
            "requirements": requirements,
            "policy": policy,
            "regulations": guidance,
            "authoritative": True,
        }

    def answer_query(
        self,
        *,
        query: str,
        insurance_type: str | None = None,
        policy_number: str | None = None,
        incident_date: date | None = None,
        claim_facts: dict | None = None,
        top_k: int = 6,
        tenant_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> dict:
        """Answer an arbitrary claimant question from retrieved policy/guidance evidence.

        This is deliberately separate from requirement planning. It is query-first:
        claimant questions can be answered before baseline confirmation or policy
        verification. No policy-specific assertion is generated without retrieved
        evidence.
        """
        question = " ".join(str(query or "").split()).strip()
        if not question:
            return {
                "answer": "Tell me what you would like to know about your insurance claim.",
                "grounded": False,
                "sources": [],
                "status": "EMPTY_QUERY",
            }

        facts = dict(claim_facts or {})
        fact_context = " ".join(
            f"{key}: {value}"
            for key, value in facts.items()
            if value not in (None, "", "UNKNOWN")
            and key not in {"event_description"}
        )
        retrieval_query = " ".join(
            part for part in (question, insurance_type or "", fact_context) if part
        ).strip()[:4000]

        document_types = [
            "policy_wording",
            "regulation",
            "guideline",
            "claim_requirement",
        ]
        rows: list[dict] = []
        try:
            rows = search(
                retrieval_query,
                insurance_type=insurance_type,
                policy_number=policy_number,
                document_types=document_types,
                incident_date=incident_date,
                limit=max(top_k * 2, 8),
                tenant_id=tenant_id,
                jurisdiction=jurisdiction,
            )
        except Exception:
            rows = []

        # A general process question is still valid before the claimant supplies a
        # policy number/type. Broaden retrieval once rather than forcing intake first.
        if not rows and (insurance_type or policy_number):
            try:
                rows = search(
                    question,
                    document_types=document_types,
                    limit=max(top_k * 2, 8),
                    tenant_id=tenant_id,
                    jurisdiction=jurisdiction,
                )
            except Exception:
                rows = []

        try:
            ranked = rerank(retrieval_query, rows, top_n=top_k) if rows else []
        except Exception:
            ranked = rows[:top_k]

        sources = [
            {
                key: row.get(key)
                for key in (
                    "chunk_id",
                    "document_id",
                    "source_name",
                    "source_uri",
                    "document_type",
                    "insurance_type",
                    "score",
                    "rerank_score",
                    "page_number",
                    "section_number",
                    "clause_number",
                    "citation_label",
                    "jurisdiction",
                    "document_version",
                    "text",
                )
                if row.get(key) is not None
            }
            for row in ranked
        ]
        if not sources:
            return {
                "answer": (
                    "I can help with the insurance process, but I do not have a matching "
                    "policy or claims-guidance source indexed for that question yet, so I "
                    "won't guess at a policy-specific answer. I can still help you collect "
                    "the details and documents needed for your claim."
                ),
                "grounded": False,
                "sources": [],
                "status": "NO_RELEVANT_KNOWLEDGE",
            }

        evidence_text = "\n\n".join(
            (
                f"[SOURCE {idx}] {row.get("source_name") or "Unknown source"} "
                f"({row.get("document_type") or "guidance"}; {row.get("citation_label") or "citation unavailable"})\n"
                f"{str(row.get('text') or '')[:2500]}"
            )
            for idx, row in enumerate(sources, 1)
        )
        prompt = f"""You are the claimant-facing insurance RAG answerer.

Answer the claimant's actual question directly using ONLY the retrieved evidence below.
The claimant may ask a general process question, a policy question, a coverage question,
a document/evidence question, or a question about what happens next.

Rules:
- Answer the question first. Do not force a baseline questionnaire before answering.
- Treat retrieved policy wording as authoritative for policy-specific terms.
- Treat retrieved regulatory/guidance sources as authoritative for procedural or regulatory points.
- Never invent exclusions, coverage, limits, waiting periods, deadlines, reimbursement rules, or required documents.
- If the evidence does not establish a policy-specific answer, explicitly say that the indexed sources do not establish it.
- Do not copy the claimant's missing-field list into the answer.
- Keep the response clear and voice-friendly, normally 2 to 6 sentences.
- Every policy/coverage/deadline/evidence assertion must cite at least one supplied source using its citation_label. If citation_label is unavailable, explicitly say exact clause/page provenance is unavailable and do not present the statement as clause-supported.
- Intake collection is parallel work. Do not ask for claim details unless the question itself is about filing/processing
  or the caller is clearly continuing a claim; when you do ask, ask for only one useful next detail.

Claim context:
Insurance type: {insurance_type or "unknown"}
Policy number: {policy_number or "unknown"}
Incident date: {incident_date or "unknown"}

Retrieved evidence:
{evidence_text}

Claimant question:
{question}
"""
        try:
            result = invoke_with_retry(
                lambda: get_fast_llm().invoke(prompt),
                operation_name="claimant RAG question answering",
                attempts=1,
            )
            content = getattr(result, "content", result)
            if isinstance(content, list):
                answer = " ".join(
                    item if isinstance(item, str)
                    else str(item.get("text") or "")
                    for item in content
                    if isinstance(item, (str, dict))
                ).strip()
            else:
                answer = str(content or "").strip()
            if answer:
                policy_specific = bool(
                    insurance_type
                    or policy_number
                    or any(
                        token in question.lower()
                        for token in (
                            "cover", "coverage", "exclude", "exclusion", "deductible",
                            "limit", "waiting", "deadline", "reimburse", "eligible",
                            "required document", "evidence",
                        )
                    )
                )
                missing_citation = policy_specific and not all(
                    source.get("citation_label") and str(source.get("citation_label")) in answer
                    for source in sources[:1]
                )
                if missing_citation:
                    answer = (
                        "I found relevant material, but the retrieved source does not provide "
                        "a verifiable clause or page citation for that statement. I won't present "
                        "it as a policy-supported answer."
                    )
                    return {
                        "answer": answer,
                        "grounded": False,
                        "sources": sources,
                        "status": "CITATION_REQUIRED",
                    }
                return {
                    "answer": answer,
                    "grounded": True,
                    "sources": sources,
                    "status": "OK",
                }
        except Exception:
            pass

        return {
            "answer": (
                "I found relevant insurance guidance, but the answer service is temporarily "
                "unavailable. I won't guess at the policy-specific details."
            ),
            "grounded": False,
            "sources": sources,
            "status": "LLM_TEMPORARILY_UNAVAILABLE",
        }
