"""Canonical, source-aware claim context used by the agentic intake workflow.

The database remains authoritative.  This module contains deterministic read/decision
logic only; no LLM output can make a claim submission-ready by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional


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


def _requirement_blocking(requirement: Any) -> bool:
    required = bool(getattr(requirement, "required", True))
    state = str(getattr(requirement, "status", "unknown")).lower()
    return required and state not in {"satisfied", "verified", "waived"}


def calculate_readiness(
    *,
    requirements: Iterable[Any],
    policy_verification: Optional[dict[str, Any]] = None,
    evidence_rows: Iterable[Any] = (),
    exceptions: Iterable[Any] = (),
    claimant_confirmation: Optional[bool] = None,
    rag_status: Optional[str] = None,
) -> ReadinessResult:
    if claimant_confirmation is None:
        claimant_confirmation = True if (policy_verification and policy_verification.get("valid") is True) else False
    requirements_list = list(requirements)
    evidence_list = list(evidence_rows)
    exception_list = list(exceptions)

    blocking: list[dict[str, Any]] = []
    if len(requirements_list) == 0 or (rag_status is not None and rag_status != "OK"):
        blocking.append(
            {
                "id": "policy_manifest_unavailable",
                "key": "policy_manifest",
                "label": "Policy requirement manifest unavailable — escalate to admin/adjuster to index policy wording",
                "type": "KNOWLEDGE",
                "status": "knowledge_unavailable",
                "required": True,
            }
        )

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
        "claimant_confirmation": "PASS" if claimant_confirmation else "PENDING",
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
        and verification["claimant_confirmation"] == "PASS"
        and not blocking_exceptions
    )

    return ReadinessResult(
        ready=ready,
        blocking_requirements=blocking,
        verification=verification,
        evidence={
            "required": sum(
                1
                for req in requirements_list
                if bool(getattr(req, "required", True)) and getattr(req, "evidence_type", None)
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
