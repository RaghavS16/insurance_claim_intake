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
    def retrieve(self, *, insurance_type: str, policy_number: str | None = None, incident_date: date | None = None, query: str = "", intake_channel: str = "insurer_web_portal", intake_started_at: str | None = None, claim_facts: dict | None = None) -> dict:
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
        policy_docs_found = False
        # Document-level compilation is authoritative when available, but a DB/cache
        # outage must not disable the existing retrieval path.
        try:
            policy_docs = list_policy_documents(insurance_type=insurance_type, policy_number=policy_number, incident_date=incident_date)
            policy_docs_found = bool(policy_docs)
            for doc in policy_docs:
                cached = get_cached_requirement_manifest(doc["document_id"])
                if not cached:
                    chunks = get_document_chunks(doc["document_id"])
                    try:
                        cached = compile_policy_requirements(document_id=doc["document_id"], insurance_type=insurance_type, chunks=chunks)
                        if cached: save_requirement_manifest(doc["document_id"], cached)
                    except Exception:
                        cached = []
                manifest.extend(cached)
        except Exception:
            manifest = []

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
                    ),
                    "regulations": search(
                        q,
                        insurance_type=insurance_type,
                        document_types=["regulation", "guideline", "claim_requirement"],
                        incident_date=incident_date,
                    ),
                    "authoritative": True,
                    "planning_model": "policy_manifest",
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
            }

        try:
            policy = search(q, insurance_type=insurance_type, policy_number=policy_number, document_types=["policy_wording"], incident_date=incident_date)
            guidance = search(q, insurance_type=insurance_type, document_types=["regulation", "guideline", "claim_requirement"], incident_date=incident_date)
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
