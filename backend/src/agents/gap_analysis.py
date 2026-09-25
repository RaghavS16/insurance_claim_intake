"""Continuous information validation and gap analysis engine.

Cross-checks extracted claim facts against policy coverage rules, regulatory mandates,
and incident details to flag inconsistencies, missing elements, or unclear submissions,
enabling the conversational agent to circle back smoothly without restarting.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from src.agents.state import ClaimState


def analyze_claim_gaps(state: ClaimState | Dict[str, Any]) -> Dict[str, Any]:
    """Perform continuous cross-checking of extracted data and evidence."""
    data = state.get("extracted_data") or {}
    insurance_type = str(data.get("insurance_type") or "").lower()
    description = str(data.get("event_description") or "").lower()
    est_amount = data.get("estimated_claim_amount")
    missing_fields = list(state.get("missing_fields") or [])
    dynamic_missing = list(state.get("dynamic_missing") or [])
    missing_evidence = list(state.get("missing_evidence") or [])
    evidence = list(state.get("evidence") or [])

    gaps: List[Dict[str, Any]] = []
    consistency_notes: List[str] = []

    # 1. Baseline completeness check
    if not missing_fields:
        consistency_notes.append("Baseline claim foundation (policy, date, location, amount, description) complete.")
    else:
        for f in missing_fields:
            gaps.append({
                "category": "baseline_missing",
                "field": f,
                "severity": "high",
                "message": f"Core detail required: {f.replace('_', ' ')}",
            })

    # 2. Motor-specific domain cross-checks
    if insurance_type == "motor":
        # Third-party involvement check
        has_tp_mention = bool(re.search(r"\b(another|other|second|third|cab|truck|bus|rickshaw|bike|car|vehicle|driver|pedestrian)\b", description))
        has_tp_data = bool(data.get("third_party_details") or data.get("third_party_vehicle") or data.get("third_party_insurance"))
        if has_tp_mention and not has_tp_data:
            gaps.append({
                "category": "third_party_gap",
                "field": "third_party_details",
                "severity": "medium",
                "message": "Narrative mentions another party; details or police report may be needed.",
            })
        elif has_tp_data:
            consistency_notes.append("Third-party vehicle/driver details captured.")

        # Police FIR requirement check for major collision or theft
        is_theft_or_major = bool(re.search(r"\b(theft|stolen|hit and run|major|total loss|fatal|injury|hospital)\b", description))
        has_police_report = any("police" in str(e.get("document_type", "")).lower() or "fir" in str(e.get("label", "")).lower() for e in evidence)
        if is_theft_or_major and not has_police_report and not any(r.get("key") == "police_report" for r in missing_evidence):
            gaps.append({
                "category": "regulatory_mandate",
                "field": "police_fir",
                "severity": "high",
                "message": "Major collision or theft requires police intimation / FIR under motor claim regulations.",
            })

    # 3. Health-specific cross-checks
    elif insurance_type in {"health", "senior_health"}:
        # Inpatient vs Outpatient
        is_hospitalized = bool(re.search(r"\b(admit|admitted|hospital|ward|icu|surgery|operation)\b", description))
        if is_hospitalized and not data.get("hospital_name") and "event_location" not in data:
            gaps.append({
                "category": "hospital_identity_gap",
                "field": "hospital_name",
                "severity": "medium",
                "message": "Hospital facility name is needed for network cashless pre-authorization.",
            })

    # 4. Property-specific cross-checks
    elif insurance_type in {"property", "home"}:
        is_water_or_fire = bool(re.search(r"\b(fire|burst|pipe|flood|storm|roof|leak)\b", description))
        if is_water_or_fire and not data.get("mitigation_steps"):
            gaps.append({
                "category": "mitigation_gap",
                "field": "mitigation_steps",
                "severity": "low",
                "message": "Confirming mitigation steps taken to prevent further loss supports full reimbursement.",
            })

    # 5. Financial reasonableness & documentation
    if est_amount is not None:
        try:
            amt = float(est_amount)
            if amt <= 0:
                gaps.append({
                    "category": "amount_zero",
                    "field": "estimated_claim_amount",
                    "severity": "medium",
                    "message": "Loss amount appears zero or unestimated.",
                })
            else:
                consistency_notes.append(f"Estimated claim loss recorded: {amt:,.2f}")
        except (ValueError, TypeError):
            gaps.append({
                "category": "amount_invalid",
                "field": "estimated_claim_amount",
                "severity": "medium",
                "message": "Loss amount needs numerical clarification.",
            })

    # 6. Sentiment & Frustration Analysis
    last_utterance = str(state.get("last_user_utterance") or "").lower()
    frustration_cues = re.search(r"\b(frustrated|angry|terrible|ridiculous|taking too long|already said|hate this|waste of time|useless|horrible)\b", last_utterance)
    distress_cues = re.search(r"\b(hurt|injured|scared|emergency|stranded|hospital|pain|trauma|frightened)\b", last_utterance)

    user_mood = "normal"
    if frustration_cues:
        user_mood = "frustrated"
    elif distress_cues:
        user_mood = "distressed"

    gap_analysis = {
        "flagged_gaps": gaps,
        "consistency_notes": consistency_notes,
        "has_critical_gaps": any(g.get("severity") == "high" for g in gaps),
        "total_gaps": len(gaps),
        "user_sentiment": user_mood,
        "de_escalation_needed": user_mood in {"frustrated", "distressed"},
    }
    return gap_analysis
