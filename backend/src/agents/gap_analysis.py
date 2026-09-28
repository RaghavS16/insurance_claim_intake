"""Claim gap analysis driven by the active requirement manifest."""
from __future__ import annotations

import re
from typing import Any, Dict, List


def analyze_claim_gaps(state: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-check baseline facts and policy-derived requirements.

    Policy-specific requirements belong to the RAG manifest. This module never
    invents motor/health/property checklists outside that manifest.
    """
    data = state.get("extracted_data") or {}
    est_amount = data.get("estimated_claim_amount")
    missing_fields = list(state.get("missing_fields") or [])
    dynamic_missing = list(state.get("dynamic_missing") or [])
    missing_evidence = list(state.get("missing_evidence") or [])
    pending_review = list(state.get("pending_evidence_review") or [])
    evidence = list(state.get("evidence") or [])

    gaps: List[Dict[str, Any]] = []
    consistency_notes: List[str] = []

    for field in missing_fields:
        gaps.append({
            "category": "baseline_missing",
            "field": field,
            "severity": "high",
            "message": f"Core detail required: {field.replace('_', ' ')}",
        })
    if not missing_fields:
        consistency_notes.append("Baseline claim foundation is complete.")

    for requirement in dynamic_missing:
        gaps.append({
            "category": "policy_requirement_missing",
            "field": requirement.get("key"),
            "severity": "high",
            "message": requirement.get("label") or str(requirement.get("key") or "").replace("_", " "),
            "condition": requirement.get("condition"),
            "source_section": requirement.get("source_section"),
            "source_chunk_ids": requirement.get("source_chunk_ids") or [],
        })

    for requirement in missing_evidence:
        gaps.append({
            "category": "policy_evidence_missing",
            "field": requirement.get("key"),
            "severity": "high",
            "message": requirement.get("label") or str(requirement.get("key") or "").replace("_", " "),
            "condition": requirement.get("condition"),
            "source_section": requirement.get("source_section"),
            "source_chunk_ids": requirement.get("source_chunk_ids") or [],
        })

    for requirement in pending_review:
        gaps.append({
            "category": "policy_evidence_review_pending",
            "field": requirement.get("key"),
            "severity": "high",
            "message": requirement.get("label") or str(requirement.get("key") or "").replace("_", " "),
            "condition": requirement.get("condition"),
            "source_section": requirement.get("source_section"),
            "source_chunk_ids": requirement.get("source_chunk_ids") or [],
        })

    if est_amount is not None:
        try:
            amount = float(est_amount)
            if amount <= 0:
                gaps.append({
                    "category": "amount_zero",
                    "field": "estimated_claim_amount",
                    "severity": "medium",
                    "message": "Loss amount appears zero or unestimated.",
                })
            else:
                consistency_notes.append(f"Estimated claim loss recorded: {amount:,.2f}")
        except (ValueError, TypeError):
            gaps.append({
                "category": "amount_invalid",
                "field": "estimated_claim_amount",
                "severity": "medium",
                "message": "Loss amount needs numerical clarification.",
            })

    if evidence:
        consistency_notes.append(f"{len(evidence)} evidence item(s) are attached to the claim.")

    last_utterance = str(state.get("last_user_utterance") or "").lower()
    frustration_cues = re.search(
        r"\b(frustrated|angry|terrible|ridiculous|taking too long|already said|hate this|waste of time|useless|horrible)\b",
        last_utterance,
    )
    distress_cues = re.search(
        r"\b(hurt|injured|scared|emergency|stranded|hospital|pain|trauma|frightened)\b",
        last_utterance,
    )

    user_mood = "frustrated" if frustration_cues else "distressed" if distress_cues else "normal"

    return {
        "flagged_gaps": gaps,
        "consistency_notes": consistency_notes,
        "has_critical_gaps": any(g.get("severity") == "high" for g in gaps),
        "total_gaps": len(gaps),
        "user_sentiment": user_mood,
        "de_escalation_needed": user_mood in {"frustrated", "distressed"},
    }
