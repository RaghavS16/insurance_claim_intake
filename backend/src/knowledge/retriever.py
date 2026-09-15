"""Semantic RAG retriever; claim requirements are generated from retrieved evidence."""
from datetime import date
from src.agents.llm_factory import get_configured_llm
from .requirements import get_requirements_from_context
from .store import search

class KnowledgeRetriever:
    def retrieve(self,*,insurance_type:str,policy_number:str|None=None,incident_date:date|None=None,query:str="")->dict:
        q=query or insurance_type
        try:
            policy=search(q,insurance_type=insurance_type,policy_number=policy_number,document_types=["policy_wording"],incident_date=incident_date)
            guidance=search(q,insurance_type=insurance_type,document_types=["regulation","guideline","claim_requirement"],incident_date=incident_date)
        except Exception:
            # RAG is an enrichment layer. A temporary embedding/vector outage must
            # never break the baseline conversational intake.
            policy=[]; guidance=[]
        requirements=get_requirements_from_context(get_configured_llm(),insurance_type=insurance_type,policy_context=policy,regulatory_context=guidance,incident_description=query)
        return {"requirements":requirements,"policy":policy,"regulations":guidance}
