"""Canonical Phase 1 insurance claim schema and labels."""

SUPPORTED_INSURANCE_TYPES = {
    "health": "Health",
    "senior_health": "Senior Health",
    "home": "Home",
    "travel": "Travel",
    "motor": "Motor",
    "cyber": "Cyber",
}

INSURANCE_TYPE_KEYS = set(SUPPORTED_INSURANCE_TYPES.keys())

# Per the project flow, Phase 1 collects the common baseline fields. Incident
# location is intentionally included here because it is part of the baseline,
# while claim-type-specific questions/documents remain Phase 2.
COMMON_REQUIRED_FIELDS = [
    "policy_id",
    "event_date",
    "insurance_type",
    "event_description",
    "event_location",
    "estimated_claim_amount",
]

FIELD_HUMAN_NAMES = {
    "policy_id": "policy number",
    "event_date": "incident date",
    "insurance_type": "insurance type",
    "event_description": "what happened",
    "event_location": "incident location",
    "estimated_claim_amount": "estimated loss or damage amount",
}
