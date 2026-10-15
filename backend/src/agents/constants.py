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

# Zero hardcoded baseline fields: everything required must come entirely
# from authoritative policy wording and regulatory documents via RAG.
COMMON_REQUIRED_FIELDS: list[str] = []

FIELD_HUMAN_NAMES: dict[str, str] = {
    "policy_id": "policy number",
    "event_date": "incident date",
    "insurance_type": "insurance type",
    "event_description": "what happened",
    "event_location": "incident location",
    "estimated_claim_amount": "estimated loss or damage amount",
}
