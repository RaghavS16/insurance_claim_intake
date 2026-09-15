"""Retrieval abstraction for claim requirements, policies, and regulations."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from .models import KnowledgeChunk, RequirementSet
from .requirements import get_requirement_set

@dataclass
class RetrievalContext:
    requirements: RequirementSet
    policy_chunks: list[KnowledgeChunk]
    regulation_chunks: list[KnowledgeChunk]

class KnowledgeRetriever:
    """Provider-neutral retrieval interface.

    The initial implementation uses the structured requirement catalogue. It is
    intentionally designed so a pgvector/managed-vector implementation can be
    plugged in later without changing agent nodes.
    """

    def retrieve(self, *, insurance_type: str, policy_number: str | None = None,
                 incident_date: date | None = None, query: str = "") -> RetrievalContext:
        return RetrievalContext(
            requirements=get_requirement_set(insurance_type),
            policy_chunks=[],
            regulation_chunks=[],
        )
