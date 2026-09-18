"""Production RAG orchestration extracting requirements directly from authoritative policy and regulatory documents."""
from datetime import date
from src.agents.llm_factory import get_configured_llm
from .requirements import get_requirements_from_context
from .store import search
from .reranker import rerank

class KnowledgeRetrievalError(RuntimeError):
    pass

class KnowledgeRetriever:
    def retrieve(self, *, insurance_type: str, policy_number: str | None = None, incident_date: date | None = None, query: str = "") -> dict:
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
            return {
                "available": False,
                "status": "NO_RELEVANT_KNOWLEDGE",
                "requirements": [],
                "policy": [],
                "regulations": [],
            }

        try:
            requirements = get_requirements_from_context(
                get_configured_llm(),
                insurance_type=insurance_type,
                policy_context=policy,
                regulatory_context=guidance,
                incident_description=q,
            )
        except Exception:
            requirements = []

        if not requirements:
            return {
                "available": False,
                "status": "REQUIREMENT_PLAN_UNAVAILABLE",
                "requirements": [],
                "policy": policy,
                "regulations": guidance,
            }

        return {
            "available": True,
            "status": "OK",
            "requirements": requirements,
            "policy": policy,
            "regulations": guidance,
        }
