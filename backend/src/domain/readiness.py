"""Deterministic submission-readiness facade."""
from __future__ import annotations
from typing import Any, Iterable
from src.domain.claim_context import calculate_readiness


def build_readiness(
    *,
    requirements: Iterable[Any],
    policy_verification: dict[str, Any] | None,
    evidence_rows: Iterable[Any] = (),
    exceptions: Iterable[Any] = (),
    submission_confirmation: bool = False,
) -> dict[str, Any]:
    return calculate_readiness(
        requirements=requirements,
        policy_verification=policy_verification,
        evidence_rows=evidence_rows,
        exceptions=exceptions,
        submission_confirmation=submission_confirmation,
    ).as_dict()
