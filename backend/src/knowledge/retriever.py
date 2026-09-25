"""Production RAG orchestration extracting requirements directly from authoritative policy and regulatory documents."""
from datetime import date
from src.agents.llm_factory import LLMTransientError, get_configured_llm, is_transient_llm_error
from .requirements import get_requirements_from_context, get_provisional_requirements
from .store import search
from .reranker import rerank

class KnowledgeRetrievalError(RuntimeError):
    pass

class KnowledgeRetriever:
    def retrieve(self, *, insurance_type: str, policy_number: str | None = None, incident_date: date | None = None, query: str = "", intake_channel: str = "insurer_web_portal", intake_started_at: str | None = None) -> dict:
        q = (query or insurance_type).strip()
        if not insurance_type:
            return {"available": False, "status": "INVALID_CONTEXT", "requirements": [], "policy": [], "regulations": []}
        
        policy = []
        guidance = []
        try:
            policy = search(q, insurance_type=insurance_type, policy_number=policy_number, document_types=["policy_wording"], incident_date=incident_date)
            guidance = search(q, insurance_type=insurance_type, document_types=["regulation", "guideline", "claim_requirement"], incident_date=incident_date)
        except Exception:
            pass

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
            provisional = get_provisional_requirements(
                get_configured_llm(),
                insurance_type=insurance_type,
                claim_facts={"policy_number": policy_number, "incident_date": str(incident_date) if incident_date else None, "incident": q},
                conversation=q,
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
            requirements = get_requirements_from_context(
                get_configured_llm(),
                insurance_type=insurance_type,
                policy_context=policy,
                regulatory_context=guidance,
                incident_description=q,
                intake_channel=intake_channel,
                intake_started_at=intake_started_at,
            )
        except Exception as exc:
            # Preserve the transient-provider state so the conversational layer can
            # retry RAG instead of incorrectly reporting a permanent missing plan.
            transient_text = str(exc).lower()
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
                get_configured_llm(),
                insurance_type=insurance_type,
                claim_facts={"policy_number": policy_number, "incident_date": str(incident_date) if incident_date else None, "incident": q},
                conversation=q,
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
