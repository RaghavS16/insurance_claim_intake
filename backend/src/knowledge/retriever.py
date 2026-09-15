"""Retrieval interface for policy/regulatory-grounded claim questions."""
from __future__ import annotations
from datetime import date
from .requirements import get_requirements
from .store import search

class KnowledgeRetriever:
    def requirements(self, insurance_type: str) -> list[dict]:
        return [r.model_dump() for r in get_requirements(insurance_type)]

    def retrieve(self, *, insurance_type: str, policy_number: str | None = None,
                 incident_date: date | None = None, query: str = "") -> dict:
        # This contract is deliberately provider-neutral. The current repository's
        # policy table remains authoritative for policy identity/date checks.
        return {
            "requirements": self.requirements(insurance_type),
            "policy": search(query or insurance_type, insurance_type=insurance_type, policy_number=policy_number, document_types=["policy_wording"], incident_date=incident_date),
            "regulations": search(query or insurance_type, insurance_type=insurance_type, document_types=["regulation", "guideline"], incident_date=incident_date),
        }
