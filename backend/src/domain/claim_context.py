"""Canonical, source-aware claim context used by the agentic intake workflow.

This module is deliberately independent from the conversational LangGraph state.
The claim database remains the source of truth; this context is a read/decision model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


FACT_STATES = {
    "PROPOSED",
    "VALIDATED",
    "USER_CONFIRMED",
    "EVIDENCE_SUPPORTED",
    "SYSTEM_VERIFIED",
    "ACCEPTED",
    "CONFLICTED",
    "REJECTED",
}

REQUIREMENT_TYPES = {"FACT", "DOCUMENT", "VERIFICATION", "AUTHORIZATION"}
REQUIREMENT_STATES = {
    "unknown",
    "open",
    "satisfied",
    "blocked",
    "waived",
    "verified",
    "conflicted",
}

POST_SUBMISSION_STATUSES = {
    "submitted",
    "assigned",
    "under_review",
    "pending_evidence",
    "approved",
    "partially_approved",
    "rejected",
    "escalated",
    "closed",
}


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    blocking_requirements: list[dict[str, Any]]
    verification: dict[str, str]
    evidence: dict[str, int]
    exceptions: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blocking_requirements": self.blocking_requirements,
            "verification": self.verification,
            "evidence": self.evidence,
            "exceptions": self.exceptions,
        }


def canonical_fact(
    *,
    field: str,
    value: Any,
    source_type: str,
    source_id: Optional[str] = None,
    status: str = "PROPOSED",
    confidence: Optional[float] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if status not in FACT_STATES:
        raise ValueError(f"Unknown fact status: {status}")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return {
        "field": field,
        "value": value,
        "source_type": source_type,
        "source_id": source_id,
        "status": status,
        "confidence": confidence,
        "metadata": metadata or {},
    }


def merge_fact_metadata(
    existing: Optional[dict[str, Any]],
    *,
    source_type: str,
    source_id: Optional[str],
    confidence: Optional[float],
    status: str,
) -> dict[str, Any]:
    """Produce provenance without overwriting historical source semantics."""
    result = dict(existing or {})
    history = list(result.get("provenance_history") or [])
    history.append(
        {
            "source_type": source_type,
            "source_id": source_id,
            "confidence": confidence,
            "status": status,
        }
    )
    result["provenance_history"] = history[-20:]
    result["last_source_type"] = source_type
    result["last_source_id"] = source_id
    result["last_status"] = status
    return result


def _requirement_blocking(requirement: Any) -> bool:
    required = bool(getattr(requirement, "required", True))
    status = str(getattr(requirement, "status", "unknown")).lower()
    return required and status not in {"satisfied", "verified", "waived"}


def calculate_readiness(
    *,
    requirements: Iterable[Any],
    policy_verification: Optional[dict[str, Any]] = None,
    evidence_rows: Iterable[Any] = (),
    exceptions: Iterable[Any] = (),
    submission_confirmation: bool = False,
) -> ReadinessResult:
    requirements_list = list(requirements)
    evidence_list = list(evidence_rows)
    exception_list = list(exceptions)

    blocking: list[dict[str, Any]] = []
    for req in requirements_list:
        provenance = getattr(req, "provenance_json", None) or {}
        authoritative = provenance.get("authoritative", True)
        blocked_by_knowledge = bool(getattr(req, "required", True)) and authoritative is False
        if _requirement_blocking(req) or blocked_by_knowledge:
            blocking.append(
                {
                    "id": str(getattr(req, "id", "")),
                    "key": str(getattr(req, "requirement_key", "")),
                    "label": str(getattr(req, "label", "")),
                    "type": (
                        "DOCUMENT"
                        if getattr(req, "evidence_type", None)
                        else ("KNOWLEDGE" if blocked_by_knowledge else "FACT")
                    ),
                    "status": "knowledge_pending" if blocked_by_knowledge else str(getattr(req, "status", "unknown")),
                    "required": bool(getattr(req, "required", True)),
                }
            )

    verification = {
        "policy": "PASS"
        if policy_verification and policy_verification.get("valid") is True
        else "PENDING",
        "identity": "PASS"
        if policy_verification and policy_verification.get("identity_verified") is True
        else "PENDING",
    }

    verified_evidence = sum(
        1
        for item in evidence_list
        if str(getattr(item, "verification_status", "")).upper() == "VERIFIED"
    )

    blocking_exceptions = [
        {
            "id": str(getattr(item, "id", "")),
            "type": str(getattr(item, "event_type", "EXCEPTION")),
            "reason": str(getattr(item, "reason", "")),
            "blocking": True,
        }
        for item in exception_list
        if bool(getattr(item, "blocking", True))
    ]

    ready = (
        not blocking
        and verification["policy"] == "PASS"
        and verification["identity"] == "PASS"
        and not blocking_exceptions
        and submission_confirmation
    )
    return ReadinessResult(
        ready=ready,
        blocking_requirements=blocking,
        verification=verification,
        evidence={
            "required": sum(
                1
                for req in requirements_list
                if bool(getattr(req, "required", True))
                and getattr(req, "evidence_type", None)
            ),
            "received": sum(
                1
                for item in evidence_list
                if str(getattr(item, "status", "")).lower() not in {"rejected"}
            ),
            "verified": verified_evidence,
        },
        exceptions=blocking_exceptions,
    )
